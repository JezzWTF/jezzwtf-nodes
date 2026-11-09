"""LM Studio (OpenAI-compatible) bridge and its prompt box (spec sections 1 and 2)."""

from __future__ import annotations

import base64
import io
import json
import os
import queue
import threading
import time
import wave
from urllib.parse import urlsplit
from typing import Callable, Iterable, Iterator, Mapping, TypedDict

import numpy as np
from PIL import Image

from .common import (
    ANY,
    CATEGORY_LLM,
    JSONDict,
    JSONValue,
    MAX_IMAGES,
    encode_jpeg_b64,
    folder_for_type,
    frame_to_pil,
    linspace_indices,
    send_event,
)

EVENT = "jezzwtf.lmstudio.progress"
DEFAULT_URL = "http://127.0.0.1:1234"
DEFAULT_MODEL = "local-model"
DEFAULT_SYSTEM = "You are a helpful assistant. Answer clearly and concisely."
TAG = "[JezzWTF LM Studio]"
TAIL = 240
REQUEST_DEADLINE = 900.0  # seconds a single completion may take in total
POLL_INTERVAL = 0.25


class MediaCounts(TypedDict):
    image: int
    video: int
    audio: int


# --------------------------------------------------------------------------- inputs


def resolve_user_text(prompt_override: str | None, generate_prompt: str | None) -> str:
    override = (prompt_override or "").strip()
    return override if override else (generate_prompt or "")


def to_int(value: object, default: int) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError, OverflowError):
        return default


def max_side_of(image_size: object) -> int:
    return to_int(image_size, 1024) or 1024


# --------------------------------------------------------------------------- parts


def image_part(b64_jpeg: str) -> JSONDict:
    return {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_jpeg}"}}


def text_part(text: str) -> JSONDict:
    return {"type": "text", "text": text}


def audio_part(b64_wav: str) -> JSONDict:
    return {"type": "input_audio", "input_audio": {"data": b64_wav, "format": "wav"}}


def image_batch_b64(image: object, max_side: int) -> list[str]:
    """IMAGE tensor `[B,H,W,C]` or `[H,W,C]` -> one base64 JPEG per frame (at most MAX_IMAGES)."""
    shape = tuple(getattr(image, "shape", ()))
    if len(shape) == 3:
        image = image[None, ...]  # type: ignore[index]
        shape = (1, *shape)
    if len(shape) != 4:
        raise ValueError(f"expected an IMAGE tensor, got shape {shape}")
    # Sending a whole batch is a payload/VRAM hazard: evenly subsample above MAX_IMAGES.
    picks = list(range(shape[0])) if shape[0] <= MAX_IMAGES else linspace_indices(shape[0], MAX_IMAGES)
    if len(picks) < shape[0]:
        print(f"{TAG} {shape[0]} images wired in; sending an evenly spaced {len(picks)}.")
    return [encode_jpeg_b64(frame_to_pil(image[i]), max_side) for i in picks]  # type: ignore[index]


def wav_bytes(waveform: np.ndarray, sample_rate: int) -> bytes:
    """`[C,N]` float waveform -> 16-bit PCM WAV bytes.

    Uses `soundfile` when installed, otherwise the stdlib `wave` writer (same output).
    """
    data = np.asarray(waveform, dtype=np.float32)
    if data.ndim == 1:
        data = data[None, :]
    frames = data.T  # [N, C]
    buf = io.BytesIO()
    try:
        import soundfile as sf  # type: ignore[import-not-found]

        sf.write(buf, frames, sample_rate, format="WAV", subtype="PCM_16")
        return buf.getvalue()
    except ImportError:
        pass
    pcm = (np.clip(frames, -1.0, 1.0) * 32767.0).round().astype("<i2")
    with wave.open(buf, "wb") as w:
        w.setnchannels(int(frames.shape[1]))
        w.setsampwidth(2)
        w.setframerate(int(sample_rate))
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


def audio_b64(audio: Mapping[str, object]) -> str:
    wf = audio.get("waveform")
    if wf is None:
        raise ValueError("audio has no waveform")
    detach = getattr(wf, "detach", None)
    arr = detach().cpu().float().numpy() if callable(detach) else np.asarray(wf)  # type: ignore[attr-defined]
    if arr.ndim == 3:
        arr = arr[0]
    sr = to_int(audio.get("sample_rate"), 22050) or 22050
    return base64.b64encode(wav_bytes(arr, sr)).decode("ascii")


# --------------------------------------------------------------------------- video


