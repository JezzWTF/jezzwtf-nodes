"""Character Chat node and its HTTP routes (spec section 7)."""

from __future__ import annotations

import asyncio
import base64
import inspect
import json
import os
import time
from typing import Mapping

from PIL import Image

from io import BytesIO

from comfy_api.latest import io

from .character import (
    PLACEHOLDER,
    CardReadError,
    LoadedCard,
    Message,
    NormalizedCard,
    apply_turn,
    build_prompt,
    card_choices,
    card_info,
    chat_log,
    clean_reply,
    dedupe_dirs,
    load_card,
    parse_history,
    resolve_card_path,
    sampling_kwargs,
    substitute,
    video_frame_indices,
)
from .common import MAX_IMAGES, linspace_indices, pil_to_tensor, safe_name

TAG = "[JezzWTF Character Chat]"
MTP_MODES = ["auto", "off", "2", "3", "4", "5", "tree2s1", "tree2s2", "tree3s1", "tree4s1m8"]
REFMOD_FOLDER_KEYS = ("refmod", "refmods", "h3_refmod", "minimax_refmod", "reference", "references")
REFMOD_ENV_VARS = ("JEZZWTF_REFMOD_DIR",)
_audio_note_shown = False


# --------------------------------------------------------------------------- folders


def card_dir() -> str:
    import folder_paths  # type: ignore[import-not-found]

    return os.path.join(folder_paths.get_input_directory(), "characters")


def refmod_dirs() -> list[str]:
    dirs: list[str] = []
    for var in REFMOD_ENV_VARS:
        dirs.extend(p for p in os.environ.get(var, "").split(os.pathsep) if p.strip())
    try:
        import folder_paths  # type: ignore[import-not-found]

        for key in REFMOD_FOLDER_KEYS:
            try:
                dirs.extend(folder_paths.get_folder_paths(key))
            except Exception:  # noqa: BLE001 - key not registered
                continue
        dirs.append(os.path.join(folder_paths.models_dir, "refmods"))
    except ImportError:
        pass
    return dedupe_dirs(dirs)


def list_choices() -> list[str]:
    try:
        return card_choices(card_dir(), refmod_dirs())
    except Exception as exc:  # noqa: BLE001 - never break INPUT_TYPES
        print(f"{TAG} could not list cards: {exc}")
        return [PLACEHOLDER]


def explicit_roots() -> list[str]:
    """Folders a node-level `card_path` may point into: ComfyUI input, output and RefMod folders."""
    import folder_paths  # type: ignore[import-not-found]

    return dedupe_dirs([folder_paths.get_input_directory(), folder_paths.get_output_directory(), *refmod_dirs()])


def load_selected(character: str | None, card_path: str | None = None, allow_explicit: bool = False) -> LoadedCard:
    """Load the chosen card. `card_path` is honoured only when `allow_explicit` (the node, never the routes)."""
    roots = explicit_roots() if allow_explicit else None
    return load_card(resolve_card_path(character, card_path, card_dir(), refmod_dirs(), roots))


# --------------------------------------------------------------------------- media


def avatar_tensor(loaded: LoadedCard) -> "torch.Tensor":  # noqa: F821
    data = loaded["avatar_png"]
    if data and not loaded["path"].lower().endswith(".json"):
        try:
            with Image.open(BytesIO(data)) as img:
                return pil_to_tensor(img.convert("RGB"))
        except Exception as exc:  # noqa: BLE001 - fall back to the placeholder
            print(f"{TAG} avatar could not be read: {exc}")
    return pil_to_tensor(Image.new("RGB", (256, 256), (40, 40, 40)))


def write_chat_files(history: list[Message], char: str, user: str) -> str:
    """Write a chat to output/chats as a readable .txt plus a .json; returns the .txt path."""
    import folder_paths  # type: ignore[import-not-found]

    folder = os.path.join(folder_paths.get_output_directory(), "chats")
    os.makedirs(folder, exist_ok=True)
    stem = f"{safe_name(char)}_{time.strftime('%Y%m%d_%H%M%S')}"
    txt = os.path.join(folder, stem + ".txt")
    with open(txt, "w", encoding="utf-8") as fh:
        fh.write(chat_log(history, char, user) + "\n")
    with open(os.path.join(folder, stem + ".json"), "w", encoding="utf-8") as fh:
        json.dump({"character": char, "user": user, "messages": history}, fh, ensure_ascii=False, indent=2)
    return os.path.abspath(txt)


