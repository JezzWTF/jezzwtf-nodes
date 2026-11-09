"""Card parsing / normalisation (V1, V2, V3), PNG chunks and the workflow classifier."""

import base64
import io
import json
import os
import struct
import zlib

import pytest
from PIL import Image

from nodes.llm_cards import bakers, card_v2, character, png_chunks
from nodes.llm_cards.common import JSONTextError, clean_json_text, safe_name, safe_prefix_path


def _png(chunks: dict[str, str]) -> bytes:
    return png_chunks.png_bytes_with_text(Image.new("RGB", (4, 4), (255, 0, 0)), chunks)


def _raw_chunk(ctype: bytes, body: bytes) -> bytes:
    return struct.pack(">I", len(body)) + ctype + body + struct.pack(">I", zlib.crc32(ctype + body))


# --------------------------------------------------------------------------- V2 baker normalisation


def test_flat_card_is_wrapped_and_filled():
    card, notes = card_v2.parse_card_text('{"name": "Ana", "description": "A pilot"}')
    assert card["spec"] == "chara_card_v2" and card["spec_version"] == "2.0"
    assert card["data"]["name"] == "Ana"
    assert card["data"]["alternate_greetings"] == [] and card["data"]["extensions"] == {}
    assert any("Wrapped" in n for n in notes)


def test_no_fill_keeps_missing_fields():
    card, _ = card_v2.parse_card_text('{"name": "Ana"}', fill_missing=False)
    assert "tags" not in card["data"]


def test_fenced_double_encoded_and_wrapped():
    inner = json.dumps({"name": "Bo", "first_mes": "hi"})
    text = "```json\n" + json.dumps({"result": json.dumps(inner)}) + "\n```"
    card, notes = card_v2.parse_card_text(text)
    assert card["data"]["name"] == "Bo"
    assert len(notes) >= 2


def test_v3_relabelled_and_extras_kept():
    raw = {"Spec": "chara_card_v3", "spec_version": "3.0", "data": {"Name": "Cy", "assets": [1]}, "extra": 5}
    card, notes = card_v2.normalise_v2(raw)
    assert card["spec"] == "chara_card_v2" and card["extra"] == 5
    assert card["data"]["name"] == "Cy" and card["data"]["assets"] == [1]
    assert any("chara_card_v3" in n for n in notes)


def test_legacy_tavern_keys_renamed():
    card, _ = card_v2.normalise_v2({"char_name": "Di", "char_greeting": "yo", "example_dialogue": "x"})
    assert card["data"]["name"] == "Di" and card["data"]["first_mes"] == "yo"
    assert card["data"]["mes_example"] == "x"


def test_type_repairs():
    card, _ = card_v2.normalise_v2({"name": "E", "tags": "a, b ,", "alternate_greetings": "hey",
                                    "extensions": "bad", "creator": 7, "scenario": None})
    d = card["data"]
    assert d["tags"] == ["a", "b"] and d["alternate_greetings"] == ["hey"]
    assert d["extensions"] == {} and d["creator"] == "7" and d["scenario"] == ""


def test_errors():
    with pytest.raises(JSONTextError):
        card_v2.parse_card_text("   ")
    with pytest.raises(JSONTextError, match="line 1, column"):
        card_v2.parse_card_text('{"name": }')
    with pytest.raises(card_v2.CardError, match="no name"):
        card_v2.parse_card_text('{"description": "x"}')
    with pytest.raises(card_v2.CardError, match="Top-level keys: foo, bar"):
        card_v2.parse_card_text('{"foo": 1, "bar": 2}')


def test_card_info_counts_and_rarity():
    card, notes = card_v2.normalise_v2({"name": "F", "description": "d" * 4000, "alternate_greetings": ["a"],
                                        "character_book": {"entries": [{"content": "c" * 400}]}})
    info = card_v2.card_info(card, 2048, notes)
    assert info["book_entries"] == 1 and info["alt_greetings"] == 1
    assert info["tokens"] == round((1 + 4000 + 1 + 400) / 4)
    assert info["rarity"] == "rare" and info["kb"] == 2.0
    assert info["excerpt_description"].endswith("\u2026") and len(info["excerpt_description"]) == 380


def test_safe_names():
    assert safe_name('  a/b:c*?"<>|%  ') == "a_b_c_______"
    assert safe_name(" ... ") == "card"
    assert safe_prefix_path("../x/./y\\z") == "x/y/z"
    assert safe_prefix_path("") == "workflow"
    assert bakers.card_prefix("V2_cards/%name%", "A/B") == "V2_cards/A_B"
    assert clean_json_text("\ufeff ```\n{}\n``` ") == "{}"


