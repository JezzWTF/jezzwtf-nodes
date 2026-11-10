from __future__ import annotations

import hashlib
import io
import json
import urllib.error
import urllib.request
from email.message import Message
from pathlib import Path

import pytest
import torch
from safetensors.torch import save_file

from model_loaders.inspector_logic import (
    FetchError,
    InspectorCache,
    build_payload,
    fetch_by_hash,
    inspect_lora,
    media_type,
    node_outputs,
    read_safetensors_metadata,
    resolve_api_key,
    safe_civitai_url,
    sha256_file,
    source_order,
    strip_html,
)

RECORD = {
    "id": 22, "name": "v1", "baseModel": "Flux.1 D", "trainedWords": ["ohwx", "red hat"],
    "description": "<p>Nice &amp; <b>clean</b>\n\n LoRA</p>",
    "model": {"id": 11, "name": "Hat LoRA", "type": "LORA", "nsfw": False},
    "stats": {"downloadCount": 5, "rating": 4.5},
    "files": [{"sizeKB": 10.0, "metadata": {"format": "PickleTensor"}},
              {"primary": True, "sizeKB": 20.0, "metadata": {"format": "SafeTensor"}}],
    "images": [{"url": "https://image.civitai.com/a.mp4?w=1", "width": 1, "height": 2},
               {"url": "https://image.civitai.com/b.jpeg", "type": "image", "meta": {"prompt": "p"}, "nsfw": "Soft"},
               {"nourl": True}],
}


def _http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://x", code, "err", Message(), io.BytesIO(b""))


class FakeOpener:
    def __init__(self, responses: dict[str, int | dict[str, object]]) -> None:
        self.responses = responses
        self.calls: list[urllib.request.Request] = []

    def __call__(self, req: urllib.request.Request, timeout: float) -> bytes:
        self.calls.append(req)
        host = req.full_url.split("/")[2]
        r = self.responses[host]
        if isinstance(r, int):
            raise _http_error(r)
        return json.dumps(r).encode()


def _lora(tmp_path: Path, meta: dict[str, str] | None = None) -> Path:
    p = tmp_path / "hat.safetensors"
    save_file({"w": torch.ones(4)}, str(p), metadata=meta)
    return p


def test_read_metadata(tmp_path: Path) -> None:
    p = _lora(tmp_path, {"ss_base_model_version": "flux1", "modelspec.title": "Hat"})
    assert read_safetensors_metadata(str(p)) == {"ss_base_model_version": "flux1", "modelspec.title": "Hat"}
    bad = tmp_path / "bad.safetensors"
    bad.write_bytes(b"\x05\x00\x00\x00\x00\x00\x00\x00{nope")
    assert "_error" in read_safetensors_metadata(str(bad))
    assert read_safetensors_metadata(str(tmp_path / "x.ckpt")) == {}


def test_sha256_and_progress(tmp_path: Path) -> None:
    p = tmp_path / "blob.bin"
    data = bytes(range(256)) * 400
    p.write_bytes(data)
    events: list[tuple[str, float, str]] = []
    assert sha256_file(str(p), lambda s, v, m: events.append((s, v, m)), chunk=1000) == hashlib.sha256(data).hexdigest()
    assert events[-1][1] == 1.0 and all(e[0] == "hash" for e in events)
    vals = [e[1] for e in events]
    assert all(b - a >= 0.01 - 1e-9 for a, b in zip(vals, vals[1:]))


def test_cache_persists_and_reloads(tmp_path: Path) -> None:
    path = tmp_path / "sub" / "c.json"
    c = InspectorCache(str(path))
    assert c.get("k") is None
    c.set("k", {"a": [1, "ü"]})
    assert json.loads(path.read_text(encoding="utf-8")) == {"k": {"a": [1, "ü"]}}
    assert InspectorCache(str(path)).get("k") == {"a": [1, "ü"]}


def test_resolve_api_key_priority(tmp_path: Path) -> None:
    f = tmp_path / "key.txt"
    f.write_text(" filekey \n")
    assert resolve_api_key(" explicit ", {"CIVITAI_API_TOKEN": "t"}, [str(f)]) == "explicit"
    assert resolve_api_key("", {"CIVITAI_API_KEY": "k", "CIVITAI_API_TOKEN": "t"}, [str(f)]) == "t"
    assert resolve_api_key("", {"CIVITAI_API_KEY": "k"}, [str(f)]) == "k"
    assert resolve_api_key(None, {}, [str(tmp_path / "missing"), str(f)]) == "filekey"
    assert resolve_api_key(None, {}, []) is None


