"""Refinement must start from generated pixels and keep reference conditioning."""
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("family", ["Flux_2", "Flux_3", "Flux_3_Distilled"])
def test_refinement_uses_encoded_image_references_and_low_noise(family):
    path = ROOT / "example_workflows" / f"RefMod_Upscale_Refine_{family}.json"
    workflow = json.loads(path.read_text(encoding="utf-8"))
    nodes = {n["type"]: n for n in workflow["nodes"]}
    links = {link[0]: link for link in workflow["links"]}

    def source(kind, field):
        node = nodes[kind]
        return links[next(i["link"] for i in node["inputs"] if i["name"] == field)][1:3]

    assert source("SamplerCustomAdvanced", "latent_image") == [nodes["VAEEncode"]["id"], 0]
    assert source("VAEEncode", "pixels") == [nodes["ImageScaleToTotalPixels"]["id"], 0]
    assert source("VAEEncode", "vae") == source("VAEDecode", "vae")
    assert source("CFGGuider", "positive") == [nodes["JWTFUnifiedRefModApply"]["id"], 0]
    assert source("CFGGuider", "negative") == [nodes["JWTFUnifiedRefModApply"]["id"], 1]
    assert nodes["JWTFUnifiedRefModApply"]["widgets_values_named"]["ref_strength"] == 1
    assert nodes["ImageScaleToTotalPixels"]["widgets_values_named"]["resolution_steps"] == 16
    assert not any(n["type"].startswith("Empty") for n in workflow["nodes"])
    if family == "Flux_2":
        assert source("SamplerCustomAdvanced", "sigmas") == [nodes["SplitSigmasDenoise"]["id"], 1]
        assert nodes["SplitSigmasDenoise"]["widgets_values_named"]["denoise"] == 0.2
        assert source("Flux2Scheduler", "width") == [nodes["GetImageSize"]["id"], 0]
        assert source("Flux2Scheduler", "height") == [nodes["GetImageSize"]["id"], 1]
        assert source("GetImageSize", "image") == [nodes["ImageScaleToTotalPixels"]["id"], 0]
    else:
        assert source("SamplerCustomAdvanced", "sigmas") == [nodes["BasicScheduler"]["id"], 0]
        assert nodes["BasicScheduler"]["widgets_values_named"]["denoise"] == 0.2
        if family == "Flux_3_Distilled":
            assert nodes["UNETLoader"]["widgets_values_named"]["unet_name"] == "flux3-image-klein-int8-convrot.safetensors"
            assert nodes["BasicScheduler"]["widgets_values_named"]["steps"] == 16
            assert nodes["CFGGuider"]["widgets_values_named"]["cfg"] == 1
