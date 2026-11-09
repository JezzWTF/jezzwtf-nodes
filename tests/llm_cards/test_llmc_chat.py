"""Character chat: macros, lorebook activation, prompt building, reply cleanup and turn logic."""

from nodes.llm_cards import character as ch


def _card(**over):
    base = ch.normalize_card({"spec": "chara_card_v2", "data": {"name": "Mira", "description": "{{char}} meets {{user}}",
                                                                "first_mes": "Hello {{user}}"}})
    base.update(over)
    return base


def _msgs(*pairs):
    return [{"role": r, "content": c} for r, c in pairs]


def test_macros():
    s = ch.substitute("{{// note }}{{ Char }} & <BOT> vs {{user}}/<USER>{{original}}", "Mira", "Sam")
    assert s == "Mira & Mira vs Sam/Sam"
    assert ch.substitute("{{char}}", "a\\1b", "u") == "a\\1b"


def test_lore_key_matching():
    assert ch.key_matches("Dragon", "a dragon appears", False)
    assert not ch.key_matches("Dragon", "a dragon appears", True)
    assert ch.key_matches("/drag(on)?/i", "DRAG", False)
    assert not ch.key_matches("/drag/i", "DRAG", True)  # case_sensitive overrides the i flag
    assert not ch.key_matches("/drag/", "DRAG", False)
    assert not ch.key_matches("/([/", "anything", False)  # invalid regex never matches
    assert not ch.key_matches("  ", "x", False)


def test_lore_activation_order_budget_and_position():
    book = {"entries": [
        {"keys": ["sword"], "content": "S" * 3000, "insertion_order": 5},
        {"keys": ["castle"], "content": "castle lore", "insertion_order": 1, "priority": 1},
        {"keys": ["castle"], "content": "castle hi-pri", "insertion_order": 1, "priority": 9},
        {"keys": ["sword"], "content": "B" * 600, "insertion_order": 6},
        {"keys": ["sword"], "content": "tiny", "insertion_order": 7, "position": "after_char"},
        {"constant": True, "content": "always", "insertion_order": 100},
        {"keys": ["castle"], "content": "disabled", "enabled": False},
        {"keys": ["castle"], "secondary_keys": ["moat"], "selective": True, "content": "needs moat"},
        {"keys": ["castle"], "secondary_keys": ["gate"], "selective": True, "content": "has gate"},
        {"keys": ["castle"], "content": ""},
    ]}
    hist = _msgs(("user", "old moat"), ("assistant", "x"), ("user", "the castle gate"), ("assistant", "a sword"),
                 ("user", "ok"))
    before, after = ch.activate_lorebook(book, hist)
    # "old moat" is outside the last 4 messages, so "needs moat" does not fire
    # "B"*600 would exceed the 3500-char budget and is skipped; later smaller entries still fit.
    assert before == ["castle hi-pri", "castle lore", "S" * 3000, "always", "has gate"]
    assert after == ["tiny"]


def test_lore_world_info_dict_entries():
    book = {"entries": {"0": {"keys": ["x"], "content": "from dict"}}}
    assert ch.activate_lorebook(book, _msgs(("user", "x")))[0] == ["from dict"]


def test_system_text_sections_order():
    card = _card(personality="kind", scenario="a ship", mes_example="<START>\n{{char}}: hi\n<start>\n{{user}}: yo",
                 post_history_instructions="be brief",
                 character_book={"entries": [{"constant": True, "content": "pre"},
                                             {"constant": True, "content": "post", "position": "after_char"}]})
    text = ch.build_system_text(card, "Sam", [])
    order = [text.index(s) for s in ("Mira's next reply", "Mira meets Sam", "personality: kind", "Scenario: a ship",
                                     "pre", "Mira: hi", "Sam: yo", "post", "Reminder: be brief")]
    assert order == sorted(order)
    assert ch.build_system_text(card, "Sam", [], "Custom for {{char}}").startswith("Custom for Mira")
    assert ch.build_system_text(_card(system_prompt="Card sys"), "Sam", []).startswith("Card sys")


def test_build_prompt_chatml_and_media():
    hist = _msgs(("assistant", "Hello {{user}}"), ("user", "  look at this  "))
    p = ch.build_prompt(_card(), "Sam", hist, 40, n_images=3, n_video_frames=2, thinking=False)
    assert p.startswith("<|im_start|>system\n")
    assert "<|im_start|>assistant\nHello Sam<|im_end|>\n" in p
    assert ch.VISION_BLOCK * 3 + "\n[The last 2 attached images" in p
    assert "look at this<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n" in p
    assert p.endswith("<think>\n\n</think>\n\n")
    p2 = ch.build_prompt(_card(), "Sam", hist, 1, thinking=True)
    assert "Hello Sam" not in p2.split("<|im_end|>\n", 1)[1]  # trimmed to the last message
    assert p2.endswith("<|im_start|>assistant\n<think>\n")
    p3 = ch.build_prompt(_card(), "Sam", _msgs(("user", "a"), ("assistant", "b")), 40, n_images=2)
    assert ch.VISION_BLOCK not in p3  # last message is not a user message


def test_clean_reply():
    assert ch.clean_reply("<think>hmm</think>\n Mira: Hi there<|im_end|>junk", "Mira") == "Hi there"
    assert ch.clean_reply("<think>partial Mira: ok", "Mira") == "partial Mira: ok"
    assert ch.clean_reply("mira:  yes<|endoftext|>", "Mira") == "yes"


def test_turn_logic():
    hist, gen = ch.apply_turn([], "none", "", "Hello Sam")
    assert hist == _msgs(("assistant", "Hello Sam")) and not gen
    hist, gen = ch.apply_turn(hist, "send", "  hi  ", "Hello Sam")
    assert hist[-1] == {"role": "user", "content": "hi"} and gen
    hist2, gen2 = ch.apply_turn(hist + _msgs(("assistant", "r1"), ("assistant", "r2")), "regenerate", "", "")
    assert hist2 == hist and gen2
    only, gen3 = ch.apply_turn(_msgs(("assistant", "greet")), "regenerate", "", "")
    assert only == _msgs(("assistant", "greet")) and not gen3
    _, gen4 = ch.apply_turn(_msgs(("assistant", "g")), "send", "   ", "")
    assert not gen4


def test_parse_history_and_log():
    raw = '[{"role":"user","content":"a"},{"role":"system","content":"x"},{"role":"assistant","content":5},' \
          '{"role":"assistant","content":"{{user}}!"}]'
    hist = ch.parse_history(raw)
    assert hist == _msgs(("user", "a"), ("assistant", "{{user}}!"))
    assert ch.parse_history("not json") == []
    assert ch.chat_log(hist, "Mira", "Sam") == "Sam: a\n\nMira: Sam!"


def test_video_indices_and_sampling():
    assert ch.video_frame_indices(48, 24, 8) == [0, 47]
    assert ch.video_frame_indices(240, 24, 8) == [0, 34, 68, 102, 137, 171, 205, 239]
    assert ch.video_frame_indices(3, 0, 8) == [0]
    off = ch.sampling_kwargs("off", 100, 0.7, 64, 0.9, 0.05, 1.1, 0.5, 42, "auto")
    assert off["do_sample"] is False and off["seed"] is None and off["top_k"] == 50 and off["mtp"] is True
    on = ch.sampling_kwargs("on", 100, 0.7, 64, 0.9, 0.05, 1.1, 0.5, 42, "tree2s1")
    assert on["do_sample"] is True and on["seed"] == 42 and on["mtp"] == "tree2s1"
    assert ch.mtp_value("off") is False