def test_source_order() -> None:
    assert source_order("auto") == ["civitai.com", "red.civitai.com"]
    assert source_order("red.civitai.com") == ["red.civitai.com", "civitai.com"]


def test_fetch_success_fallback_and_auth_header() -> None:
    op = FakeOpener({"civitai.com": 500, "red.civitai.com": RECORD})
    ev: list[tuple[str, float, str]] = []
    src, data = fetch_by_hash("ab", "auto", "KEY", lambda s, v, m: ev.append((s, v, m)), opener=op)
    assert src == "red.civitai.com" and data == RECORD
    assert op.calls[0].get_header("Authorization") == "Bearer KEY"
    assert op.calls[1].full_url == "https://red.civitai.com/api/v1/model-versions/by-hash/ab"
    assert [v for _, v, _ in ev] == [0.0, 0.5, 0.0, 1.0]


def test_fetch_not_found_and_errors() -> None:
    assert fetch_by_hash("ab", "auto", None, opener=FakeOpener({"civitai.com": 404, "red.civitai.com": 404})) == (
        "red.civitai.com", None)
    with pytest.raises(FetchError, match="authentication"):
        fetch_by_hash("ab", "auto", None, opener=FakeOpener({"civitai.com": 404, "red.civitai.com": 401}))


def test_helpers() -> None:
    assert strip_html("<p>a &amp;  <i>b</i></p>") == "a & b"
    assert len(strip_html("x" * 1000)) == 600
    assert media_type("https://h/v.WEBM#t", None) == "video"
    assert media_type("https://h/v.mp4", "image") == "image"
    assert media_type("https://h/a.png", "weird") == "image"


def test_build_payload() -> None:
    p = build_payload("hat.safetensors", "ab", "civitai.com", RECORD,
                      {"ss_output_name": "hat_out", "ss_steps": 100, "ss_resolution": ""})
    assert p["found"] is True and p["model_name"] == "Hat LoRA" and p["version_name"] == "v1"
    assert p["description"] == "Nice & clean LoRA"
    assert p["url"] == "https://civitai.com/models/11?modelVersionId=22"
    assert p["file_size_kb"] == 20.0 and p["format"] == "SafeTensor"
    images = p["images"]
    assert isinstance(images, list) and len(images) == 2
    assert images[0] == {"url": "https://image.civitai.com/a.mp4?w=1", "type": "video", "width": 1, "height": 2, "nsfw": "None",
                         "meta": {}}
    assert p["image"] == "https://image.civitai.com/b.jpeg"
    local = p["local"]
    assert isinstance(local, dict) and local["modelspec_title"] == "hat_out" and local["steps"] == "100"
    assert local["resolution"] is None
    empty = build_payload("f", "s", "red.civitai.com", None, {})
    assert empty["found"] is False and empty["images"] == [] and empty["trigger_words"] == []


def test_inspect_pipeline_caches(tmp_path: Path) -> None:
    lora = _lora(tmp_path, {"ss_base_model_version": "flux1"})
    cache = InspectorCache(str(tmp_path / "cache.json"))
    op = FakeOpener({"civitai.com": RECORD, "red.civitai.com": 404})
    stages: list[str] = []
    p1 = inspect_lora(str(lora), "hat.safetensors", "auto", None, False, cache, lambda s, v, m: stages.append(s), op)
    assert p1["sha256"] == hashlib.sha256(lora.read_bytes()).hexdigest()
    assert stages[0] == "start" and "hash" in stages and "fetch" in stages
    p2 = inspect_lora(str(lora), "hat.safetensors", "auto", None, False, cache, opener=op)
    assert p2 == p1 and len(op.calls) == 1
    inspect_lora(str(lora), "hat.safetensors", "auto", None, True, cache, opener=op)
    assert len(op.calls) == 2
    assert node_outputs(p1, "hat.safetensors")[:3] == ("Hat LoRA", "Flux.1 D", "ohwx, red hat")


def test_inspect_network_error_is_local_only_and_not_cached(tmp_path: Path) -> None:
    lora = _lora(tmp_path, {"ss_base_model_version": "sdxl"})
    cache = InspectorCache(str(tmp_path / "cache.json"))
    op = FakeOpener({"civitai.com": 500, "red.civitai.com": 503})
    p = inspect_lora(str(lora), "hat.safetensors", "auto", None, False, cache, opener=op)
    assert p["source"] == "local only" and "HTTP 500" in str(p["warning"])
    assert node_outputs(p, "hat.safetensors")[:2] == ("hat.safetensors", "sdxl")
    inspect_lora(str(lora), "hat.safetensors", "auto", None, False, cache, opener=op)
    assert len(op.calls) == 4


