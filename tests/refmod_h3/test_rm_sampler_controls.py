"""Advanced-input widget overrides must preserve values and handle link id zero."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

NODE = shutil.which("node")
MODULE = Path(__file__).resolve().parents[2] / "js/refmod_h3/sampler_controls.js"


@pytest.mark.skipif(NODE is None, reason="Node is not installed")
def test_advanced_input_visibility_and_values():
    script = f"""
      import {{ samplerWidgetVisibility }} from {json.dumps(MODULE.as_uri())};
      const widgets = [{{name:'sampler_name',value:'euler'}},{{name:'seed',value:42}},{{name:'cfg',value:5.5}},{{name:'cfg_enabled',value:true}}];
      const node = {{ widgets, inputs: [{{name:'noise',link:0}},{{name:'sampler',link:1}},{{name:'guider',link:2}}] }};
      const connected = samplerWidgetVisibility(node);
      node.inputs = node.inputs.map(i => ({{...i, link:null}}));
      const unconnected = samplerWidgetVisibility(node);
      node.inputs = [{{name:'noise',link:0}},{{name:'sampler',link:1}},{{name:'guider',link:2}}];
      widgets[0].value = 'clown: res_2m';
      console.log(JSON.stringify({{ connected, unconnected, clown:samplerWidgetVisibility(node), widgets }}));
    """
    result = subprocess.run([NODE, "--input-type=module", "-e", script], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["connected"] == dict.fromkeys(("sampler_name", "seed", "cfg", "cfg_enabled"), False)
    assert all(data["unconnected"].values()) and all(data["clown"].values())
    assert [w["value"] for w in data["widgets"]] == ["clown: res_2m", 42, 5.5, True]
