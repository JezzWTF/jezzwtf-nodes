"""Pure logic for the LoRA Inspector: safetensors metadata, SHA-256 hashing, the JSON cache,
Civitai lookup (with an injectable opener) and payload building. No ComfyUI imports."""
from __future__ import annotations

import hashlib
import html
import json
import os
import re
import struct
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from typing import Union

from ._comfy import log

JSONScalar = Union[str, int, float, bool, None]
JSONValue = Union[JSONScalar, list["JSONValue"], dict[str, "JSONValue"]]
JSONDict = dict[str, JSONValue]

ProgressFn = Callable[[str, float, str], None]  # (stage, value, message)

CHUNK = 8 * 1024 * 1024
MAX_HEADER = 20 * 1024 * 1024
NOT_FOUND_TTL = 24 * 3600.0
SOURCES = {"civitai.com": "https://civitai.com/api/v1", "red.civitai.com": "https://red.civitai.com/api/v1"}
USER_AGENT = "jezzwtf-lora-inspector/1.0"
VIDEO_EXT = re.compile(r"\.(mp4|webm|mov|m4v)$", re.IGNORECASE)


def read_safetensors_metadata(path: str) -> JSONDict:
    if not path.lower().endswith(".safetensors"):
        return {}
    try:
        with open(path, "rb") as fh:
            (n,) = struct.unpack("<Q", fh.read(8))
            header = json.loads(fh.read(min(n, MAX_HEADER)).decode("utf-8"))
        meta = header.get("__metadata__", {}) if isinstance(header, dict) else {}
        return meta if isinstance(meta, dict) else {}
    except Exception as exc:
        return {"_error": str(exc)}


def sha256_file(path: str, progress: ProgressFn | None = None, chunk: int = CHUNK) -> str:
    total = os.path.getsize(path)
    h = hashlib.sha256()
    done = 0
    last = -1.0
    with open(path, "rb") as fh:
        while True:
            buf = fh.read(chunk)
            if not buf:
                break
            h.update(buf)
            done += len(buf)
            frac = done / total if total else 1.0
            if progress and (frac - last >= 0.01 or done >= total):
                last = frac
                progress("hash", round(frac, 4), f"hashing {done / 1048576:.1f} / {total / 1048576:.1f} MB")
    if progress and total == 0:
        progress("hash", 1.0, "hashing 0.0 / 0.0 MB")
    return h.hexdigest()


class InspectorCache:
    """Flat JSON object on disk, loaded lazily, rewritten in full after every set.

    A cache file that exists but cannot be parsed is moved aside to `<path>.corrupt-<ts>` (never
    silently overwritten); one that cannot be read at all disables persistence for this process."""

    def __init__(self, path: str) -> None:
        self.path = path
        self._data: JSONDict | None = None
        self._persist = True
        self._lock = threading.Lock()

    def _set_aside(self, reason: str) -> None:
        backup = f"{self.path}.corrupt-{int(time.time())}"
        try:
            os.replace(self.path, backup)
            log.warning("LoRA Inspector cache %s is unusable (%s); kept as %s and started fresh",
                        self.path, reason, backup)
        except OSError as exc:
            self._persist = False
            log.warning("LoRA Inspector cache %s is unusable (%s) and could not be moved aside (%s); "
                        "results will not be saved", self.path, reason, exc)

    def _load(self) -> JSONDict:
        if self._data is None:
            self._data = {}
            try:
                with open(self.path, encoding="utf-8") as fh:
                    loaded = json.load(fh)
            except FileNotFoundError:
                pass
            except ValueError as exc:  # JSONDecodeError and UnicodeDecodeError
                self._set_aside(str(exc))
            except OSError as exc:
                self._persist = False
                log.warning("LoRA Inspector cache %s is unreadable (%s); results will not be saved", self.path, exc)
            else:
                if isinstance(loaded, dict):
                    self._data = loaded
                else:
                    self._set_aside("not a JSON object")
        return self._data

    def get(self, key: str) -> JSONValue:
        with self._lock:
            return self._load().get(key)

    def set(self, key: str, value: JSONValue) -> None:
        with self._lock:
            data = self._load()
            data[key] = value
            if not self._persist:
                return
            folder = os.path.dirname(self.path) or "."
            os.makedirs(folder, exist_ok=True)
            fd, tmp = tempfile.mkstemp(prefix=os.path.basename(self.path) + ".", suffix=".tmp", dir=folder)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    json.dump(data, fh, ensure_ascii=False)
                os.replace(tmp, self.path)
            except BaseException:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise


