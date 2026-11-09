"""Character-card reading, lorebook activation and ChatML prompt building (spec section 7).

Pure logic: nothing here imports ComfyUI or torch.
"""

from __future__ import annotations

import base64
import binascii
import json
import math
import os
import re
import struct
from typing import Literal, Mapping, Sequence, TypedDict, Union

from .common import JSONDict, JSONValue, linspace_indices
from .png_chunks import read_text_chunks, sniff_image_kind

CARD_EXTENSIONS = (".png", ".json", ".safetensors")
CARD_HINTS = ("name", "description", "first_mes", "personality", "char_name")
REFMOD_PREFIX = "refmod:"
PLACEHOLDER = "(none - add cards to input/characters)"
NULL_LITERALS = ("none", "null", "undefined")
LORE_BUDGET = 3500
SAFETENSORS_MAX_HEADER = 100 * 1024 * 1024

# RefMod `.safetensors` header keys written by the baker.
META_CARD = "jezzwtf_character_card"
META_SYSTEM = "jezzwtf_character_system_prompt"
META_AVATAR = "jezzwtf_character_avatar_png_b64"
META_NAME = "jezzwtf_character_name"
META_VERSION = "jezzwtf_character_version"


DEFAULT_INSTRUCTION = (
    "This is a fictional chat between {{char}} and {{user}}. Write only {{char}}'s next reply. "
    "Stay in character at all times, keep the voice and details of the character description, "
    "and never write {{user}}'s actions, thoughts or dialogue."
)

Role = Literal["user", "assistant"]
Source = Literal["card", "refmod"]


class Message(TypedDict):
    role: Role
    content: str


class NormalizedCard(TypedDict):
    spec: str
    name: str
    description: str
    personality: str
    scenario: str
    first_mes: str
    mes_example: str
    system_prompt: str
    post_history_instructions: str
    creator_notes: str
    creator: str
    tags: list[str]
    alternate_greetings: list[str]
    character_book: JSONDict | None


class LoadedCard(TypedDict):
    card: NormalizedCard
    source: Source
    path: str
    avatar_png: bytes | None


class CardInfo(TypedDict):
    name: str
    creator: str
    tags: list[str]
    spec: str
    first_mes: str
    alternate_greetings: list[str]
    description: str
    creator_notes: str
    lore_entries: int
    source: Source


class CardReadError(ValueError):
    pass


# --------------------------------------------------------------------------- payloads