def avatar_thumbnail(loaded: LoadedCard, size: int = 96) -> str:
    """Small JPEG data URL of the card avatar, or "" when there is none."""
    data = loaded["avatar_png"]
    if not data or loaded["path"].lower().endswith(".json"):
        return ""
    try:
        with Image.open(BytesIO(data)) as img:
            thumb = img.convert("RGB")
            thumb.thumbnail((size, size))
            buf = BytesIO()
            thumb.save(buf, "JPEG", quality=80)
    except Exception:  # noqa: BLE001 - header just shows no avatar
        return ""
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def _subsample(frames: list["torch.Tensor"], cap: int) -> list["torch.Tensor"]:  # noqa: F821
    if len(frames) <= cap:
        return frames
    return [frames[i] for i in linspace_indices(len(frames), cap)]


def gather_images(image: object, video: object, max_frames: int) -> tuple[list["torch.Tensor"], int]:  # noqa: F821
    """Return ([1,H,W,C] frames: image batch first, then sampled video frames), video frame count.

    At most MAX_IMAGES frames are returned: an IMAGE batch is evenly subsampled (to half the cap when a
    video is wired too), and video frames fill whatever budget is left.
    """
    frames: list["torch.Tensor"] = []  # noqa: F821
    if image is not None and len(getattr(image, "shape", ())) == 4:
        batch = [image[i : i + 1] for i in range(image.shape[0])]  # type: ignore[index,attr-defined]
        frames.extend(_subsample(batch, MAX_IMAGES // 2 if video is not None else MAX_IMAGES))
        if len(batch) > len(frames):
            print(f"{TAG} {len(batch)} images wired in; sending an evenly spaced {len(frames)}.")
    n_video = 0
    if video is not None:
        clip_frames = None
        fps = 24.0
        if len(getattr(video, "shape", ())) == 4:
            clip_frames = video
        elif callable(getattr(video, "get_components", None)):
            comp = video.get_components()  # type: ignore[attr-defined]
            clip_frames = getattr(comp, "images", None)
            try:
                fps = float(getattr(comp, "frame_rate", 24) or 24)
            except (TypeError, ValueError):
                fps = 24.0
        if clip_frames is not None and len(getattr(clip_frames, "shape", ())) == 4:
            budget = max(0, MAX_IMAGES - len(frames))
            for i in video_frame_indices(int(clip_frames.shape[0]), fps, min(max_frames, budget)):
                frames.append(clip_frames[i : i + 1])
                n_video += 1
    return frames, n_video


# --------------------------------------------------------------------------- generate kwargs


def supported_generate_kwargs(generate: object, kwargs: Mapping[str, object]) -> dict[str, object]:
    """Keep only the kwargs `generate` accepts (ComfyUI's CLIP.generate has no `mtp` in many versions)."""
    try:
        params = inspect.signature(generate).parameters  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return dict(kwargs)
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()):
        return dict(kwargs)
    return {k: v for k, v in kwargs.items() if k in params}


# --------------------------------------------------------------------------- node


class JWTFCharacterChat(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="JWTFCharacterChat",
            display_name='Character Chat',
            category='JezzWTF/LLM',
            inputs=[
                io.Clip.Input("clip"),
                io.Combo.Input("character", options=list_choices()),
                io.String.Input("user_name", default='User'),
                io.Int.Input("max_length", default=512, min=1, max=32768),
                io.Float.Input("temperature", default=0.7, min=0.01, max=2.0, step=0.01),
                io.Float.Input("top_p", default=0.95, min=0.0, max=1.0, step=0.01),
                io.Int.Input("top_k", default=64, min=0, max=1000),
                io.Float.Input("min_p", default=0.05, min=0.0, max=1.0, step=0.01),
                io.Float.Input("repetition_penalty", default=1.05, min=0.0, max=5.0, step=0.01),
                io.Int.Input("seed", default=0, min=0, max=18446744073709551615, control_after_generate=True),
                io.Boolean.Input("thinking", default=False),
                io.Int.Input("context_messages", default=40, min=2, max=400),
                io.String.Input("card_path", default='', optional=True),
                io.String.Input("action", default='none', optional=True),
                io.String.Input("user_message", default='', optional=True),
                io.String.Input("history_json", default='[]', optional=True),
                io.Float.Input("presence_penalty", default=0.0, min=0.0, max=5.0, step=0.01, optional=True),
                io.Combo.Input("mtp", options=MTP_MODES, default='auto', optional=True),
                io.Int.Input("video_max_frames", default=8, min=1, max=64, optional=True),
                io.Image.Input("image", optional=True),
                io.Audio.Input("audio", optional=True),
                io.Video.Input("video", optional=True),
                io.String.Input("system_prompt", multiline=True, optional=True, force_input=True),
                io.Combo.Input("sampling_mode", options=['on', 'off'], default='on', optional=True),
            ],
            outputs=[
                io.String.Output("reply"),
                io.String.Output("chat_log"),
                io.String.Output("character_name"),
                io.String.Output("description"),
                io.Image.Output("avatar"),
                io.String.Output("history_json"),
            ],
            is_output_node=True,
        )

    @classmethod
    def execute(cls,
        clip: object,
        character: str,
        user_name: str,
        max_length: int,
        temperature: float,
        top_p: float,
        top_k: int,
        min_p: float,
        repetition_penalty: float,
        seed: int,
        thinking: bool,
        context_messages: int,
        card_path: str = "",
        action: str = "none",
        user_message: str = "",
        history_json: str = "[]",
        presence_penalty: float = 0.0,
        mtp: str = "auto",
        video_max_frames: int = 8,
        image: object = None,
        audio: Mapping[str, object] | None = None,
        video: object = None,
        system_prompt: str | None = None,
        sampling_mode: str = "on",
    ) -> io.NodeOutput:
        try:
            loaded = load_selected(character, card_path, allow_explicit=True)
        except CardReadError as exc:
            raise ValueError(f"Character Chat: {exc}") from exc
        card = loaded["card"]
        char = card["name"]
        user = (user_name or "").strip() or "User"
        greeting = substitute(card["first_mes"], char, user)
        history, generate = apply_turn(parse_history(history_json), action, user_message, greeting)

        reply = ""
        stats: dict[str, float | int] | None = None
        if generate:
            reply, stats = cls._generate(clip, card, user, history, context_messages, thinking, image, audio,
                                          video, video_max_frames, system_prompt, sampling_mode, max_length,
                                          temperature, top_k, top_p, min_p, repetition_penalty,
                                          presence_penalty, seed, mtp)
            history.append({"role": "assistant", "content": reply})
        elif history and history[-1]["role"] == "assistant":
            reply = history[-1]["content"]

        history_out = json.dumps(history, ensure_ascii=False)
        payload = json.dumps({"history": history, "reply": reply, "generated": generate, "stats": stats,
                              "card": {**card_info(loaded, user), "avatar": avatar_thumbnail(loaded)}},
                             ensure_ascii=False)
        return io.NodeOutput(reply, chat_log(history, char, user), char, substitute(card["description"], char, user), avatar_tensor(loaded), history_out, ui={"jwtf_chat": [payload]})

    @classmethod
    def _generate(cls, clip: object, card: NormalizedCard, user: str, history: list[Message],
                  context_messages: int, thinking: bool, image: object, audio: Mapping[str, object] | None,
                  video: object, video_max_frames: int, system_prompt: str | None, sampling_mode: str,
                  max_length: int, temperature: float, top_k: int, top_p: float, min_p: float,
                  repetition_penalty: float, presence_penalty: float, seed: int,
                  mtp: str) -> tuple[str, dict[str, float | int]]:
        import torch

        global _audio_note_shown
        frames, n_video = gather_images(image, video, int(video_max_frames))
        prompt = build_prompt(card, user, history, int(context_messages), len(frames), n_video, bool(thinking),
                              system_prompt)
        tok_kwargs: dict[str, object] = {"skip_template": True, "min_length": 1, "thinking": bool(thinking),
                                         "video": None, "audio": audio, "system_prompt": ""}
        if audio is not None and not _audio_note_shown:
            print(f"{TAG} audio input only works with models whose tokenizer supports audio.")
            _audio_note_shown = True
        if frames:
            shapes = {tuple(f.shape) for f in frames}
            if len(shapes) == 1:
                tok_kwargs["image"] = torch.cat(frames, dim=0)
            else:
                tok_kwargs["image"] = None
                tok_kwargs["images"] = frames
        else:
            tok_kwargs["image"] = None
        tokens = clip.tokenize(prompt, **tok_kwargs)  # type: ignore[attr-defined]
        kwargs = sampling_kwargs(sampling_mode, max_length, temperature, top_k, top_p, min_p,
                                 repetition_penalty, presence_penalty, seed, mtp)
        generate = clip.generate  # type: ignore[attr-defined]
        accepted = supported_generate_kwargs(generate, kwargs)
        for dropped in sorted(set(kwargs) - set(accepted)):
            if dropped == "mtp" and kwargs["mtp"] is True:
                continue  # "auto" on a ComfyUI without MTP: silently nothing to do
            print(f"{TAG} this ComfyUI's CLIP.generate has no '{dropped}' option; ignoring it.")
        t0 = time.time()
        try:
            ids = generate(tokens, **accepted)
        except (KeyError, TypeError):
            if "mtp" not in accepted or not isinstance(accepted["mtp"], str):
                raise
            print(f"{TAG} this ComfyUI does not support mtp={accepted['mtp']!r}; retrying with mtp=True")
            accepted["mtp"] = True
            ids = generate(tokens, **accepted)
        seconds = time.time() - t0
        reply = clean_reply_text(clip.decode(ids), card["name"])  # type: ignore[attr-defined]
        try:
            n_tokens = len(ids) or 0  # type: ignore[arg-type]
        except TypeError:
            n_tokens = 0
        return reply or "...", {"tokens": n_tokens, "seconds": round(seconds, 2), "max_length": int(max_length)}


def clean_reply_text(decoded: object, char: str) -> str:
    if isinstance(decoded, (list, tuple)):
        decoded = decoded[0] if decoded else ""
    return clean_reply(str(decoded), char)


# --------------------------------------------------------------------------- routes


def register(routes: object) -> None:
    from aiohttp import web

    async def card_list(_request: web.Request) -> web.Response:
        cards = await asyncio.to_thread(list_choices)
        return web.json_response({"cards": cards})

    async def info(request: web.Request) -> web.Response:
        q = request.query
        try:
            loaded = await asyncio.to_thread(load_selected, q.get("character"))
        except (CardReadError, OSError) as exc:
            return web.json_response({"error": str(exc)}, status=400)
        except Exception as exc:  # noqa: BLE001 - report as JSON instead of an opaque 500
            print(f"{TAG} card info failed: {exc!r}")
            return web.json_response({"error": f"{type(exc).__name__}: {exc}"}, status=500)
        user = (q.get("user") or "").strip() or "User"
        return web.json_response(card_info(loaded, user))

    async def save_chat(request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except ValueError:
            return web.json_response({"error": "Body must be JSON."}, status=400)
        if not isinstance(body, dict):
            return web.json_response({"error": "Body must be a JSON object."}, status=400)
        try:
            history = parse_history(json.dumps(body.get("history", [])))
        except (TypeError, ValueError):
            history = []
        if not history or len(history) > 5000:
            return web.json_response({"error": "There is no chat to save."}, status=400)
        char = str(body.get("character_name") or "chat")[:80]
        user = (str(body.get("user_name") or "").strip() or "User")[:80]
        path = await asyncio.to_thread(write_chat_files, history, char, user)
        return web.json_response({"saved": path})

    async def avatar(request: web.Request) -> web.StreamResponse:
        q = request.query
        try:
            loaded = await asyncio.to_thread(load_selected, q.get("character"))
        except Exception:  # noqa: BLE001 - no avatar for any unreadable card
            return web.Response(status=404)
        if loaded["source"] == "card" and loaded["path"].lower().endswith(".png"):
            return web.FileResponse(loaded["path"], headers={"Cache-Control": "no-cache"})
        if loaded["source"] == "refmod" and loaded["avatar_png"]:
            return web.Response(body=loaded["avatar_png"], content_type="image/png",
                                headers={"Cache-Control": "no-cache"})
        return web.Response(status=404)

    routes.get("/jezzwtf/character/list")(card_list)  # type: ignore[attr-defined]
    routes.post("/jezzwtf/character/save_chat")(save_chat)  # type: ignore[attr-defined]
    routes.get("/jezzwtf/character/info")(info)  # type: ignore[attr-defined]
    routes.get("/jezzwtf/character/avatar")(avatar)  # type: ignore[attr-defined]


NODES = [JWTFCharacterChat]
