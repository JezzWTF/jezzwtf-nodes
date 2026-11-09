"""V2 card PNG baker and workflow PNG baker (spec sections 5 and 6)."""

from __future__ import annotations

import json
import os
from typing import Callable, TypedDict

from PIL import Image

from .card_v2 import CardError, card_info, parse_card_text
from .common import (
    CATEGORY_CARDS,
    JSONDict,
    JSONTextError,
    JSONValue,
    frame_to_uint8,
    parse_json_text,
    safe_name,
    safe_prefix_path,
)
from .png_chunks import decode_chara, encode_chara, read_png_text_from_file, save_png_with_text


class SavedImage(TypedDict):
    filename: str
    subfolder: str
    type: str


# --------------------------------------------------------------------------- shared saving


def save_batch(images: object, prefix: str, chunks: dict[str, str],
               verify: Callable[[str], None], to_characters: bool = False) -> tuple[list[str], list[SavedImage]]:
    """Save every frame of an IMAGE batch as a numbered PNG carrying `chunks`.

    `to_characters` writes into input/characters instead of the output folder, so the
    Character Chat dropdown lists the card straight away.
    """
    import folder_paths  # type: ignore[import-not-found]

    shape = tuple(getattr(images, "shape", ()))
    if len(shape) == 3:
        images = images[None, ...]  # type: ignore[index]
        shape = (1, *shape)
    if len(shape) != 4 or shape[0] == 0:
        raise ValueError("Expected an IMAGE batch with at least one frame.")
    if to_characters:
        out_dir = os.path.join(folder_paths.get_input_directory(), CHARACTERS_FOLDER)
        os.makedirs(out_dir, exist_ok=True)
        kind = "input"
    else:
        out_dir = folder_paths.get_output_directory()
        kind = "output"
    full_folder, fname, counter, subfolder, _ = folder_paths.get_save_image_path(prefix, out_dir, shape[2], shape[1])
    if to_characters:
        subfolder = "/".join(p for p in (CHARACTERS_FOLDER, subfolder) if p)
    os.makedirs(full_folder, exist_ok=True)
    paths: list[str] = []
    saved: list[SavedImage] = []
    for i in range(shape[0]):
        img = Image.fromarray(frame_to_uint8(images[i]))  # type: ignore[index]
        file = f"{fname}_{counter:05}_.png"
        path = os.path.join(full_folder, file)
        save_png_with_text(img, path, chunks, compress_level=4)
        verify(path)
        paths.append(os.path.abspath(path))
        saved.append({"filename": file, "subfolder": subfolder, "type": kind})
        counter += 1
    return paths, saved


CHARACTERS_FOLDER = "characters"
SAVE_TO_CHARACTERS = "characters folder"
SAVE_TO_OUTPUT = "output folder"


# --------------------------------------------------------------------------- V2 baker


def card_prefix(prefix: str, name: str) -> str:
    """Substitute %name% and sanitise every path part (the original only sanitised the name)."""
    return safe_prefix_path((prefix or "").replace("%name%", safe_name(name)), empty="card")


def verify_chara(path: str, card: JSONDict) -> None:
    chunks = read_png_text_from_file(path)
    raw = chunks.get("chara")
    if raw is None:
        raise RuntimeError(f"Verification failed: no `chara` chunk in {path}")
    if decode_chara(raw) != card:
        raise RuntimeError(f"Verification failed: the `chara` chunk in {path} does not match the card")