def looks_like_card(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    data = value.get("data")
    targets = [value] + ([data] if isinstance(data, dict) else [])
    return any(any(k in t for k in CARD_HINTS) for t in targets)


def decode_payload(text: str) -> JSONDict | None:
    """Decode a card payload: base64 (standard or URL-safe) JSON, or raw JSON."""
    s = (text or "").strip().lstrip("﻿").strip()
    if not s:
        return None
    squashed = re.sub(r"\s+", "", s)
    padded = squashed + "=" * (-len(squashed) % 4)
    candidates: list[str] = []
    for decode in (lambda b: base64.b64decode(b, validate=True), base64.urlsafe_b64decode):
        try:
            candidates.append(decode(padded).decode("utf-8-sig"))
        except (binascii.Error, ValueError, UnicodeDecodeError):
            continue
    candidates.append(s)
    for cand in candidates:
        try:
            value: JSONValue = json.loads(cand)
        except (json.JSONDecodeError, ValueError):
            continue
        for _ in range(2):
            if not isinstance(value, str):
                break
            try:
                value = json.loads(value)
            except (json.JSONDecodeError, ValueError):
                break
        if isinstance(value, dict):
            return value
    return None


def card_from_png(data: bytes, label: str = "file") -> JSONDict:
    kind = sniff_image_kind(data)
    if kind != "PNG":
        hint = f"it is really a {kind} file" if kind != "unknown" else "it is not a PNG at all"
        raise CardReadError(
            f"{label} has a .png name but {hint}. Character cards must be the original PNG "
            "exported by the card app, not a converted or re-saved copy."
        )
    chunks = read_text_chunks(data)
    if not chunks:
        raise CardReadError(
            f"{label} is a PNG with no text chunks, so it carries no card. It was probably "
            "re-saved by an app that strips metadata; download the original card PNG."
        )
    lowered = {k.lower(): v for k, v in reversed(list(chunks.items()))}
    order = [k for k in ("ccv3", "chara") if k in lowered] + [k for k in lowered if k not in ("ccv3", "chara")]
    for key in order:
        parsed = decode_payload(lowered[key])
        if parsed is not None and looks_like_card(parsed):
            return parsed
    raise CardReadError(
        f"{label} has PNG text chunks ({', '.join(chunks)}) but none of them holds a character card."
    )


def read_safetensors_metadata(path: str) -> dict[str, str]:
    """Header-only read of a `.safetensors` file; returns its `__metadata__` strings."""
    with open(path, "rb") as fh:
        head = fh.read(8)
        if len(head) < 8:
            raise CardReadError(f"{os.path.basename(path)} is too short to be a .safetensors file.")
        (n,) = struct.unpack("<Q", head)
        if not 2 <= n <= SAFETENSORS_MAX_HEADER:
            raise CardReadError(f"{os.path.basename(path)} has an invalid .safetensors header length ({n}).")
        raw = fh.read(n)
    if len(raw) < n:
        raise CardReadError(f"{os.path.basename(path)} has a truncated .safetensors header.")
    try:
        header = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CardReadError(f"{os.path.basename(path)} has an unreadable .safetensors header: {exc}") from exc
    if not isinstance(header, dict):
        raise CardReadError(f"{os.path.basename(path)} has a malformed .safetensors header.")
    meta = header.get("__metadata__")
    if not isinstance(meta, dict):
        return {}
    return {str(k): v for k, v in meta.items() if isinstance(v, str)}


def refmod_has_card(path: str) -> bool:
    try:
        return bool(read_safetensors_metadata(path).get(META_CARD, "").strip())
    except (OSError, CardReadError):
        return False


# --------------------------------------------------------------------------- normalisation


def _s(value: object) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    return str(value)


def normalize_card(raw: Mapping[str, object]) -> NormalizedCard:
    """Flatten a V1 / V2 / V3 card into one shape."""
    data = raw.get("data")
    d: Mapping[str, object] = data if isinstance(data, dict) else raw

    def pick(key: str, legacy: str | None = None) -> str:
        v = d.get(key)
        if (v is None or v == "") and legacy:
            v = d.get(legacy)
        return _s(v)

    tags_raw = d.get("tags")
    if isinstance(tags_raw, str):
        tags = [t.strip() for t in tags_raw.split(",") if t.strip()]
    elif isinstance(tags_raw, list):
        tags = [_s(t).strip() for t in tags_raw if _s(t).strip()]
    else:
        tags = []
    alts_raw = d.get("alternate_greetings")
    alts = [a for a in alts_raw if isinstance(a, str) and a.strip()] if isinstance(alts_raw, list) else []
    book = d.get("character_book")
    return {
        "spec": _s(raw.get("spec")) or "chara_card_v1",
        "name": pick("name", "char_name").strip() or "Character",
        "description": pick("description", "char_persona"),
        "personality": pick("personality"),
        "scenario": pick("scenario", "world_scenario"),
        "first_mes": pick("first_mes", "char_greeting"),
        "mes_example": pick("mes_example", "example_dialogue"),
        "system_prompt": pick("system_prompt"),
        "post_history_instructions": pick("post_history_instructions"),
        "creator_notes": pick("creator_notes"),
        "creator": pick("creator"),
        "tags": tags,
        "alternate_greetings": alts,
        "character_book": book if isinstance(book, dict) else None,
    }


def read_json_text(path: str, label: str) -> str:
    """Read a JSON card as text: UTF-8 (with or without BOM), then Windows-1252."""
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
    except OSError as exc:
        raise CardReadError(f"{label} could not be read: {exc.strerror or exc}") from exc
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        pass
    try:
        return raw.decode("cp1252")
    except UnicodeDecodeError as exc:
        raise CardReadError(f"{label} is not valid UTF-8 or Windows-1252 text.") from exc


def load_card(path: str) -> LoadedCard:
    """Read and normalise a `.png`, `.json` or `.safetensors` card file."""
    label = os.path.basename(path)
    ext = os.path.splitext(path)[1].lower()
    if not os.path.isfile(path):
        raise CardReadError(f"Card file not found: {path}")
    if ext == ".png":
        with open(path, "rb") as fh:
            data = fh.read()
        return {"card": normalize_card(card_from_png(data, label)), "source": "card", "path": path,
                "avatar_png": data}
    if ext == ".json":
        parsed = decode_payload(read_json_text(path, label))
        if parsed is None or not looks_like_card(parsed):
            raise CardReadError(f"{label} does not contain a character card JSON object.")
        return {"card": normalize_card(parsed), "source": "card", "path": path, "avatar_png": None}
    if ext == ".safetensors":
        meta = read_safetensors_metadata(path)
        raw_card = meta.get(META_CARD, "")
        parsed = decode_payload(raw_card) if raw_card.strip() else None
        if parsed is None:
            raise CardReadError(f"{label} is a .safetensors file without an embedded character card.")
        card = normalize_card(parsed)
        system = meta.get(META_SYSTEM, "")
        if system.strip():
            card["system_prompt"] = system
        avatar: bytes | None = None
        raw_avatar = meta.get(META_AVATAR, "")
        if raw_avatar.strip():
            try:
                avatar = base64.b64decode(re.sub(r"\s+", "", raw_avatar))
            except (binascii.Error, ValueError):
                avatar = None
        return {"card": card, "source": "refmod", "path": path, "avatar_png": avatar}
    raise CardReadError(f"Unsupported card type '{ext}'. Use .png, .json or .safetensors.")


# --------------------------------------------------------------------------- discovery


def list_card_files(card_dir: str) -> list[str]:
    out: list[str] = []
    if not os.path.isdir(card_dir):
        return out
    for root, _dirs, files in os.walk(card_dir):
        for f in files:
            if f.lower().endswith(CARD_EXTENSIONS):
                out.append(os.path.relpath(os.path.join(root, f), card_dir).replace(os.sep, "/"))
    return sorted(out, key=str.lower)


def dedupe_dirs(dirs: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for d in dirs:
        if not d:
            continue
        key = os.path.normcase(os.path.abspath(d)).lower()
        if key in seen or not os.path.isdir(d):
            continue
        seen.add(key)
        out.append(os.path.abspath(d))
    return out


# (mtime_ns, size) -> has a card; header reads happen once per file version, not per INPUT_TYPES call.
_REFMOD_CARD_CACHE: dict[str, tuple[tuple[int, int], bool]] = {}


def _refmod_has_card_cached(full: str) -> bool:
    try:
        st = os.stat(full)
    except OSError:
        return False
    sig = (st.st_mtime_ns, st.st_size)
    hit = _REFMOD_CARD_CACHE.get(full)
    if hit is not None and hit[0] == sig:
        return hit[1]
    result = refmod_has_card(full)
    _REFMOD_CARD_CACHE[full] = (sig, result)
    return result


def list_refmods(refmod_dirs: Sequence[str]) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    seen_paths: set[str] = set()
    for base in refmod_dirs:
        for root, _dirs, files in os.walk(base):
            for f in files:
                if not f.lower().endswith(".safetensors"):
                    continue
                full = os.path.join(root, f)
                rel = os.path.relpath(full, base).replace(os.sep, "/")
                if rel.lower() in seen:
                    continue
                seen_paths.add(full)
                if not _refmod_has_card_cached(full):
                    continue
                seen.add(rel.lower())
                found.append(rel)
    for stale in [k for k in _REFMOD_CARD_CACHE if k not in seen_paths]:
        del _REFMOD_CARD_CACHE[stale]
    return [REFMOD_PREFIX + r for r in sorted(found, key=str.lower)]


def card_choices(card_dir: str, refmod_dirs: Sequence[str]) -> list[str]:
    return list_card_files(card_dir) + list_refmods(refmod_dirs) or [PLACEHOLDER]


def _inside(base: str, rel: str) -> str | None:
    base_abs = os.path.abspath(base)
    full = os.path.abspath(os.path.join(base_abs, rel))
    try:
        if os.path.commonpath([base_abs, full]) != base_abs:
            return None
    except ValueError:  # different drives on Windows
        return None
    return full


def clean_card_path(card_path: str | None) -> str:
    p = (card_path or "").strip().strip('"').strip("'").strip()
    return "" if p.lower() in NULL_LITERALS else p


_DRIVE_RELATIVE = re.compile(r"^[A-Za-z]:(?![/\\])")


def is_unsafe_explicit_path(path: str) -> bool:
    """UNC / device paths and drive-relative paths are never accepted as card paths."""
    return path.startswith(("\\\\", "//")) or bool(_DRIVE_RELATIVE.match(path))


def _explicit_card_path(explicit: str, roots: Sequence[str]) -> str:
    if is_unsafe_explicit_path(explicit):
        raise CardReadError("card_path must not be a network (UNC) or drive-relative path.")
    candidates = [explicit] if os.path.isabs(explicit) else [os.path.join(r, explicit) for r in roots]
    for cand in candidates:
        real = os.path.realpath(cand)
        for root in roots:
            base = os.path.realpath(root)
            try:
                inside = os.path.commonpath([base, real]) == base
            except ValueError:  # different drives on Windows
                inside = False
            if inside:
                return real
    raise CardReadError("card_path must point inside the ComfyUI input, output or RefMod folders.")


def resolve_card_path(character: str | None, card_path: str | None, card_dir: str,
                      refmod_dirs: Sequence[str], explicit_roots: Sequence[str] | None = None) -> str:
    """Resolve a card file. `explicit_roots` lists the folders `card_path` may point into;
    None (the HTTP routes) means `card_path` is not accepted at all and only `character` is used."""
    explicit = clean_card_path(card_path)
    if explicit and explicit_roots is not None:
        return _explicit_card_path(explicit, explicit_roots)
    choice = (character or "").strip()
    if not choice or choice == PLACEHOLDER or choice.startswith("(none"):
        raise CardReadError("No character selected. Put cards in ComfyUI/input/characters or set card_path.")
    if choice.startswith(REFMOD_PREFIX):
        rel = choice[len(REFMOD_PREFIX):]
        for base in refmod_dirs:
            full = _inside(base, rel)
            if full and os.path.isfile(full):
                return full
        raise CardReadError(f"RefMod not found: {rel}")
    full = _inside(card_dir, choice)
    if full is None:
        raise CardReadError(f"Card path escapes the characters folder: {choice}")
    return full


# --------------------------------------------------------------------------- macros


_COMMENT = re.compile(r"\{\{//.*?\}\}", re.S)
_CHAR = re.compile(r"\{\{\s*char\s*\}\}|<BOT>", re.I)
_USER = re.compile(r"\{\{\s*user\s*\}\}|<USER>", re.I)
_ORIGINAL = re.compile(r"\{\{\s*original\s*\}\}", re.I)


def substitute(text: str, char: str, user: str) -> str:
    s = _COMMENT.sub("", text or "")
    s = _CHAR.sub(lambda _m: char, s)
    s = _USER.sub(lambda _m: user, s)
    return _ORIGINAL.sub("", s)


# --------------------------------------------------------------------------- history


def parse_history(raw: object) -> list[Message]:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw) if raw.strip() else []
        except json.JSONDecodeError:
            return []
    out: list[Message] = []
    if isinstance(raw, list):
        for m in raw:
            if isinstance(m, dict) and m.get("role") in ("user", "assistant") and isinstance(m.get("content"), str):
                out.append({"role": m["role"], "content": m["content"]})
    return out


def apply_turn(history: list[Message], action: str, user_message: str,
               greeting: str) -> tuple[list[Message], bool]:
    """Apply the queued action; returns (history, should_generate)."""
    hist = list(history)
    if not hist and greeting.strip():
        hist.append({"role": "assistant", "content": greeting})
    act = (action or "none").strip().lower()
    if act == "send":
        msg = (user_message or "").strip()
        if msg:
            hist.append({"role": "user", "content": msg})
    elif act == "regenerate":
        while len(hist) > 1 and hist[-1]["role"] == "assistant":
            hist.pop()
    generate = act in ("send", "regenerate") and bool(hist) and hist[-1]["role"] == "user"
    return hist, generate


def chat_log(history: Sequence[Message], char: str, user: str) -> str:
    return "\n\n".join(
        f"{char if m['role'] == 'assistant' else user}: {substitute(m['content'], char, user)}" for m in history
    )


# --------------------------------------------------------------------------- lorebook


_REGEX_KEY = re.compile(r"^/(.+)/([a-z]*)$", re.S)
_REGEX_FLAGS = frozenset("imsgu")
REGEX_MAX_LEN = 200
REGEX_MAX_TEXT = 20000
# A quantified group that itself contains a quantifier, e.g. (a+)+ or (.*)*: catastrophic backtracking.
_NESTED_QUANT = re.compile(r"\((?:[^()\\]|\\.)*[+*](?:[^()\\]|\\.)*\)\s*(?:[+*]|\{\d*,\d*\})")


def key_matches(key: str, text: str, case_sensitive: bool) -> bool:
    k = key.strip()
    if not k:
        return False
    m = _REGEX_KEY.match(k)
    if m and set(m.group(2)) <= _REGEX_FLAGS:
        pattern = m.group(1)
        if len(pattern) > REGEX_MAX_LEN or _NESTED_QUANT.search(pattern):
            return False
        flags = 0
        if "i" in m.group(2) and not case_sensitive:
            flags |= re.I
        if "s" in m.group(2):
            flags |= re.S
        if "m" in m.group(2):
            flags |= re.M
        try:
            return re.search(pattern, text[-REGEX_MAX_TEXT:], flags) is not None
        except re.error:
            return False
    return k in text if case_sensitive else k.lower() in text.lower()


def _num(value: object, default: float) -> float:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)) and math.isfinite(value):
        return float(value)
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return default


