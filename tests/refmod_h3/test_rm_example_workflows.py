"""Shipped examples must have valid sockets, positional widgets and complete generation paths."""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
FILES = sorted((ROOT / "example_workflows").glob("RefMod_Apply_*.json")) + [
    ROOT / "example_workflows" / "RefMod_Bake_Image_Families.json",
    ROOT / "example_workflows" / "RefMod_Bake_LTX_Guide.json",
    ROOT / "example_workflows" / "RefMod_Reference_Audition.json",
    ROOT / "example_workflows" / "RefMod_Diagnose_MOSS_Image.json",
    ROOT / "example_workflows" / "RefMod_Character_New_Scene_Flux_2.json",
] + sorted((ROOT / "example_workflows").glob("RefMod_Upscale_Refine_*.json")) + sorted((ROOT / "example_workflows").glob("Smart_Select_*.json"))


@pytest.fixture(scope="module")
def generator():
    spec = importlib.util.spec_from_file_location("refmod_workflow_generator", ROOT / "tools" / "generate_refmod_workflows.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    import comfy
    core_root = next(Path(path).resolve().parent for path in comfy.__path__ if (Path(path).parent / "nodes.py").is_file())
    environment = {**os.environ, "PYTHONPATH": str(core_root) + os.pathsep + os.environ.get("PYTHONPATH", "")}
    result = subprocess.run([sys.executable, str(ROOT / "tools" / "generate_refmod_workflows.py"), "--schemas"],
                            cwd=core_root, env=environment, capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stderr
    schemas = json.loads(result.stdout.strip().splitlines()[-1])
    # Tests inspect schemas obtained from the actual core in an isolated interpreter.
    # Importing core nodes.py here would collide with this repository's nodes package.
    return SimpleNamespace(input_spec=lambda name: schemas[name]["input"], is_widget=module.is_widget,
                           registry=lambda: {name: SimpleNamespace(RETURN_TYPES=value["output"]) for name, value in schemas.items()})


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_moss_diagnostic_shares_model_target_and_sampling_but_uses_independent_conditioning():
    workflow = read(ROOT / "example_workflows" / "RefMod_Diagnose_MOSS_Image.json")
    nodes = workflow["nodes"]
    links = {link[0]: link for link in workflow["links"]}
    check = next(n for n in nodes if n["type"] == "JWTFRefModConditioningCheck")
    samplers = [n for n in nodes if n["type"] == "KSampler"]
    assert len(samplers) == 2 and samplers[0]["widgets_values"] == samplers[1]["widgets_values"]
    def source(node, name):
        return links[next(i["link"] for i in node["inputs"] if i["name"] == name)][1:3]
    assert source(samplers[0], "model") == source(samplers[1], "model")
    assert source(samplers[0], "latent_image") == source(samplers[1], "latent_image") == [check["id"], 4]
    assert [source(n, "positive") for n in samplers] == [[check["id"], 0], [check["id"], 2]]
    assert [source(n, "negative") for n in samplers] == [[check["id"], 1], [check["id"], 3]]
    assert not any(n["type"] in ("LoadImage", "JWTFUnifiedRefModBake") for n in nodes)


def test_character_scene_uses_saved_references_and_independent_matching_target_schedule():
    workflow = read(ROOT / "example_workflows" / "RefMod_Character_New_Scene_Flux_2.json")
    nodes = {node["type"]: node for node in workflow["nodes"]}
    links = {link[0]: link for link in workflow["links"]}
    def source(kind, field):
        node = nodes[kind]
        return links[next(i["link"] for i in node["inputs"] if i["name"] == field)][1]
    assert source("SamplerCustomAdvanced", "latent_image") == nodes["EmptyFlux2LatentImage"]["id"]
    assert source("SamplerCustomAdvanced", "latent_image") != nodes["JWTFUnifiedRefModApply"]["id"]
    assert source("CFGGuider", "positive") == source("CFGGuider", "negative") == nodes["JWTFUnifiedRefModApply"]["id"]
    target, schedule = (nodes[name]["widgets_values_named"] for name in ("EmptyFlux2LatentImage", "Flux2Scheduler"))
    assert (target["width"], target["height"]) == (schedule["width"], schedule["height"]) == (1024, 768)
    assert nodes["CFGGuider"]["widgets_values_named"]["cfg"] == 5
    assert schedule["steps"] == 20
    assert nodes["JWTFUnifiedRefModApply"]["widgets_values_named"]["model"] == "auto (from refmod)"


def test_face_refinement_samples_full_crop_and_applies_soft_selection_only_at_pasteback():
    workflow = read(ROOT / "example_workflows" / "Smart_Select_Face_Refine_Flux_2.json")
    nodes = {node["type"]: node for node in workflow["nodes"]}
    links = {link[0]: link for link in workflow["links"]}

    def source(kind, field):
        node = nodes[kind]
        return links[next(i["link"] for i in node["inputs"] if i["name"] == field)][1:3]

    assert source("JWTFRegionCrop", "images") == source("JWTFRegionComposite", "images") == [nodes["LoadImage"]["id"], 0]
    assert source("JWTFRegionCrop", "mask") == [nodes["JWTFMaskEditor"]["id"], 1]
    assert source("JWTFRegionComposite", "region") == [nodes["JWTFRegionCrop"]["id"], 2]
    assert source("JWTFRegionComposite", "refined_crop") == [nodes["VAEDecode"]["id"], 0]
    assert source("VAEEncode", "pixels") == [nodes["JWTFRegionCrop"]["id"], 0]
    # A fractional matte at every sampling step repeatedly pulls the face toward
    # the input. Keep it for pasteback; let diffusion refine the whole RGB crop.
    assert "SetLatentNoiseMask" not in nodes
    assert source("SamplerCustomAdvanced", "latent_image") == [nodes["VAEEncode"]["id"], 0]
    assert source("SamplerCustomAdvanced", "sigmas") == [nodes["SplitSigmasDenoise"]["id"], 1]
    assert source("CFGGuider", "positive") == [nodes["JWTFUnifiedRefModApply"]["id"], 0]
    assert source("CFGGuider", "negative") == [nodes["JWTFUnifiedRefModApply"]["id"], 1]
    assert nodes["JWTFUnifiedRefModApply"]["widgets_values_named"]["ref_strength"] == 1
    assert source("Flux2Scheduler", "width") == [nodes["GetImageSize"]["id"], 0]
    assert source("Flux2Scheduler", "height") == [nodes["GetImageSize"]["id"], 1]
    assert source("JWTFSmartSelect", "clip") != source("CLIPTextEncode", "clip")
    comparisons = [node for node in workflow["nodes"] if node["type"] == "JWTFImageCompare"]
    pairs = {
        tuple(tuple(links[s["link"]][1:3]) for field in ("image_a", "image_b")
              for s in node["inputs"] if s["name"] == field)
        for node in comparisons
    }
    assert ((nodes["JWTFRegionCrop"]["id"], 0), (nodes["VAEDecode"]["id"], 0)) in pairs
    assert ((nodes["LoadImage"]["id"], 0), (nodes["JWTFRegionComposite"]["id"], 0)) in pairs


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.stem)
def test_workflow_links_widgets_and_required_inputs_match_real_schemas(path, generator):
    data = read(path)
    nodes = {n["id"]: n for n in data["nodes"]}
    links = {link[0]: link for link in data["links"]}
    assert len(nodes) == len(data["nodes"]) and len(links) == len(data["links"])
    assert data["last_node_id"] == max(nodes) and data["last_link_id"] == max(links)
    for node in nodes.values():
        specs = generator.input_spec(node["type"])
        expected_widgets = {}
        sockets = {}
        for section in ("required", "optional"):
            for name, spec in specs.get(section, {}).items():
                if generator.is_widget(spec):
                    expected_widgets[name] = spec
                    options = spec[1] if len(spec) > 1 else {}
                    if options.get("control_after_generate"):
                        expected_widgets["control_after_generate"] = (["fixed", "increment", "decrement", "randomize"], {})
                else:
                    sockets[name] = str(spec[0])
        named = node["widgets_values_named"]
        assert list(named) == list(expected_widgets), node["type"]
        assert list(named.values()) == node["widgets_values"]
        for name, spec in expected_widgets.items():
            kind, options = spec[0], spec[1] if len(spec) > 1 else {}
            choices = kind if isinstance(kind, (list, tuple)) else options.get("options", [])
            # File lists are machine-dependent; static enum choices must be real choices.
            if choices and name not in {"image", "unet_name", "ckpt_name", "clip_name", "clip_name1", "clip_name2", "vae_name", "lora_name", "refmod_1", "refmod_2", "refmod_3"}:
                assert named[name] in choices, f"{node['type']}.{name}={named[name]}"
        for socket in node["inputs"]:
            if "widget" in socket:
                assert socket["widget"]["name"] == socket["name"]
                spec = expected_widgets[socket["name"]]
                sockets[socket["name"]] = "COMBO" if isinstance(spec[0], (list, tuple)) else str(spec[0])
        assert {i["name"]: i["type"] for i in node["inputs"]} == sockets
        for field, spec in specs.get("required", {}).items():
            if not generator.is_widget(spec):
                socket = next(i for i in node["inputs"] if i["name"] == field)
                assert socket["link"] in links, f"Unwired required input {node['type']}.{field}"
        if node["type"] != "MarkdownNote":
            assert [o["type"] for o in node["outputs"]] == [str(t) for t in generator.registry()[node["type"]].RETURN_TYPES]
        for slot, socket in enumerate(node["inputs"]):
            if socket["link"] is not None:
                assert links[socket["link"]][3:5] == [node["id"], slot]
        for slot, output in enumerate(node["outputs"]):
            assert set(output["links"] or []) == {link[0] for link in links.values() if link[1:3] == [node["id"], slot]}
    for link_id, origin, source_slot, target, target_slot, kind in links.values():
        source, destination = nodes[origin]["outputs"][source_slot], nodes[target]["inputs"][target_slot]
        assert destination["link"] == link_id and link_id in source["links"]
        assert source["type"] == kind
        assert kind == destination["type"] or "*" in (kind, destination["type"])
        assert nodes[origin]["order"] < nodes[target]["order"]
    note = next(n for n in nodes.values() if n["type"] == "MarkdownNote")
    assert note["flags"]["pinned"]
    if data["extra"]["jezzwtf_refmod_example"]["purpose"] == "smart_selection":
        assert "WeVisOne" in note["widgets_values"][0]
    else:
        assert "matching VAE" in note["widgets_values"][0]


def test_apply_examples_cover_every_registered_family_and_require_a_saved_bundle(generator):
    from refmod_h3.unified import HANDLERS
    examples = [read(p) for p in FILES if "Apply_" in p.name]
    assert {w["extra"]["jezzwtf_refmod_example"]["family"] for w in examples} == set(HANDLERS)
    for workflow in examples:
        apply = next(n for n in workflow["nodes"] if n["type"] == "JWTFUnifiedRefModApply")
        assert apply["widgets_values_named"]["model"] == "auto (from refmod)"
        assert apply["widgets_values_named"]["refmod_1"] == "None"
        assert next(i for i in apply["inputs"] if i["name"] == "extra_image")["link"] is None
        assert not any(n["type"] == "JWTFUnifiedRefModBake" for n in workflow["nodes"])


def test_ltx_guide_is_cropped_after_sampling_and_before_decode():
    workflow = read(ROOT / "example_workflows" / "RefMod_Apply_LTX_Video.json")
    by_type = {n["type"]: n for n in workflow["nodes"]}
    links = {link[0]: link for link in workflow["links"]}
    def source(type_name, field):
        node = by_type[type_name]
        return links[next(i["link"] for i in node["inputs"] if i["name"] == field)][1]
    assert source("SamplerCustomAdvanced", "latent_image") == by_type["JWTFUnifiedRefModApply"]["id"]
    assert source("SamplerCustomAdvanced", "sigmas") == by_type["LTXVScheduler"]["id"]
    assert source("LTXVScheduler", "latent") == by_type["EmptyLTXVLatentVideo"]["id"]
    assert source("LTXVCropGuides", "latent") == by_type["SamplerCustomAdvanced"]["id"]
    assert source("LTXVCropGuides", "positive") == by_type["JWTFUnifiedRefModApply"]["id"]
    assert source("VAEDecode", "samples") == by_type["LTXVCropGuides"]["id"]
    assert source("SaveWEBM", "images") == by_type["VAEDecode"]["id"]
    target = by_type["EmptyLTXVLatentVideo"]["widgets_values_named"]
    bake = read(ROOT / "example_workflows" / "RefMod_Bake_LTX_Guide.json")
    scale = next(n["widgets_values_named"] for n in bake["nodes"] if n["type"] == "ImageScale")
    assert (scale["width"], scale["height"]) == (target["width"], target["height"]) == (512, 512)
    assert by_type["LTXVConditioning"]["widgets_values_named"]["frame_rate"] == by_type["SaveWEBM"]["widgets_values_named"]["fps"] == 24
    assert by_type["CheckpointLoaderSimple"]["widgets_values_named"]["ckpt_name"] == next(n for n in bake["nodes"] if n["type"] == "CheckpointLoaderSimple")["widgets_values_named"]["ckpt_name"]
    assert source("VAEDecode", "vae") == by_type["CheckpointLoaderSimple"]["id"]


@pytest.mark.parametrize("name", ["MOSS_Image", "Krea_2"])
def test_edit_examples_wire_the_edit_lora_into_the_sampler(name):
    workflow = read(ROOT / "example_workflows" / f"RefMod_Apply_{name}.json")
    nodes = {n["type"]: n for n in workflow["nodes"]}
    links = {link[0]: link for link in workflow["links"]}
    sampler_input = next(i for i in nodes["KSampler"]["inputs"] if i["name"] == "model")
    patch = nodes["SkipLayerGuidanceDiTSimple" if name == "MOSS_Image" else "ModelSamplingFlux"]
    assert links[sampler_input["link"]][1] == patch["id"]
    patch_input = next(i for i in patch["inputs"] if i["name"] == "model")
    assert links[patch_input["link"]][1] == nodes["LoraLoaderModelOnly"]["id"]
    assert nodes["JWTFUnifiedRefModApply"]["widgets_values_named"]["edit_format"] == ("Moss-Image-Edit" if name == "MOSS_Image" else "Krea2 style reference")
    if name == "MOSS_Image":
        assert nodes["LoraLoaderModelOnly"]["widgets_values_named"]["lora_name"] == "moss_image_edit_lora_rank_64_bf16.safetensors"
        sampler = nodes["KSampler"]["widgets_values_named"]
        assert (sampler["steps"], sampler["cfg"], sampler["sampler_name"], sampler["scheduler"]) == (30, 4, "euler", "normal")


def test_bake_examples_keep_existing_bundles():
    for path in FILES:
        if "Bake_" not in path.name:
            continue
        bake = next(n for n in read(path)["nodes"] if n["type"] == "JWTFUnifiedRefModBake")
        assert bake["widgets_values_named"]["overwrite"] is False


@pytest.mark.parametrize("filename", ["RefMod_Apply_Flux_2.json", "RefMod_Reference_Audition.json"])
def test_flux2_examples_use_native_schedule_matching_fixed_target(filename):
    workflow = read(ROOT / "example_workflows" / filename)
    nodes = {n["type"]: n for n in workflow["nodes"]}
    schedule = nodes["Flux2Scheduler"]["widgets_values_named"]
    target = nodes["EmptyFlux2LatentImage"]["widgets_values_named"]
    assert (schedule["width"], schedule["height"]) == (target["width"], target["height"])
    destination = nodes.get("JWTFReferenceAudition", nodes.get("SamplerCustomAdvanced"))
    link_id = next(i["link"] for i in destination["inputs"] if i["name"] == "sigmas")
    assert next(link[1] for link in workflow["links"] if link[0] == link_id) == nodes["Flux2Scheduler"]["id"]
    assert schedule["steps"] == 20
    assert nodes["CLIPLoader"]["widgets_values_named"]["clip_name"] == "qwen_3_4b.safetensors"
    assert nodes["UNETLoader"]["widgets_values_named"]["unet_name"] == "flux-2-klein-base-4b.safetensors"
    guidance = nodes.get("JWTFReferenceAudition", nodes.get("CFGGuider"))
    assert guidance["widgets_values_named"]["cfg"] == 5


@pytest.mark.parametrize("path", [path for path in FILES if "Apply_" in path.name], ids=lambda p: p.stem)
def test_named_presets_match_reviewed_official_template_snapshot(path):
    workflow = read(path)
    family = workflow["extra"]["jezzwtf_refmod_example"]["family"]
    snapshot = read(ROOT / "tests/refmod_h3/fixtures/workflow_presets.json")["families"][family]
    nodes = {node["type"]: node for node in workflow["nodes"]}
    widgets = lambda kind: nodes[kind]["widgets_values_named"]
    if family == "ltxv":
        assert widgets("CheckpointLoaderSimple")["ckpt_name"] == snapshot["model"]
    else:
        assert widgets("UNETLoader")["unet_name"] == snapshot["model"]
        assert widgets("VAELoader")["vae_name"] == snapshot["vae"]
    clip = widgets("DualCLIPLoader" if family == "flux_kontext" else "CLIPLoader")
    assert clip["type"] == snapshot["clip_type"]
    assert clip["clip_name1" if family == "flux_kontext" else "clip_name"] == snapshot["clip"]
    if family == "flux_kontext":
        assert clip["clip_name2"] == snapshot["clip_2"]
        assert widgets("FluxGuidance")["guidance"] == snapshot["guidance"]
    if "lora" in snapshot:
        assert widgets("LoraLoaderModelOnly")["lora_name"] == snapshot["lora"]
        assert widgets("JWTFUnifiedRefModApply")["edit_format"] == snapshot["edit_format"]
    if family in ("flux2", "ltxv"):
        assert widgets(snapshot["scheduler"])["steps"] == snapshot["steps"]
        assert widgets("CFGGuider")["cfg"] == snapshot["cfg"]
        assert widgets("KSamplerSelect")["sampler_name"] == "euler"
    else:
        sampler = widgets("KSampler")
        assert (sampler["steps"], sampler["cfg"], sampler["scheduler"], sampler["sampler_name"]) == (snapshot["steps"], snapshot["cfg"], snapshot["scheduler"], "euler")