class JWTFV2PNGBaker:
    CATEGORY = CATEGORY_CARDS
    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("saved_path", "character_name")
    FUNCTION = "bake"
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, dict[str, tuple]]:
        return {
            "required": {
                "image": ("IMAGE",),
                "json_text": ("STRING", {"forceInput": True, "multiline": True}),
                "filename_prefix": ("STRING", {"default": "V2_cards/%name%"}),
                "fill_missing_fields": ("BOOLEAN", {"default": True, "label_on": "fill missing V2 fields",
                                                    "label_off": "keep JSON exactly as pasted"}),
            },
            "optional": {
                "save_to": ([SAVE_TO_CHARACTERS, SAVE_TO_OUTPUT], {"default": SAVE_TO_CHARACTERS}),
            },
        }

    def bake(self, image: object, json_text: str, filename_prefix: str, fill_missing_fields: bool,
             save_to: str = SAVE_TO_CHARACTERS) -> dict[str, object]:
        try:
            card, notes = parse_card_text(json_text, bool(fill_missing_fields))
        except (CardError, JSONTextError) as exc:
            raise ValueError(f"V2 PNG Baker: {exc}") from exc
        data = card["data"]
        assert isinstance(data, dict)
        name = str(data.get("name") or "")
        b64 = encode_chara(card)
        paths, saved = save_batch(image, card_prefix(filename_prefix, name), {"chara": b64},
                                  lambda p: verify_chara(p, card), to_characters=save_to != SAVE_TO_OUTPUT)
        info = card_info(card, len(b64), notes)
        return {"ui": {"card_preview": saved, "card_info": [info]}, "result": ("\n".join(paths), name)}


# --------------------------------------------------------------------------- workflow baker


def is_workflow(value: object) -> bool:
    return isinstance(value, dict) and isinstance(value.get("nodes"), list) and "links" in value


def is_api_prompt(value: object) -> bool:
    return isinstance(value, dict) and bool(value) and all(
        isinstance(v, dict) and "class_type" in v for v in value.values()
    )


def _unstring(value: JSONValue, layers: int) -> JSONValue:
    for _ in range(layers):
        if not isinstance(value, str):
            break
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            break
    return value


def classify_workflow(text: str) -> tuple[JSONDict | None, JSONDict | None]:
    """Return (workflow, api_prompt); at least one is set, otherwise raise ValueError."""
    obj = _unstring(parse_json_text(text), 3)
    if not isinstance(obj, dict):
        raise ValueError(f"The workflow JSON must be an object, got {type(obj).__name__}.")
    if is_workflow(obj):
        return obj, None
    if is_api_prompt(obj):
        return None, obj
    workflow = _unstring(obj.get("workflow"), 3)
    prompt = _unstring(obj.get("prompt"), 3)
    wf = workflow if is_workflow(workflow) else None
    pr = prompt if is_api_prompt(prompt) else None
    if wf is None and pr is None:
        keys = ", ".join(list(obj)[:12]) or "(none)"
        raise ValueError(f"This JSON is neither a ComfyUI workflow nor an API prompt. Top-level keys: {keys}")
    return wf, pr  # type: ignore[return-value]


def workflow_chunks(workflow: JSONDict | None, prompt: JSONDict | None) -> dict[str, str]:
    chunks: dict[str, str] = {}
    if workflow is not None:
        chunks["workflow"] = json.dumps(workflow)
    if prompt is not None:
        chunks["prompt"] = json.dumps(prompt)
    return chunks


def verify_workflow(path: str, workflow: JSONDict | None, prompt: JSONDict | None) -> None:
    chunks = read_png_text_from_file(path)
    for key, expected in (("workflow", workflow), ("prompt", prompt)):
        if expected is None:
            continue
        raw = chunks.get(key)
        if raw is None or json.loads(raw) != expected:
            raise RuntimeError(f"Verification failed: the `{key}` chunk in {path} does not match")


class JWTFWorkflowPNGBaker:
    CATEGORY = CATEGORY_CARDS
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("saved_path",)
    FUNCTION = "bake"
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, dict[str, tuple]]:
        return {
            "required": {
                "image": ("IMAGE",),
                "json_text": ("STRING", {"forceInput": True, "multiline": True}),
                "filename_prefix": ("STRING", {"default": "Workflow_PNG/workflow"}),
            }
        }

    def bake(self, image: object, json_text: str, filename_prefix: str) -> dict[str, object]:
        workflow, prompt = classify_workflow(json_text)
        paths, saved = save_batch(image, safe_prefix_path(filename_prefix), workflow_chunks(workflow, prompt),
                                  lambda p: verify_workflow(p, workflow, prompt))
        return {"ui": {"images": saved}, "result": ("\n".join(paths),)}