def _keys(value: object) -> list[str]:
    if isinstance(value, str):
        return [k for k in (p.strip() for p in value.split(",")) if k]
    if isinstance(value, list):
        return [k for k in value if isinstance(k, str) and k.strip()]
    return []


def book_entries(book: Mapping[str, object] | None) -> list[JSONDict]:
    if not isinstance(book, dict):
        return []
    entries = book.get("entries")
    if isinstance(entries, dict):  # SillyTavern world-info style {"0": {...}}
        entries = list(entries.values())
    return [e for e in entries if isinstance(e, dict)] if isinstance(entries, list) else []


def activate_lorebook(book: Mapping[str, object] | None,
                      history: Sequence[Message]) -> tuple[list[str], list[str]]:
    """Return (before_examples, after_examples) lore contents that trigger on the last 4 messages."""
    scan = "\n".join(m["content"] for m in history[-4:])
    hits: list[tuple[float, float, int, JSONDict]] = []
    for idx, e in enumerate(book_entries(book)):
        if not e.get("enabled", True):
            continue
        content = e.get("content")
        if not isinstance(content, str) or not content.strip():
            continue
        cs = bool(e.get("case_sensitive"))
        hit = bool(e.get("constant")) or any(key_matches(k, scan, cs) for k in _keys(e.get("keys")))
        secondary = _keys(e.get("secondary_keys"))
        if hit and e.get("selective") and secondary:
            hit = any(key_matches(k, scan, cs) for k in secondary)
        if hit:
            hits.append((_num(e.get("insertion_order"), 100), -_num(e.get("priority"), 0), idx, e))
    hits.sort(key=lambda h: (h[0], h[1], h[2]))
    before: list[str] = []
    after: list[str] = []
    used = 0
    for *_rank, e in hits:
        content = str(e["content"])
        if used + len(content) > LORE_BUDGET:
            continue
        used += len(content)
        (after if e.get("position") == "after_char" else before).append(content)
    return before, after