def sha_cache_key(path: str) -> str:
    st = os.stat(path)
    return f"sha::{path}::{int(st.st_mtime)}::{st.st_size}"


def resolve_api_key(explicit: str | None, env: Mapping[str, str], key_files: Sequence[str]) -> str | None:
    if explicit and explicit.strip():
        return explicit.strip()
    for var in ("CIVITAI_API_TOKEN", "CIVITAI_API_KEY"):
        v = env.get(var, "").strip()
        if v:
            return v
    for f in key_files:
        try:
            with open(f, encoding="utf-8") as fh:
                v = fh.read().strip()
            if v:
                return v
        except OSError:
            continue
    return None


def source_order(source: str) -> list[str]:
    names = list(SOURCES)
    if source in SOURCES:
        return [source] + [n for n in names if n != source]
    return names


class FetchError(RuntimeError):
    pass


Opener = Callable[[urllib.request.Request, float], bytes]


def default_opener(req: urllib.request.Request, timeout: float) -> bytes:
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - fixed https hosts
        return bytes(resp.read())


def fetch_by_hash(sha: str, source: str, api_key: str | None, progress: ProgressFn | None = None,
                  opener: Opener = default_opener, timeout: float = 25.0) -> tuple[str, JSONDict | None]:
    """Query each source in order. First success → (source, record). All 404 → (last, None)."""
    order = source_order(source)
    errors: list[str] = []
    not_found = 0
    for i, name in enumerate(order):
        url = f"{SOURCES[name]}/model-versions/by-hash/{sha}"
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        if progress:
            progress("fetch", 0.0, f"querying {name}")
        try:
            body = opener(urllib.request.Request(url, headers=headers), timeout)
            data = json.loads(body.decode("utf-8"))
            if progress:
                progress("fetch", 1.0, f"found on {name}")
            if not isinstance(data, dict):
                raise ValueError("unexpected response shape")
            return name, data
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                not_found += 1
                errors.append(f"{name}: not found")
            elif exc.code in (401, 403):
                errors.append(f"{name}: authentication failed (HTTP {exc.code}) - check the Civitai API key")
            else:
                errors.append(f"{name}: HTTP {exc.code}")
        except Exception as exc:
            errors.append(f"{name}: {exc}")
        if progress:
            progress("fetch", (i + 1) / len(order), errors[-1])
    if not_found == len(order):
        return order[-1], None
    raise FetchError("; ".join(errors))


def strip_html(text: object, limit: int = 600) -> str:
    if not isinstance(text, str):
        return ""
    s = re.sub(r"<[^>]+>", " ", text)
    s = html.unescape(s)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:limit]


def safe_civitai_url(url: object) -> str | None:
    """`url` if it is an https URL on civitai.com or one of its subdomains, else None."""
    if not isinstance(url, str):
        return None
    try:
        parts = urllib.parse.urlsplit(url.strip())
        host = (parts.hostname or "").lower()
    except ValueError:
        return None
    if parts.scheme != "https" or not (host == "civitai.com" or host.endswith(".civitai.com")):
        return None
    return url.strip()


def media_type(url: str, declared: object) -> str:
    if declared in ("video", "image"):
        return str(declared)
    bare = re.split(r"[?#]", url, maxsplit=1)[0]
    return "video" if VIDEO_EXT.search(bare) else "image"


def _first_truthy(meta: Mapping[str, JSONValue], *keys: str) -> str | None:
    for k in keys:
        v = meta.get(k)
        if v:
            return str(v)
    return None


def _d(v: JSONValue) -> JSONDict:
    return v if isinstance(v, dict) else {}