# --------------------------------------------------------------------------- PNG chunks


def test_chara_roundtrip_utf8():
    card = {"spec": "chara_card_v2", "spec_version": "2.0", "data": {"name": "Zoë 日本"}}
    b64 = png_chunks.encode_chara(card)
    assert b64.isascii()
    assert "Zoë 日本" in base64.b64decode(b64).decode("utf-8")  # real UTF-8, no \u escapes
    data = _png({"chara": b64})
    chunks = png_chunks.read_text_chunks(data)
    assert png_chunks.decode_chara(chunks["chara"]) == card
    assert character.card_from_png(data)["data"]["name"] == "Zoë 日本"


def test_ztxt_itxt_and_first_wins():
    sig = png_chunks.PNG_SIG
    ihdr = _raw_chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    z = _raw_chunk(b"zTXt", b"k1\x00\x00" + zlib.compress("zé".encode("utf-8")))
    i = _raw_chunk(b"iTXt", b"k2\x00\x01\x00en\x00\x00" + zlib.compress("ié".encode("utf-8")))
    t1 = _raw_chunk(b"tEXt", b"k1\x00second")
    bad = _raw_chunk(b"zTXt", b"k3\x00\x00notzlib")
    data = sig + ihdr + z + i + t1 + bad + _raw_chunk(b"IEND", b"") + _raw_chunk(b"tEXt", b"late\x00x")
    assert png_chunks.read_text_chunks(data) == {"k1": "zé", "k2": "ié"}


def test_ccv3_preferred_over_chara():
    v2 = base64.b64encode(json.dumps({"data": {"name": "Old"}}).encode()).decode()
    v3 = base64.b64encode(json.dumps({"spec": "chara_card_v3", "data": {"name": "New"}}).encode()).decode()
    raw = character.card_from_png(_png({"chara": v2, "ccv3": v3}))
    assert raw["data"]["name"] == "New"


def test_png_error_messages():
    with pytest.raises(character.CardReadError, match="JPEG"):
        character.card_from_png(b"\xff\xd8\xff\xe0rest")
    with pytest.raises(character.CardReadError, match="WebP"):
        character.card_from_png(b"RIFF\x00\x00\x00\x00WEBPVP8 ")
    buf = io.BytesIO()
    Image.new("RGB", (2, 2)).save(buf, format="PNG")
    with pytest.raises(character.CardReadError, match="no text chunks"):
        character.card_from_png(buf.getvalue())
    with pytest.raises(character.CardReadError, match=r"\(Software\)"):
        character.card_from_png(_png({"Software": "paint"}))


# --------------------------------------------------------------------------- chat card normalisation


def test_decode_payload_variants():
    obj = {"name": "G"}
    raw = json.dumps(obj)
    assert character.decode_payload(raw) == obj
    assert character.decode_payload(base64.b64encode(raw.encode()).decode()) == obj
    url = base64.urlsafe_b64encode(("\ufeff" + json.dumps({"name": "~~??>>"})).encode()).decode().rstrip("=")
    assert character.decode_payload(url) == {"name": "~~??>>"}
    assert character.decode_payload(json.dumps(json.dumps(obj))) == obj
    assert character.decode_payload("not json") is None


def test_normalize_v1_v2_v3():
    v1 = character.normalize_card({"char_name": "H", "char_persona": "p", "char_greeting": "hi"})
    assert v1["spec"] == "chara_card_v1" and v1["name"] == "H"
    assert v1["description"] == "p" and v1["first_mes"] == "hi"
    v2 = character.normalize_card({"spec": "chara_card_v2", "data": {
        "name": "I", "tags": ["a", 3], "alternate_greetings": ["x", "", 5], "character_book": {"entries": []}}})
    assert v2["tags"] == ["a", "3"] and v2["alternate_greetings"] == ["x"]
    assert v2["character_book"] == {"entries": []}
    v3 = character.normalize_card({"spec": "chara_card_v3", "data": {"name": "", "tags": "q, r"}})
    assert v3["name"] == "Character" and v3["tags"] == ["q", "r"] and v3["character_book"] is None