def _resolve_video_path(video: object) -> str:
    if isinstance(video, str):
        path = video.strip().strip('"')
        if os.path.isabs(path) and os.path.exists(path):
            return path
        return os.path.join(folder_for_type("input"), path)
    if isinstance(video, Mapping):
        filename = str(video.get("filename") or video.get("name") or "")
        if not filename:
            raise ValueError("video dict has no filename")
        if os.path.isabs(filename) and os.path.exists(filename):
            return filename
        base = folder_for_type(str(video.get("type") or "temp"), default="temp")
        return os.path.join(base, str(video.get("subfolder") or ""), filename)
    raise ValueError(f"unsupported video input: {type(video).__name__}")


def _decode_video_file(path: str, count: int, max_side: int) -> list[str]:
    try:
        import cv2  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError(
            "opencv-python is not installed, so video files cannot be decoded. "
            "Wire an IMAGE batch (for example from a video loader) into `video` instead."
        ) from exc
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise RuntimeError(f"could not open video: {path}")
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    wanted = set(linspace_indices(total, count)) if total > 1 else None
    out: list[str] = []
    idx = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if wanted is None or idx in wanted:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                out.append(encode_jpeg_b64(Image.fromarray(rgb), max_side))
            idx += 1
    finally:
        cap.release()
    if len(out) > count:
        out = [out[i] for i in linspace_indices(len(out), count)]
    if not out:
        raise RuntimeError(f"no frames could be read from {path}")
    return out


def video_frames_b64(video: object, count: int, max_side: int) -> list[str]:
    """Sample up to `count` frames from any supported video input (spec 1.3)."""
    if isinstance(video, list) and video:
        video = video[0]
    get_components = getattr(video, "get_components", None)
    if callable(get_components):  # core VIDEO object (extension over the original)
        video = getattr(get_components(), "images")
    shape = tuple(getattr(video, "shape", ()))
    if len(shape) == 4:
        n = shape[0]
        return [
            encode_jpeg_b64(frame_to_pil(video[i]), max_side)  # type: ignore[index]
            for i in linspace_indices(n, min(count, n))
        ]
    return _decode_video_file(_resolve_video_path(video), count, max_side)


def embedded_image_b64(raw: str, max_side: int) -> str:
    info = json.loads(raw)
    if not isinstance(info, dict):
        raise ValueError("embedded_image is not a JSON object")
    name = str(info.get("name") or info.get("filename") or "")
    if not name:
        raise ValueError("embedded_image has no file name")
    base = os.path.abspath(folder_for_type(str(info.get("type") or "input")))
    path = os.path.abspath(os.path.join(base, str(info.get("subfolder") or ""), name))
    if os.path.commonpath([base, path]) != base:
        raise ValueError("embedded_image points outside the ComfyUI folders")
    with Image.open(path) as img:
        return encode_jpeg_b64(img.convert("RGB"), max_side)


# --------------------------------------------------------------------------- payload


def build_messages(system_prompt: str, parts: list[JSONDict], user_text: str) -> list[JSONDict]:
    messages: list[JSONDict] = []
    if (system_prompt or "").strip():
        messages.append({"role": "system", "content": system_prompt})
    content: JSONValue = parts if len(parts) > 1 else user_text  # type: ignore[assignment]
    messages.append({"role": "user", "content": content})
    return messages


def build_payload(
    model_name: str,
    messages: list[JSONDict],
    temperature: float,
    top_p: float,
    stream: bool,
    max_tokens: int,
    seed: int,
) -> JSONDict:
    payload: JSONDict = {
        "model": (model_name or "").strip() or DEFAULT_MODEL,
        "messages": messages,  # type: ignore[dict-item]
        "temperature": float(temperature),
        "top_p": float(top_p),
        "stream": bool(stream),
    }
    if max_tokens > 0:
        payload["max_tokens"] = int(max_tokens)
    if seed > 0:
        payload["seed"] = int(seed)
    return payload


def model_ids(data: object) -> list[str]:
    """Extract model ids from an OpenAI `/v1/models` response."""
    items = data.get("data") if isinstance(data, dict) else data
    out: list[str] = []
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict) and isinstance(item.get("id"), str):
                out.append(item["id"])
            elif isinstance(item, str):
                out.append(item)
    return out


# --------------------------------------------------------------------------- HTTP