def build_payload(lora_file: str, sha: str, source: str, civ: JSONDict | None,
                  local_meta: Mapping[str, JSONValue]) -> JSONDict:
    local: JSONDict = {
        "base_model_version": _first_truthy(local_meta, "ss_base_model_version"),
        "sd_model_name": _first_truthy(local_meta, "ss_sd_model_name"),
        "network_module": _first_truthy(local_meta, "ss_network_module"),
        "resolution": _first_truthy(local_meta, "ss_resolution"),
        "clip_skip": _first_truthy(local_meta, "ss_clip_skip"),
        "steps": _first_truthy(local_meta, "ss_steps"),
        "modelspec_title": _first_truthy(local_meta, "modelspec.title", "ss_output_name"),
    }
    payload: JSONDict = {
        "found": civ is not None, "source": source, "lora_file": lora_file, "sha256": sha,
        "model_name": None, "version_name": None, "model_type": None, "base_model": None,
        "trigger_words": [], "description": "", "url": None, "image": None, "images": [],
        "downloads": None, "rating": None, "nsfw": False, "file_size_kb": None, "format": None,
        "local": local,
    }
    if civ is None:
        return payload
    model = _d(civ.get("model"))
    stats = _d(civ.get("stats"))
    payload["model_name"] = model.get("name")
    payload["version_name"] = civ.get("name")
    payload["model_type"] = model.get("type")
    payload["base_model"] = civ.get("baseModel")
    words = civ.get("trainedWords")
    payload["trigger_words"] = [str(w) for w in words if w] if isinstance(words, list) else []
    payload["description"] = strip_html(civ.get("description"))
    if model.get("id") is not None:
        payload["url"] = f"https://civitai.com/models/{model.get('id')}?modelVersionId={civ.get('id')}"
    payload["downloads"] = stats.get("downloadCount")
    payload["rating"] = stats.get("rating")
    payload["nsfw"] = bool(model.get("nsfw", False))
    files = [f for f in civ.get("files") or [] if isinstance(f, dict)] if isinstance(civ.get("files"), list) else []
    primary = next((f for f in files if f.get("primary")), files[0] if files else None)
    if primary is not None:
        payload["file_size_kb"] = primary.get("sizeKB")
        payload["format"] = _d(primary.get("metadata")).get("format")
    images: list[JSONValue] = []
    raw_images = civ.get("images")
    for im in raw_images if isinstance(raw_images, list) else []:
        if not isinstance(im, dict):
            continue
        url = safe_civitai_url(im.get("url"))
        if url is None:
            continue
        images.append({"url": url, "type": media_type(url, im.get("type")), "width": im.get("width"),
                       "height": im.get("height"), "nsfw": im.get("nsfw", "None") or "None",
                       "meta": im.get("meta") if isinstance(im.get("meta"), dict) else {}})
    payload["images"] = images
    still = next((i for i in images if isinstance(i, dict) and i.get("type") == "image"), None)
    first = still or (images[0] if images else None)
    payload["image"] = first.get("url") if isinstance(first, dict) else None
    return payload


def inspect_lora(path: str, lora_file: str, source: str, api_key: str | None, force: bool,
                 cache: InspectorCache, progress: ProgressFn | None = None,
                 opener: Opener = default_opener, now: Callable[[], float] = time.time) -> JSONDict:
    if not os.path.isfile(path):
        raise FileNotFoundError(f"LoRA not found: {lora_file}")
    if progress:
        progress("start", 0.0, f"inspecting {lora_file}")
    local_meta = read_safetensors_metadata(path)

    skey = sha_cache_key(path)
    cached_sha = cache.get(skey)
    if isinstance(cached_sha, str) and not force:
        sha = cached_sha
        if progress:
            progress("hash", 1.0, "hash from cache")
    else:
        sha = sha256_file(path, progress)
        cache.set(skey, sha)

    ckey = f"civitai::{sha}"
    warning: str | None = None
    hit = cache.get(ckey)
    civ: JSONDict | None
    if isinstance(hit, dict) and not force and _fresh(hit, now()):
        src = hit.get("source")
        found_source = src if isinstance(src, str) else "civitai.com"
        data = hit.get("data")
        civ = data if isinstance(data, dict) else None
    else:
        try:
            found_source, civ = fetch_by_hash(sha, source, api_key, progress, opener)
            cache.set(ckey, {"source": found_source, "data": civ, "ts": now()})
        except FetchError as exc:
            found_source, civ, warning = "local only", None, str(exc)
    payload = build_payload(lora_file, sha, found_source, civ, local_meta)
    if warning:
        payload["warning"] = warning
    return payload


def _fresh(entry: Mapping[str, JSONValue], now: float) -> bool:
    """Found records never expire; a 'not on Civitai' answer is re-checked after a day."""
    if isinstance(entry.get("data"), dict):
        return True
    ts = entry.get("ts")
    return isinstance(ts, (int, float)) and now - float(ts) < NOT_FOUND_TTL


def node_outputs(payload: Mapping[str, JSONValue], lora_file: str) -> tuple[str, str, str, str]:
    local = _d(payload.get("local"))
    name = payload.get("model_name") or local.get("modelspec_title") or lora_file
    base = payload.get("base_model") or local.get("base_model_version") or ""
    words = payload.get("trigger_words")
    trig = ", ".join(str(w) for w in words) if isinstance(words, list) else ""
    return str(name), str(base), trig, json.dumps(payload, ensure_ascii=False)