# --------------------------------------------------------------------------- prompt


_START = re.compile(r"<START>", re.I)


def build_system_text(card: NormalizedCard, user: str, history: Sequence[Message],
                      system_override: str | None = None) -> str:
    char = card["name"]

    def sub(t: str) -> str:
        return substitute(t, char, user).strip()

    base = sub(system_override or "") or sub(card["system_prompt"]) or sub(DEFAULT_INSTRUCTION)
    sections = [base]
    if sub(card["description"]):
        sections.append(f"About {char}:\n{sub(card['description'])}")
    if sub(card["personality"]):
        sections.append(f"{char}'s personality: {sub(card['personality'])}")
    if sub(card["scenario"]):
        sections.append(f"Scenario: {sub(card['scenario'])}")
    before, after = activate_lorebook(card["character_book"], history)
    before = [sub(t) for t in before if sub(t)]
    after = [sub(t) for t in after if sub(t)]
    if before:
        sections.append("World info:\n" + "\n\n".join(before))
    examples = [sub(p) for p in _START.split(card["mes_example"] or "") if sub(p)]
    if examples:
        sections.append(
            f"Example dialogue, for {char}'s voice and style only (it is not part of this conversation):\n"
            + "\n\n".join(examples)
        )
    if after:
        sections.append("World info:\n" + "\n\n".join(after))
    if sub(card["post_history_instructions"]):
        sections.append(f"Reminder: {sub(card['post_history_instructions'])}")
    return "\n\n".join(sections)