def _http_post(url: str, payload: JSONDict, stream: bool) -> Iterator[str]:
    """POST JSON and yield the response body line by line (decoded)."""
    body = json.dumps(payload).encode("utf-8")
    try:
        import requests  # type: ignore[import-untyped]
    except ImportError:
        requests = None  # type: ignore[assignment]

    if requests is not None:
        resp = requests.post(url, data=body, headers={"Content-Type": "application/json"},
                             timeout=(10, 600), stream=stream)
        try:
            if resp.status_code != 200:
                raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:300]}")
            if not stream:
                yield resp.content.decode("utf-8", "replace")
                return
            for line in resp.iter_lines():
                yield line.decode("utf-8", "replace") if isinstance(line, bytes) else str(line)
        finally:
            resp.close()
        return

    import urllib.error
    import urllib.request

    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:  # noqa: S310 - user-configured local server
            if not stream:
                yield resp.read().decode("utf-8", "replace")
                return
            for raw in resp:
                yield raw.decode("utf-8", "replace").rstrip("\r\n")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc


def iter_sse_chunks(lines: Iterable[str]) -> Iterator[JSONDict]:
    """Parse `data:` lines of an SSE stream into JSON chunks until `[DONE]`."""
    for line in lines:
        line = line.strip()
        if not line or not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            return
        try:
            chunk = json.loads(data)
        except json.JSONDecodeError:
            continue
        if isinstance(chunk, dict):
            yield chunk


def error_message(data: object) -> str | None:
    """The message of an OpenAI-style `{"error": ...}` body or stream chunk, else None."""
    if not isinstance(data, dict) or "error" not in data:
        return None
    err = data["error"]
    if isinstance(err, dict):
        msg = err.get("message")
        return str(msg) if msg else json.dumps(err)[:300]
    return str(err)[:300] or "unknown error"


def validate_base_url(base: str) -> str:
    """Only plain http(s) servers with a host are allowed (no file:, ftp:, or userinfo)."""
    parts = urlsplit(base)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError("server URL must start with http:// or https://")
    if parts.username or parts.password:
        raise ValueError("server URL must not contain credentials")
    return base


def _delta_text(chunk: JSONDict) -> str:
    try:
        choices = chunk.get("choices")
        if isinstance(choices, list) and choices:
            delta = choices[0].get("delta") if isinstance(choices[0], dict) else None
            if isinstance(delta, dict) and isinstance(delta.get("content"), str):
                return delta["content"]
    except (AttributeError, IndexError):
        pass
    return ""


def _usage_tokens(chunk: Mapping[str, object]) -> int:
    usage = chunk.get("usage")
    if isinstance(usage, dict):
        return to_int(usage.get("completion_tokens"), 0)
    return 0


def _raise_if_interrupted() -> None:
    """Abort when the Cancel button was pressed in ComfyUI (no-op outside ComfyUI)."""
    try:
        import comfy.model_management as mm  # type: ignore[import-not-found]
    except ImportError:
        return
    mm.throw_exception_if_processing_interrupted()


def is_interrupt(exc: BaseException) -> bool:
    return type(exc).__name__ == "InterruptProcessingException"


_END = object()


def _pump(url: str, payload: JSONDict, stream: bool, out: "queue.Queue[object]", cancel: threading.Event) -> None:
    """Worker thread: feed response lines (or the failure, then _END) into `out`."""
    try:
        for line in _http_post(url, payload, stream):
            if cancel.is_set():
                return
            out.put(line)
    except Exception as exc:  # noqa: BLE001 - re-raised on the consumer side
        out.put(exc)
    finally:
        out.put(_END)


def _lines(url: str, payload: JSONDict, stream: bool, deadline: float) -> Iterator[str]:
    """Yield response lines while polling for Cancel and a total deadline."""
    out: "queue.Queue[object]" = queue.Queue()
    cancel = threading.Event()
    worker = threading.Thread(target=_pump, args=(url, payload, stream, out, cancel), daemon=True,
                              name="jezzwtf-lmstudio")
    worker.start()
    t_end = time.monotonic() + deadline
    try:
        while True:
            _raise_if_interrupted()
            if time.monotonic() > t_end:
                raise TimeoutError(f"no complete reply within {int(deadline)}s")
            try:
                item = out.get(timeout=POLL_INTERVAL)
            except queue.Empty:
                continue
            if item is _END:
                return
            if isinstance(item, Exception):
                raise item
            yield str(item)
    finally:
        cancel.set()  # the worker stops (and closes the connection) at its next line or timeout


