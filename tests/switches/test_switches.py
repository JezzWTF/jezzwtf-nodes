from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from multi_switch import MAX_SLOTS, MultiSwitch
from comfy_execution.graph_utils import ExecutionBlocker
from switch import MISSING, JWTFRoute, JWTFSwitch
from v3_helpers import legacy

ROOT = Path(__file__).resolve().parents[2]
NODE = shutil.which("node")


# ---------------------------------------------------------------- Switch

def test_switch_schema() -> None:
    schema = JWTFSwitch.GET_SCHEMA()
    assert schema.node_id == "JWTFSwitch" and schema.category == "JezzWTF/utils"
    assert [i.id for i in schema.inputs] == ["switch", "if_true", "if_false"]
    assert [i.display_name for i in schema.inputs[1:]] == ["true", "false"]
    assert all(i.lazy and i.optional for i in schema.inputs[1:])
    assert [o.id for o in schema.outputs] == ["output"]
    # both sides and the output share one match template, so the output takes the connected type
    assert schema.inputs[1].template.template_id == schema.inputs[2].template.template_id == schema.outputs[0].template.template_id


def test_switch_passes_the_chosen_side() -> None:
    (out,) = legacy(JWTFSwitch.execute(True, if_true="T", if_false="F"))
    assert out == "T"
    (out,) = legacy(JWTFSwitch.execute(False, if_true="T", if_false="F"))
    assert out == "F"


def test_switch_passes_any_value_untouched() -> None:
    marker = object()
    assert legacy(JWTFSwitch.execute(True, if_true=marker))[0] is marker
    assert legacy(JWTFSwitch.execute(False, if_false=None))[0] is None


def test_switch_names_the_empty_side() -> None:
    with pytest.raises(ValueError, match="false input"):
        JWTFSwitch.execute(False, if_true="only true")
    with pytest.raises(ValueError, match="true input"):
        JWTFSwitch.execute(True, if_false="only false")


def test_switch_asks_only_for_the_chosen_side() -> None:
    # None means "connected but not computed yet"; MISSING means "not connected"
    assert JWTFSwitch.check_lazy_status(True, if_true=None, if_false=None) == ["if_true"]
    assert JWTFSwitch.check_lazy_status(False, if_true=None, if_false=None) == ["if_false"]
    assert JWTFSwitch.check_lazy_status(True, if_true="done", if_false=None) == []
    assert JWTFSwitch.check_lazy_status(False, if_true=None, if_false="done") == []
    assert JWTFSwitch.check_lazy_status(True, if_false=None) == []


def test_switch_needs_something_connected() -> None:
    assert JWTFSwitch.validate_inputs(True) != True  # noqa: E712 - an error message, not True
    assert "connect something" in str(JWTFSwitch.validate_inputs(False))
    assert JWTFSwitch.validate_inputs(True, if_true=None) is True
    assert JWTFSwitch.validate_inputs(False, if_false="x") is True
    assert MISSING is not None


# ---------------------------------------------------------------- Route

def test_route_schema() -> None:
    schema = JWTFRoute.GET_SCHEMA()
    assert schema.node_id == "JWTFRoute" and schema.category == "JezzWTF/utils"
    assert [i.id for i in schema.inputs] == ["switch", "value"] and not schema.inputs[1].optional
    assert [o.id for o in schema.outputs] == ["if_true", "if_false"] and [o.display_name for o in schema.outputs] == ["true", "false"]
    assert schema.inputs[1].template.template_id == schema.outputs[0].template.template_id == schema.outputs[1].template.template_id


def test_route_sends_the_value_to_one_side_and_blocks_the_other() -> None:
    true_out, false_out = legacy(JWTFRoute.execute(True, "payload"))
    assert true_out == "payload" and isinstance(false_out, ExecutionBlocker)
    true_out, false_out = legacy(JWTFRoute.execute(False, "payload"))
    assert false_out == "payload" and isinstance(true_out, ExecutionBlocker)


def test_route_blocks_silently() -> None:
    _, blocked = legacy(JWTFRoute.execute(True, 1))
    assert blocked.message is None


def test_route_keeps_falsy_values() -> None:
    assert legacy(JWTFRoute.execute(True, 0))[0] == 0
    assert legacy(JWTFRoute.execute(False, ""))[1] == ""


# ---------------------------------------------------------------- Multi Switch

def test_multi_switch_keeps_the_ids_saved_workflows_use() -> None:
    schema = MultiSwitch.GET_SCHEMA()
    ids = [i.id for i in schema.inputs]
    assert ids[0] == "switch" and len(ids) == 1 + 2 * MAX_SLOTS
    assert ids[1:5] == ["false_1", "true_1", "false_2", "true_2"]
    assert [o.id for o in schema.outputs] == [f"output_{i}" for i in range(1, MAX_SLOTS + 1)]
    assert schema.node_id == "MultiSwitch" and schema.category == "JezzWTF/utils"


def test_multi_switch_pairs_share_a_template_with_their_output() -> None:
    schema = MultiSwitch.GET_SCHEMA()
    inputs = {i.id: i for i in schema.inputs}
    for n, out in enumerate(schema.outputs, start=1):
        assert inputs[f"true_{n}"].template.template_id == inputs[f"false_{n}"].template.template_id == out.template.template_id
    assert len({o.template.template_id for o in schema.outputs}) == MAX_SLOTS  # independent pairs
    assert all(i.lazy and i.optional for i in schema.inputs[1:])


def test_multi_switch_routes_each_pair_to_its_output() -> None:
    inputs = {"true_1": "t1", "false_1": "f1", "true_2": "t2", "false_2": "f2"}
    assert legacy(MultiSwitch.execute(True, **inputs)) == ("t1", "t2", None, None, None, None)
    assert legacy(MultiSwitch.execute(False, **inputs)) == ("f1", "f2", None, None, None, None)


def test_multi_switch_leaves_unused_outputs_empty() -> None:
    assert legacy(MultiSwitch.execute(True, true_3="only third")) == (None, None, "only third", None, None, None)
    assert legacy(MultiSwitch.execute(True)) == (None,) * MAX_SLOTS


def test_multi_switch_asks_only_for_the_chosen_side_of_each_pair() -> None:
    pending = {"true_1": None, "false_1": None, "true_2": "ready", "false_2": None, "true_3": None}
    assert MultiSwitch.check_lazy_status(True, **pending) == ["true_1", "true_3"]
    assert MultiSwitch.check_lazy_status(False, **pending) == ["false_1", "false_2"]
    assert MultiSwitch.check_lazy_status(True) == []


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_front_end_file_parses() -> None:
    done = subprocess.run([NODE or "node", "--check", "--input-type=module"], input=(ROOT / "js" / "switches.js").read_text(encoding="utf-8"),
                          capture_output=True, text=True, encoding="utf-8", timeout=30, check=False)
    assert done.returncode == 0, done.stderr