def test_load_card_files(tmp_path):
    card = {"spec": "chara_card_v2", "data": {"name": "J", "system_prompt": "orig"}}
    (tmp_path / "c.json").write_text(json.dumps(card), encoding="utf-8")
    loaded = character.load_card(str(tmp_path / "c.json"))
    assert loaded["card"]["name"] == "J" and loaded["avatar_png"] is None

    avatar = _png({})
    meta = {"jezzwtf_character_card": json.dumps(card), "jezzwtf_character_system_prompt": "embedded",
            "jezzwtf_character_avatar_png_b64": base64.b64encode(avatar).decode(), "jezzwtf_character_version": "1"}
    header = json.dumps({"__metadata__": meta}).encode()
    (tmp_path / "r.safetensors").write_bytes(struct.pack("<Q", len(header)) + header)
    loaded = character.load_card(str(tmp_path / "r.safetensors"))
    assert loaded["source"] == "refmod" and loaded["card"]["system_prompt"] == "embedded"
    assert loaded["avatar_png"] == avatar
    assert character.refmod_has_card(str(tmp_path / "r.safetensors"))

    (tmp_path / "bad.safetensors").write_bytes(struct.pack("<Q", 1) + b"{")
    with pytest.raises(character.CardReadError, match="header length"):
        character.load_card(str(tmp_path / "bad.safetensors"))


def test_discovery_and_resolution(tmp_path):
    cards = tmp_path / "characters"
    (cards / "sub").mkdir(parents=True)
    (cards / "b.json").write_text("{}")
    (cards / "sub" / "A.png").write_bytes(b"")
    (cards / "notes.txt").write_text("")
    assert character.list_card_files(str(cards)) == ["b.json", "sub/A.png"]
    assert character.card_choices(str(tmp_path / "missing"), []) == [character.PLACEHOLDER]
    assert character.resolve_card_path("sub/A.png", "", str(cards), []) == str(cards / "sub" / "A.png")
    inside = str(cards / "sub" / "A.png")
    assert character.resolve_card_path("x", ' "' + inside + '" ', str(cards), [], [str(cards)]) == os.path.realpath(inside)
    assert character.resolve_card_path("x", inside, str(cards), []).endswith("x")  # routes: card_path ignored
    assert character.resolve_card_path("b.json", "undefined", str(cards), []).endswith("b.json")
    with pytest.raises(character.CardReadError, match="escapes"):
        character.resolve_card_path("../../etc/passwd", "", str(cards), [])
    with pytest.raises(character.CardReadError, match="No character"):
        character.resolve_card_path(character.PLACEHOLDER, "", str(cards), [])


# --------------------------------------------------------------------------- workflow baker


def test_workflow_classification():
    wf = {"nodes": [], "links": []}
    api = {"1": {"class_type": "KSampler", "inputs": {}}}
    assert bakers.classify_workflow(json.dumps(wf)) == (wf, None)
    assert bakers.classify_workflow(json.dumps(json.dumps(api))) == (None, api)
    both = {"workflow": json.dumps(wf), "prompt": api, "x": 1}
    assert bakers.classify_workflow(json.dumps(both)) == (wf, api)
    with pytest.raises(ValueError, match="Top-level keys: a"):
        bakers.classify_workflow('{"a": 1}')
    chunks = bakers.workflow_chunks(wf, {"1": {"class_type": "Ü"}})
    assert chunks["prompt"].isascii()


def test_workflow_verify_roundtrip(tmp_path):
    wf = {"nodes": [{"id": 1, "title": "é"}], "links": []}
    path = str(tmp_path / "w.png")
    png_chunks.save_png_with_text(Image.new("RGB", (4, 4)), path, bakers.workflow_chunks(wf, None))
    bakers.verify_workflow(path, wf, None)
    with pytest.raises(RuntimeError):
        bakers.verify_workflow(path, {"nodes": [], "links": []}, None)


def test_clean_json_text_llm_wrappers():
    card = '{"name": "A", "note": "} not the end"}'
    assert clean_json_text("<think>plan {x}</think>\n" + card) == card
    assert clean_json_text("<think>\n" + card) == card
    assert clean_json_text("Sure! Here is the card:\n```json\n" + card + "\n```\nHope it helps.") == card
    assert clean_json_text("Here it is: " + card + "\nEnjoy.") == card
    assert clean_json_text(card + "\n\nLet me know!") == card
    assert clean_json_text("<think>x</think>Sure:\n```\n" + card + "\n```") == card
    parsed, _ = card_v2.parse_card_text("<think>hmm</think>Result:\n```json\n" + card + "\n```\ndone")
    assert parsed["data"]["name"] == "A"


def test_parse_json_text_repairs_small_model_slips():
    from nodes.llm_cards.common import parse_json_text
    assert parse_json_text('{"a": {"b": [1, 2]}') == {"a": {"b": [1, 2]}}  # missing closer
    assert parse_json_text('{"a": ["x"]], "b": "}"}') == {"a": ["x"], "b": "}"}  # stray closer
    assert parse_json_text('{"a": [1, 2,], "b": 3,}') == {"a": [1, 2], "b": 3}  # trailing commas
    with pytest.raises(JSONTextError):
        parse_json_text('{"a": "unterminated')