def run_completion(
    server_url: str,
    payload: JSONDict,
    on_piece: Callable[[str, int], None] | None = None,
    deadline: float = REQUEST_DEADLINE,
) -> tuple[str, int]:
    """Send the request; returns (text, tokens). `on_piece(accumulated, tokens)` per stream chunk.

    Interruptible (Cancel aborts within a fraction of a second), bounded by `deadline`, and raises when the
    server reports an error, even mid-stream, or when the final text is empty.
    """
    url = f"{validate_base_url(server_url.rstrip('/'))}/v1/chat/completions"
    stream = bool(payload.get("stream"))
    lines = _lines(url, payload, stream, deadline)
    if not stream:
        data = json.loads("\n".join(lines))
        msg = error_message(data)
        if msg:
            raise RuntimeError(f"server error: {msg}")
        try:
            text = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"unexpected response: {json.dumps(data)[:300]}") from exc
        if not str(text).strip():
            raise RuntimeError("the model returned an empty reply (0 tokens)")
        return str(text), _usage_tokens(data) if isinstance(data, dict) else 0

    text = ""
    tokens = 0
    reported = 0
    for chunk in iter_sse_chunks(lines):
        msg = error_message(chunk)
        if msg:
            raise RuntimeError(f"server error: {msg}")
        reported = _usage_tokens(chunk) or reported
        piece = _delta_text(chunk)
        if not piece:
            continue
        text += piece
        tokens += 1
        if on_piece is not None:
            on_piece(text, tokens)
    if not text.strip():
        raise RuntimeError("the model returned an empty reply (0 tokens)")
    # Streaming counts chunks; prefer a server-reported usage figure when one arrives.
    return text, reported or tokens


# --------------------------------------------------------------------------- nodes


class JWTFLMStudio:
    CATEGORY = CATEGORY_LLM
    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("RESPONSE", "PROMPT")
    FUNCTION = "run"
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, dict[str, tuple]]:
        return {
            "required": {
                "server_url": ("STRING", {"default": DEFAULT_URL, "multiline": False}),
                "model_name": ("STRING", {"default": DEFAULT_MODEL, "multiline": False}),
                "system_prompt": ("STRING", {"default": DEFAULT_SYSTEM, "multiline": True, "dynamicPrompts": True}),
                "generate_prompt": ("STRING", {"default": "", "multiline": True, "dynamicPrompts": True,
                                               "placeholder": "What should the model do?"}),
                "max_tokens": ("INT", {"default": 512, "min": -1, "max": 65536, "step": 1}),
                "temperature": ("FLOAT", {"default": 0.70, "min": 0.0, "max": 2.0, "step": 0.01}),
                "top_p": ("FLOAT", {"default": 0.95, "min": 0.0, "max": 1.0, "step": 0.01}),
                "stream": ("BOOLEAN", {"default": True}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xFFFFFFFFFFFFFFFF}),
                "image_size": (["1024", "768", "512"], {"default": "1024"}),
                "video_frames": ("INT", {"default": 8, "min": 1, "max": 32}),
            },
            "optional": {
                "image": ("IMAGE",),
                "audio": ("AUDIO",),
                "video": (ANY,),
                "prompt_override": ("STRING", {"forceInput": True}),
                "embedded_image": ("STRING", {"default": ""}),
            },
            "hidden": {"unique_id": "UNIQUE_ID"},
        }

    @classmethod
    def IS_CHANGED(cls, **_kwargs: object) -> float:
        return float("nan")

    def run(
        self,
        server_url: str,
        model_name: str,
        system_prompt: str,
        generate_prompt: str,
        max_tokens: int,
        temperature: float,
        top_p: float,
        stream: bool,
        seed: int,
        image_size: str,
        video_frames: int,
        image: object = None,
        audio: Mapping[str, object] | None = None,
        video: object = None,
        prompt_override: str | None = None,
        embedded_image: str = "",
        unique_id: str | None = None,
    ) -> dict[str, object]:
        node = str(unique_id) if unique_id not in (None, "") else "-1"
        user_text = resolve_user_text(prompt_override, generate_prompt)
        max_side = max_side_of(image_size)
        max_tokens = to_int(max_tokens, 512)
        video_frames = to_int(video_frames, 8)
        seed = to_int(seed, 0)
        base = (server_url or "").strip().rstrip("/") or DEFAULT_URL

        parts: list[JSONDict] = []
        media: MediaCounts = {"image": 0, "video": 0, "audio": 0}

        def attempt(label: str, fn: Callable[[], None]) -> None:
            try:
                fn()
            except Exception as exc:  # noqa: BLE001 - media is optional; log and keep going
                print(f"{TAG} skipped {label}: {exc}")

        def add_embedded() -> None:
            if (embedded_image or "").strip():
                parts.append(image_part(embedded_image_b64(embedded_image, max_side)))
                media["image"] += 1

        def add_images() -> None:
            if image is not None:
                for b64 in image_batch_b64(image, max_side):
                    parts.append(image_part(b64))
                    media["image"] += 1

        def add_video() -> None:
            if video is not None:
                for b64 in video_frames_b64(video, max(1, video_frames), max_side):
                    parts.append(image_part(b64))
                    media["video"] += 1

        def add_audio() -> None:
            if audio is not None:
                parts.append(audio_part(audio_b64(audio)))
                media["audio"] += 1

        attempt("embedded image", add_embedded)
        attempt("image", add_images)
        attempt("video", add_video)
        attempt("audio", add_audio)
        parts.append(text_part(user_text))

        payload = build_payload(model_name, build_messages(system_prompt, parts, user_text),
                                temperature, top_p, stream, max_tokens, seed)
        shown_max = max_tokens if max_tokens > 0 else 0
        send_event(EVENT, {"node": node, "state": "start", "tokens": 0, "max_tokens": shown_max,
                           "media": dict(media), "model": payload["model"]})
        t0 = time.time()

        def on_piece(text: str, tokens: int) -> None:
            send_event(EVENT, {"node": node, "state": "stream", "tokens": tokens,
                               "max_tokens": shown_max, "tail": text[-TAIL:]})

        try:
            response, tokens = run_completion(base, payload, on_piece)
        except Exception as exc:  # noqa: BLE001 - spec: errors are returned, not raised
            if is_interrupt(exc):
                send_event(EVENT, {"node": node, "state": "error", "tokens": 0, "error": "Interrupted",
                                   "elapsed": round(time.time() - t0, 2)})
                raise
            elapsed = round(time.time() - t0, 2)
            message = str(exc)[:300]
            send_event(EVENT, {"node": node, "state": "error", "tokens": 0, "error": message, "elapsed": elapsed})
            err = f"[LM Studio error] Could not get a reply from {base}: {exc}"
            print(f"{TAG} {err}")
            return {"ui": {"text": [err]}, "result": (err, user_text)}

        elapsed = round(time.time() - t0, 2)
        send_event(EVENT, {"node": node, "state": "done", "tokens": tokens, "elapsed": elapsed,
                           "tail": response[-TAIL:]})
        return {"ui": {"text": [response]}, "result": (response, user_text)}


