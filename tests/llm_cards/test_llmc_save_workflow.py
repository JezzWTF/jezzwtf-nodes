"""Saving: new cards land in input/characters (so the chat dropdown lists them) and chats can be exported."""
from __future__ import annotations

import json
import os
import types

import torch

from nodes.llm_cards import bakers, character, character_chat
from test_llmc_nodes_e2e import comfy_dirs  # noqa: F401  (fixture)


def _card() -> str:
    return json.dumps({"name": "Mira", "description": "d", "first_mes": "Hi"})


def test_baker_saves_into_characters_folder_by_default(comfy_dirs: types.ModuleType) -> None:  # noqa: F811
    res = bakers.JWTFV2PNGBaker().bake(torch.rand(1, 16, 24, 3), _card(), "%name%", True)
    path = res["result"][0]  # type: ignore[index]
    assert os.path.dirname(path) == os.path.join(comfy_dirs.get_input_directory(), "characters")
    assert res["ui"]["card_preview"][0]["type"] == "input"  # type: ignore[index]
    assert res["ui"]["card_preview"][0]["subfolder"] == "characters"  # type: ignore[index]
    choices = character.card_choices(os.path.join(comfy_dirs.get_input_directory(), "characters"), [])
    assert choices == [os.path.basename(path)]


def test_baker_can_still_save_to_output(comfy_dirs: types.ModuleType) -> None:  # noqa: F811
    res = bakers.JWTFV2PNGBaker().bake(torch.rand(1, 16, 24, 3), _card(), "cards/%name%", True,
                                       save_to=bakers.SAVE_TO_OUTPUT)
    assert res["ui"]["card_preview"][0]["type"] == "output"  # type: ignore[index]
    assert os.path.abspath(res["result"][0]).startswith(os.path.abspath(comfy_dirs.get_output_directory()))  # type: ignore[index]


def test_write_chat_files_writes_text_and_json(comfy_dirs: types.ModuleType) -> None:  # noqa: F811
    history = [{"role": "assistant", "content": "Hello"}, {"role": "user", "content": "Hi there"}]
    txt = character_chat.write_chat_files(history, "Mira/Q", "Sam")
    assert os.path.dirname(txt) == os.path.join(comfy_dirs.get_output_directory(), "chats")
    assert "Mira_Q" in os.path.basename(txt)
    text = open(txt, encoding="utf-8").read()
    assert "Mira/Q: Hello" in text and "Sam: Hi there" in text
    with open(txt[:-4] + ".json", encoding="utf-8") as fh:
        assert json.load(fh)["messages"] == history