VISION_BLOCK = "<|vision_start|><|image_pad|><|vision_end|>"


def build_prompt(card: NormalizedCard, user: str, history: Sequence[Message], context_messages: int,
                 n_images: int = 0, n_video_frames: int = 0, thinking: bool = False,
                 system_override: str | None = None) -> str:
    char = card["name"]
    system = build_system_text(card, user, history, system_override)
    window = list(history[-context_messages:]) if context_messages > 0 else list(history)
    out = [f"<|im_start|>system\n{system}<|im_end|>\n"]
    for i, m in enumerate(window):
        content = substitute(m["content"], char, user).strip()
        if i == len(window) - 1 and m["role"] == "user" and n_images > 0:
            prefix = VISION_BLOCK * n_images
            if n_video_frames > 0:
                prefix += f"\n[The last {n_video_frames} attached images are consecutive frames from a video.]"
            content = f"{prefix}\n{content}"
        out.append(f"<|im_start|>{m['role']}\n{content}<|im_end|>\n")
    out.append("<|im_start|>assistant\n")
    out.append("<think>\n" if thinking else "<think>\n\n</think>\n\n")
    return "".join(out)


_STOPS = ("<|im_end|>", "<|im_start|>", "<|endoftext|>")


def clean_reply(text: str, char: str) -> str:
    s = text or ""
    if "</think>" in s:
        s = s.rpartition("</think>")[2]
    else:
        s = s.replace("<think>", "", 1)
    cut = min((i for i in (s.find(t) for t in _STOPS) if i >= 0), default=-1)
    if cut >= 0:
        s = s[:cut]
    s = s.strip()
    if char:
        s = re.sub(rf"^\s*{re.escape(char)}\s*:\s*", "", s, count=1, flags=re.I)
    return s.strip()