PROMPT_BOX_MODES = ["APPEND", "PREPEND", "REPLACE (local wins)", "PASSTHROUGH (incoming wins)"]


def combine_prompt(mode: str, incoming: str | None, local: str | None, separator: str) -> str:
    inc = incoming or ""
    loc = local or ""
    m = (mode or "").upper()
    if m.startswith("PREPEND"):
        return loc + separator + inc if inc and loc else (loc or inc)
    if m.startswith("REPLACE"):
        return loc or inc
    if m.startswith("PASSTHROUGH"):
        return inc or loc
    return inc + separator + loc if inc and loc else (inc or loc)


class JWTFLMStudioPromptBox:
    CATEGORY = CATEGORY_LLM
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("PROMPT_OUT",)
    FUNCTION = "run"
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, dict[str, tuple]]:
        return {
            "required": {
                "text": ("STRING", {"default": "", "multiline": True, "dynamicPrompts": True}),
                "mode": (PROMPT_BOX_MODES, {"default": "APPEND"}),
                "separator": ("STRING", {"default": "\n\n", "multiline": False}),
            },
            "optional": {"prompt_in": ("STRING", {"forceInput": True})},
        }

    def run(self, text: str, mode: str, separator: str, prompt_in: str | None = None) -> dict[str, object]:
        out = combine_prompt(mode, prompt_in, text, separator if separator is not None else "")
        return {"ui": {"text": [out]}, "result": (out,)}


# --------------------------------------------------------------------------- routes


def register(routes: object) -> None:
    from aiohttp import ClientSession, ClientTimeout, web

    async def models(request: web.Request) -> web.Response:
        base = (request.query.get("base") or "").strip().rstrip("/") or DEFAULT_URL
        try:
            validate_base_url(base)
        except ValueError as exc:
            return web.json_response({"models": [], "error": str(exc)})
        try:
            async with ClientSession(timeout=ClientTimeout(total=5)) as session:
                async with session.get(f"{base}/v1/models", allow_redirects=False) as resp:
                    if resp.status != 200:
                        return web.json_response({"models": [], "error": f"server answered HTTP {resp.status}"})
                    data = await resp.json(content_type=None)
            return web.json_response({"models": model_ids(data)})
        except Exception:  # noqa: BLE001 - never echo upstream error text (probing aid)
            return web.json_response({"models": [], "error": "could not reach the server"})

    routes.get("/jezzwtf/lmstudio/models")(models)  # type: ignore[attr-defined]


__all__ = ["JWTFLMStudio", "JWTFLMStudioPromptBox", "combine_prompt", "register"]