def test_not_found_expires_after_ttl(tmp_path: Path) -> None:
    lora = _lora(tmp_path)
    cache = InspectorCache(str(tmp_path / "cache.json"))
    op = FakeOpener({"civitai.com": 404, "red.civitai.com": 404})
    clock = [1000.0]
    inspect_lora(str(lora), "hat.safetensors", "auto", None, False, cache, opener=op, now=lambda: clock[0])
    inspect_lora(str(lora), "hat.safetensors", "auto", None, False, cache, opener=op, now=lambda: clock[0])
    assert len(op.calls) == 2
    clock[0] += 2 * 24 * 3600
    p = inspect_lora(str(lora), "hat.safetensors", "auto", None, False, cache, opener=op, now=lambda: clock[0])
    assert len(op.calls) == 4 and p["found"] is False and "warning" not in p


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        inspect_lora(str(tmp_path / "nope.safetensors"), "nope", "auto", None, False,
                     InspectorCache(str(tmp_path / "c.json")))


def test_safe_civitai_url_requires_https_and_civitai_host() -> None:
    assert safe_civitai_url("https://image.civitai.com/a.png") == "https://image.civitai.com/a.png"
    assert safe_civitai_url("https://civitai.com/models/1") == "https://civitai.com/models/1"
    for bad in ("javascript:alert(1)", "http://civitai.com/a", "https://evil.com/a.png",
                "https://civitai.com.evil.io/a", "https://notcivitai.com/a", "//civitai.com/a", "", None, 5):
        assert safe_civitai_url(bad) is None


def test_build_payload_drops_unsafe_image_urls() -> None:
    civ: dict[str, object] = {"id": 1, "images": [{"url": "javascript:alert(1)"}, {"url": "https://evil.com/x.png"},
                                                  {"url": "https://image.civitai.com/ok.png", "type": "image"}]}
    p = build_payload("f", "s", "civitai.com", civ, {})  # type: ignore[arg-type]
    images = p["images"]
    assert isinstance(images, list) and len(images) == 1
    assert p["image"] == "https://image.civitai.com/ok.png"


def test_corrupt_cache_is_kept_as_backup_not_overwritten(tmp_path: Path) -> None:
    path = tmp_path / "cache.json"
    path.write_text("{not json", encoding="utf-8")
    c = InspectorCache(str(path))
    assert c.get("k") is None
    c.set("k", 1)
    backups = [p for p in tmp_path.iterdir() if ".corrupt-" in p.name]
    assert len(backups) == 1 and backups[0].read_text(encoding="utf-8") == "{not json"
    assert InspectorCache(str(path)).get("k") == 1
    assert not [p for p in tmp_path.iterdir() if p.name.endswith(".tmp")]


def test_cache_non_object_is_backed_up_and_missing_file_is_fine(tmp_path: Path) -> None:
    path = tmp_path / "c.json"
    path.write_text("[1, 2]", encoding="utf-8")
    assert InspectorCache(str(path)).get("x") is None
    assert any(".corrupt-" in p.name for p in tmp_path.iterdir())
    fresh = InspectorCache(str(tmp_path / "sub" / "new.json"))
    fresh.set("a", {"b": 1})
    assert InspectorCache(str(tmp_path / "sub" / "new.json")).get("a") == {"b": 1}


def test_cache_concurrent_writers_use_unique_temp_files(tmp_path: Path) -> None:
    import threading

    c = InspectorCache(str(tmp_path / "c.json"))
    threads = [threading.Thread(target=c.set, args=(f"k{i}", i)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(json.loads((tmp_path / "c.json").read_text(encoding="utf-8"))) == 20
    assert [p.name for p in tmp_path.iterdir()] == ["c.json"]


def test_send_sync_prefers_requesting_client(monkeypatch: pytest.MonkeyPatch) -> None:
    from model_loaders import _comfy

    sent: list[tuple[str, object, object]] = []

    class Inst:
        client_id = "last"

        def send_sync(self, event: str, data: object, sid: object) -> None:
            sent.append((event, data, sid))

    monkeypatch.setattr(_comfy, "prompt_server", lambda: Inst())
    _comfy.send_sync("e", {}, "mine")
    _comfy.send_sync("e", {})
    assert [s[2] for s in sent] == ["mine", "last"]