# --------------------------------------------------------------------------- generation helpers


def video_frame_indices(total: int, fps: float, max_frames: int) -> list[int]:
    """About one frame per second, capped at `max_frames`, evenly spaced and unique."""
    if total <= 0:
        return []
    fps = fps if fps and fps > 0 else 24.0
    wanted = max(1, min(int(max_frames), math.ceil(total / fps)))
    return linspace_indices(total, min(wanted, total))


MtpValue = Union[bool, str]
SamplingValue = Union[bool, int, float, str, None]


def mtp_value(mode: str) -> MtpValue:
    m = (mode or "auto").strip().lower()
    if m == "off":
        return False
    if m == "auto":
        return True
    return m


def sampling_kwargs(sampling_mode: str, max_length: int, temperature: float, top_k: int, top_p: float,
                    min_p: float, repetition_penalty: float, presence_penalty: float, seed: int,
                    mtp: str) -> dict[str, SamplingValue]:
    if (sampling_mode or "on") == "off":
        return {"do_sample": False, "max_length": int(max_length), "temperature": 1.0, "top_k": 50,
                "top_p": 1.0, "min_p": 0.0, "repetition_penalty": 1.0, "presence_penalty": 0.0,
                "seed": None, "mtp": mtp_value(mtp)}
    return {"do_sample": True, "max_length": int(max_length), "temperature": float(temperature),
            "top_k": int(top_k), "top_p": float(top_p), "min_p": float(min_p),
            "repetition_penalty": float(repetition_penalty), "presence_penalty": float(presence_penalty),
            "seed": int(seed), "mtp": mtp_value(mtp)}


def card_info(loaded: LoadedCard, user: str) -> CardInfo:
    card = loaded["card"]
    char = card["name"]
    return {
        "name": char,
        "creator": card["creator"],
        "tags": card["tags"][:8],
        "spec": card["spec"],
        "first_mes": substitute(card["first_mes"], char, user),
        "alternate_greetings": [substitute(a, char, user) for a in card["alternate_greetings"]],
        "description": substitute(card["description"], char, user)[:600],
        "creator_notes": card["creator_notes"][:600],
        "lore_entries": len(book_entries(card["character_book"])),
        "source": loaded["source"],
    }
