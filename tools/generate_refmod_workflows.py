"""Generate the RefMod examples from the installed ComfyUI and JezzWTF node schemas.

Put a ComfyUI checkout on PYTHONPATH, then run this script from the repository.
No models are loaded. The JSON files are the shipped artifacts; ComfyUI users do
not need this script to open them.
"""
from __future__ import annotations

import json
import sys
import uuid
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "example_workflows"
PRIMITIVES = {"INT", "FLOAT", "STRING", "BOOLEAN", "COMBO"}
FAMILIES = {
    "qwen21": ("Qwen_Image_2_1", "Qwen Image 2.1", "qwen_image", 1.0),
    "fibo2": ("Fibo_2", "Fibo 2 Dev", "fibo2", 5.0),
    "flux3": ("Flux_3", "Flux 3 Klein Base", "flux3", 1.0),
    "moss_image": ("MOSS_Image", "MOSS-Image Edit", "moss_image", 4.0),
    "krea2": ("Krea_2", "Krea 2 Turbo Style Reference", "krea2", 1.0),
    "flux_kontext": ("Flux_Kontext", "Flux.1 Kontext", "flux", 1.0),
    "flux2": ("Flux_2", "Flux.2 Klein Base 4B", "flux2", 5.0),
    "ltxv": ("LTX_Video", "LTX Video 2B 0.9.5", "ltxv", 3.0),
}

# Named variants from the official templates; see docs/refmod-workflow-audit.md.
PRESETS = {
    "qwen21": ("qwen_image_2.1_int8_convrot.safetensors", "qwen3vl_8b_int8_convrot.safetensors", "qwen_image_2.1_vae_bf16.safetensors", 25, "simple"),
    "fibo2": ("fibo2_dev_int8_convrot.safetensors", "qwen3vl_4b_bf16.safetensors", "flux2-vae.safetensors", 50, "simple"),
    "flux3": ("flux3-image-klein-base-int8-convrot.safetensors", "qwen3vl_4b_int8_convrot.safetensors", "flux2-vae.safetensors", 50, "simple"),
    "moss_image": ("moss_image_sft_int8_convrot.safetensors", "qwen3.5_9b_w4a8_gptq.safetensors", "flux2-vae_small.safetensors", 30, "normal"),
    "krea2": ("krea2_turbo_int8_convrot.safetensors", "qwen3vl_4b_fp8_scaled.safetensors", "qwen_image_vae.safetensors", 8, "simple"),
    "flux_kontext": ("flux1-dev-kontext_fp8_scaled.safetensors", "", "ae.safetensors", 20, "simple"),
    "flux2": ("flux-2-klein-base-4b.safetensors", "qwen_3_4b.safetensors", "flux2-vae.safetensors", 20, "simple"),
    "ltxv": ("ltx-video-2b-v0.9.5.safetensors", "t5xxl_fp16.safetensors", "", 30, "simple"),
}


@lru_cache(maxsize=1)
def registry() -> dict:
    sys.path.insert(0, str(ROOT / "nodes"))
    from comfy.cli_args import args
    args.cpu = True
    import nodes as core
    from comfy_extras import nodes_flux, nodes_lt, nodes_preview_any, nodes_video
    from refmod_h3.unified import JWTFUnifiedRefModApply, JWTFUnifiedRefModBake
    from refmod_h3.reference_audition import JWTFReferenceAudition, JWTFSaveAuditionSelection
    from refmod_h3.reference_diagnostic import JWTFRefModConditioningCheck
    from comfy_extras import nodes_custom_sampler
    from comfy_extras import nodes_model_advanced, nodes_slg
    from comfy_extras import nodes_images, nodes_post_processing
    from utility_core.smart_selection import JWTFSmartSelect, JWTFRegionCrop, JWTFRegionComposite
    from utility_core.mask_editor import JWTFMaskEditor
    from utility_core.image_compare import JWTFImageCompare

    result = dict(core.NODE_CLASS_MAPPINGS)
    for cls in (
        nodes_flux.FluxGuidance, nodes_lt.EmptyLTXVLatentVideo,
        nodes_lt.LTXVConditioning, nodes_lt.LTXVCropGuides,
        nodes_video.SaveWEBM, JWTFUnifiedRefModApply, JWTFUnifiedRefModBake,
        nodes_flux.EmptyFlux2LatentImage, JWTFReferenceAudition, JWTFSaveAuditionSelection,
        nodes_flux.Flux2Scheduler,
        nodes_lt.LTXVScheduler, nodes_slg.SkipLayerGuidanceDiTSimple,
        JWTFRefModConditioningCheck,
        nodes_images.GetImageSize, nodes_post_processing.ImageScaleToTotalPixels,
        JWTFSmartSelect, JWTFRegionCrop, JWTFRegionComposite, JWTFMaskEditor, JWTFImageCompare,
    ):
        result[cls.GET_SCHEMA().node_id] = cls
    result["PreviewAny"] = nodes_preview_any.PreviewAny
    for name in ("RandomNoise", "CFGGuider", "KSamplerSelect", "SamplerCustomAdvanced", "SplitSigmasDenoise", "BasicScheduler"):
        result[name] = getattr(nodes_custom_sampler, name)
    result["ModelSamplingFlux"] = nodes_model_advanced.ModelSamplingFlux
    return result


def input_spec(type_name: str) -> dict:
    if type_name == "MarkdownNote":
        return {"required": {"text": ("STRING", {"default": ""})}}
    return registry()[type_name].INPUT_TYPES()


def is_widget(spec) -> bool:
    kind, options = spec[0], spec[1] if len(spec) > 1 else {}
    return not options.get("forceInput") and (isinstance(kind, (list, tuple)) or str(kind) in PRIMITIVES)


def widgets(type_name: str, values: dict) -> dict:
    result = {}
    for section in ("required", "optional"):
        for name, spec in input_spec(type_name).get(section, {}).items():
            if not is_widget(spec):
                continue
            kind, options = spec[0], spec[1] if len(spec) > 1 else {}
            choices = kind if isinstance(kind, (list, tuple)) else options.get("options", [])
            fallback = choices[0] if choices else {"INT": 0, "FLOAT": 0.0, "BOOLEAN": False}.get(str(kind), "")
            result[name] = values.get(name, options.get("default", fallback))
            if options.get("control_after_generate"):
                result["control_after_generate"] = "fixed"
    unknown = set(values) - set(result)
    if unknown:
        raise ValueError(f"Unknown widgets on {type_name}: {sorted(unknown)}")
    return result


class Workflow:
    def __init__(self, name: str, family: str, purpose: str):
        self.name, self.family, self.purpose = name, family, purpose
        self.nodes, self.links, self.groups = [], [], []

    def node(self, type_name: str, title: str, x: int, y: int, values=None, width=360, height=220):
        values = values or {}
        inputs = []
        for section in ("required", "optional"):
            for name, spec in input_spec(type_name).get(section, {}).items():
                if is_widget(spec):
                    continue
                kind = str(spec[0])
                if kind.startswith("COMFY_"):
                    raise ValueError(f"Unsupported dynamic socket {type_name}.{name}: {kind}")
                socket = {"name": name, "type": kind, "link": None}
                if section == "optional":
                    socket["shape"] = 7
                inputs.append(socket)
        cls = registry().get(type_name)
        if cls is not None and hasattr(cls, "GET_SCHEMA"):
            schema = cls.GET_SCHEMA()
            output_types = cls.RETURN_TYPES
            output_names = [o.display_name or o.id or str(t) for o, t in zip(schema.outputs, output_types)]
        else:
            output_types = getattr(cls, "RETURN_TYPES", ())
            output_names = getattr(cls, "RETURN_NAMES", output_types)
        named = widgets(type_name, values)
        node = {
            "id": len(self.nodes) + 1, "type": type_name, "pos": [x, y], "size": [width, height],
            "flags": {"pinned": True} if type_name == "MarkdownNote" else {},
            "order": 0, "mode": 0, "inputs": inputs,
            "outputs": [{"name": str(n), "type": str(t), "links": None, "slot_index": i}
                        for i, (n, t) in enumerate(zip(output_names, output_types))],
            "title": title, "properties": {"Node name for S&R": type_name},
            "widgets_values": list(named.values()), "widgets_values_named": named,
        }
        self.nodes.append(node)
        return node

    def link(self, source: dict, output: int, target: dict, input_name: str):
        if not any(item["name"] == input_name for item in target["inputs"]):
            specs = input_spec(target["type"])
            spec = next((specs.get(section, {}).get(input_name) for section in ("required", "optional")
                         if input_name in specs.get(section, {})), None)
            if spec is None or not is_widget(spec):
                raise ValueError(f"Unknown input {target['type']}.{input_name}")
            kind = "COMBO" if isinstance(spec[0], (list, tuple)) else str(spec[0])
            target["inputs"].append({"name": input_name, "type": kind, "link": None, "widget": {"name": input_name}})
        slot = next(i for i, item in enumerate(target["inputs"]) if item["name"] == input_name)
        src, dst = source["outputs"][output], target["inputs"][slot]
        if dst["link"] is not None:
            raise ValueError(f"Input already connected: {target['title']}.{input_name}")
        if src["type"] != dst["type"] and "*" not in (src["type"], dst["type"]):
            raise ValueError(f"Type mismatch: {src['type']} → {dst['type']}")
        link_id = len(self.links) + 1
        dst["link"] = link_id
        src["links"] = (src["links"] or []) + [link_id]
        self.links.append([link_id, source["id"], output, target["id"], slot, src["type"]])

    def group(self, title, bounds, color="#49636b"):
        self.groups.append({"id": len(self.groups) + 1, "title": title, "bounding": bounds, "color": color, "flags": {}})

    def result(self):
        depths = {}
        def depth(node_id):
            if node_id not in depths:
                parents = [link[1] for link in self.links if link[3] == node_id]
                depths[node_id] = max((depth(p) + 1 for p in parents), default=0)
            return depths[node_id]
        ordered = sorted(self.nodes, key=lambda n: (depth(n["id"]), n["id"]))
        for order, node in enumerate(ordered):
            node["order"] = order
        return {
            "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"https://github.com/JezzWTF/jezzwtf-nodes/examples/{self.name}")),
            "revision": 0, "last_node_id": len(self.nodes), "last_link_id": len(self.links),
            "nodes": self.nodes, "links": self.links, "groups": self.groups, "config": {},
            "extra": {"ds": {"scale": 0.55, "offset": [30, 30]},
                      "jezzwtf_refmod_example": {"family": self.family, "purpose": self.purpose, "schema_version": 1}},
            "version": 0.4,
        }


def bake_example(ltx=False) -> Workflow:
    name = "RefMod_Bake_LTX_Guide" if ltx else "RefMod_Bake_Image_Families"
    family = "ltxv" if ltx else "moss_image"
    w = Workflow(name, family, "bake")
    image = w.node("LoadImage", "1 · Choose a reference image", 40, 90, {"image": "example.png"}, height=400)
    vae = w.node("CheckpointLoaderSimple" if ltx else "VAELoader", "2 · Load the matching checkpoint VAE" if ltx else "2 · Select the matching VAE", 40, 580,
                 {"ckpt_name": PRESETS["ltxv"][0]} if ltx else {"vae_name": "flux2-vae_small.safetensors"}, height=150 if ltx else 110)
    source = image
    if ltx:
        source = w.node("ImageScale", "Fit the guide to this example's 512×512 target", 460, 90,
                        {"upscale_method": "lanczos", "width": 512, "height": 512, "crop": "center"}, height=200)
        w.link(image, 0, source, "image")
    x = 860 if ltx else 470
    bake = w.node("JWTFUnifiedRefModBake", "3 · Bake the reusable reference bundle", x, 90,
                  {"model": family, "name": "example_character", "resolution": 0 if ltx else 1024,
                   "subfolder": "", "overwrite": False}, width=460, height=640)
    w.link(source, 0, bake, "images")
    w.link(vae, 2 if ltx else 0, bake, "vae")
    path = w.node("PreviewAny", "Saved bundle path", x + 520, 90, height=170)
    w.link(bake, 0, path, "source")
    note = (
        "# Bake a reference bundle\n\n"
        "1. Replace example.png with your own reference image and choose its matching VAE.\n"
        "2. Choose the model family in Image RefMod Bake. Each bundle belongs to that family and VAE.\n"
        "3. Queue once. The file is saved under models/refmods/<family>/example_character.safetensors.\n"
        "4. Open the corresponding RefMod Apply example, refresh node definitions (R) if needed, and choose the saved bundle. "
        "The picker uses family/example_character, without .safetensors.\n\n"
        "Overwrite is off. Enable it only when intentionally replacing an existing bundle. "
        "Connect image_2/image_3/image_4 for more references, within the selected family's limit.\n\n"
    )
    if ltx:
        note += "## LTX image guides\n\nThis example fixes the source at 512×512 and uses resolution=0 so the guide stays exactly that size. "
        note += "Use the VAE from ltx-video-2b-v0.9.5.safetensors (128 channels, 32× spatial compression), matching the companion Apply checkpoint. The target is 512×512. "
        note += "If you change dimensions, change both examples together. A guide must divide the target by the same integer on both axes. "
        note += "Bake one reference initially; extra guides consume additional attention and memory."
    else:
        note += "## Family choices\n\nUse this for Qwen 2.1, Fibo 2, Flux 3, Flux.2, Flux Kontext, MOSS or Krea 2. "
        note += "The default is MOSS-Image. Select the family BEFORE choosing the VAE. MOSS/Krea generation also needs a compatible edit LoRA. "
        note += "VAE choices: Qwen 2.1 uses qwen_image_2.1_vae_bf16; Fibo 2, Flux 3 and Flux.2 use flux2-vae; MOSS uses flux2-vae_small; Kontext uses ae; Krea2 uses qwen_image_vae. "
        note += "At resolution=1024, Fibo 2 and Kontext follow their native trained image-size policies. Non-default resolutions are custom experiments. "
        note += "For LTX use RefMod_Bake_LTX_Guide.json, which matches guide dimensions to its video target."
    w.node("MarkdownNote", "How it works · bake first", x + 520, 320, {"text": note}, width=520, height=610)
    w.group("1. Source and VAE", [20, 20, 400, 720])
    if ltx:
        w.group("2. Match guide dimensions", [440, 20, 380, 330])
    w.group("3. Bake", [x - 20, 20, 500, 750])
    w.group("4. Saved path and instructions", [x + 500, 20, 560, 940])
    return w


def apply_example(family: str) -> Workflow:
    slug, label, clip_type, cfg = FAMILIES[family]
    model_file, clip_file, vae_file, steps, scheduler = PRESETS[family]
    w = Workflow(f"RefMod_Apply_{slug}", family, "apply")
    ltx = family == "ltxv"
    edit = family in ("moss_image", "krea2")
    upstream = family in ("flux3", "flux2", "flux_kontext", "ltxv")
    instructions = (
        f"# {label} · use a saved RefMod\n\n"
        f"1. Run {'RefMod_Bake_LTX_Guide.json' if ltx else 'RefMod_Bake_Image_Families.json'} first, with model={family} and the matching VAE.\n"
        "2. The loaders name the exact checkpoint variant, text encoder and VAE this preset targets. Install those files or their matching precision variants.\n"
        f"3. In Image RefMod Apply, select {family}/example_character (or your own bundle). Model is auto (from refmod). "
        "Leaving the picker on None stops execution until a bundle is chosen. Refresh node definitions (R) after creating a bundle if it is not listed.\n"
        "4. Edit the prompt, then queue. References condition the result; identity, style and edit fidelity depend on the model and task.\n\n"
        "## Settings\n\nSampler values are starting points, not universal presets. Use the settings recommended for your exact checkpoint, especially for distilled models. "
        "Baked references must use the same VAE family as generation.\n\n"
    )
    if edit:
        instructions += "## Required edit LoRA\n\nChoose a compatible reference-image edit LoRA in the connected model-only LoRA loader. "
        instructions += "Set edit_format on Apply to match how it was trained: ai-toolkit uses isolated/cached references; ai-toolkit (kv_cache off) uses uncached references. "
        instructions += "Moss-Image-Edit is MOSS-only. "
        instructions += "Use a current ComfyUI build with this model family's reference conditioning.\n\n"
        if family == "moss_image":
            instructions += "This example uses ComfyUI's official moss_image_edit_lora_rank_64_bf16.safetensors, at strength 1.0, "
            instructions += "with edit_format=Moss-Image-Edit. Load it through the normal model-only LoRA loader. "
            instructions += "Do not use either ai-toolkit layout with that adapter. For an ai-toolkit-trained adapter, change both the file and edit_format to match its training. "
            instructions += "The official adapter is trained for instruction editing of the reference image; describe the change you want.\n\n"
        else:
            instructions += "The Krea example uses krea2_style_reference.safetensors and Krea2 style reference format, matching the official Turbo style-reference blueprint. "
            instructions += "Its prompt is a description of the new image in the reference's style, not a promise of character identity preservation.\n\n"
    if family == "flux2":
        instructions += "## Native Flux.2 schedule\n\nFlux2Scheduler supplies the sigma schedule to SamplerCustomAdvanced. "
        instructions += "Its width and height must match the explicit Empty Flux 2 target (1024×1024 initially). "
        instructions += "This graph targets Klein Base 4B: Qwen3-4B text encoder, Euler, 20 steps and CFG 5, matching ComfyUI's Base 4B edit template. "
        instructions += "CFG 1 disables classifier-free guidance and is not the Base preset. Distilled Klein and Flux.2 dev need their own model, text encoder and sampling settings. "
        instructions += "Use qwen_3_4b.safetensors for this setup; accepting another encoder's tensor dimensions does not verify the pairing.\n\n"
    if ltx:
        instructions += "## LTX video-only setup\n\nThis example uses the video-only ltx-video-2b-v0.9.5 checkpoint and its bundled VAE, with separate T5 encoding (CLIP type ltxv). "
        instructions += "Use the 512×512 guide from the companion bake example, encoded with the SAME checkpoint's VAE. The target has 49 frames at 24fps. latent_idx is in latent frames. "
        instructions += "LTXVScheduler uses 30 steps, max_shift=2.05, base_shift=0.95, stretch on and terminal=0.1. It reads the clean target's dimensions. "
        instructions += "The returned latent contains appended guide frames: LTXV Crop Guides MUST stay between sampling and decoding. "
        instructions += "The result is saved as a WebM video. LTXV Add Latent Guide must exist in your ComfyUI build.\n\n"
    elif family == "flux_kontext":
        instructions += "## Kontext models\n\nUse Flux.1 Kontext, its Flux VAE and both CLIP-L and T5 encoders. FluxGuidance sets guidance independently of the sampler's CFG=1.\n\n"
    instructions += "Optional: combine refmod_2/refmod_3 from the SAME family. ref_strength sets how long image references are active, not their pixel amplitude."
    w.node("MarkdownNote", "Setup required · select models and a saved bundle", 40, 80, {"text": instructions}, width=420, height=720)
    model = w.node("CheckpointLoaderSimple" if ltx else "UNETLoader", f"Load {label} {'checkpoint and VAE' if ltx else 'diffusion model'}", 40, 880,
                   {"ckpt_name": model_file} if ltx else {"unet_name": model_file, "weight_dtype": "default"}, height=150 if ltx else 120)
    if family == "flux_kontext":
        clip = w.node("DualCLIPLoader", "Load CLIP-L + T5", 40, 1050,
                      {"clip_name1": "clip_l.safetensors", "clip_name2": "t5xxl_fp8_e4m3fn_scaled.safetensors", "type": "flux", "device": "default"}, height=170)
    else:
        clip = w.node("CLIPLoader", f"Load {label} text encoder", 40, 1050,
                      {"clip_name": clip_file, "type": clip_type, "device": "default"}, height=150)
    vae = model if ltx else w.node("VAELoader", "Load matching VAE", 40, 1280, {"vae_name": vae_file}, height=100)
    vae_slot = 2 if ltx else 0
    model_source = model
    if edit:
        model_source = w.node("LoraLoaderModelOnly", "Required · choose the reference-image edit LoRA", 500, 880,
                              {"lora_name": "moss_image_edit_lora_rank_64_bf16.safetensors" if family == "moss_image" else "krea2_style_reference.safetensors", "strength_model": 1.0}, width=380, height=160)
        w.link(model, 0, model_source, "model")
    if family == "moss_image":
        patched = w.node("SkipLayerGuidanceDiTSimple", "MOSS official edit preset · layer 22", 500, 1130,
                         {"double_layers": "", "single_layers": "22", "start_percent": 0.0, "end_percent": 1.0}, width=380, height=170)
        w.link(model_source, 0, patched, "model")
        model_source = patched
    if family == "krea2":
        patched = w.node("ModelSamplingFlux", "Krea Turbo shift · fixed 1024×1024 target", 500, 1130,
                         {"max_shift": 1.15, "base_shift": 0.5, "width": 1024, "height": 1024}, width=380, height=220)
        w.link(model_source, 0, patched, "model")
        model_source = patched
    prompt = "A portrait of the reference character in a sunlit greenhouse, natural light, detailed clothing."
    if ltx:
        prompt = "The reference character turns toward the camera in a sunlit greenhouse, gentle natural movement, steady camera."
    elif family in ("qwen21", "fibo2", "moss_image"):
        prompt = "Change the background to a sunlit greenhouse. Keep the subject's face, hairstyle and clothing unchanged."
    elif family == "krea2":
        prompt = "A small horned yeti reading a book in a sunlit greenhouse, in the visual style of the reference image."
    positive = negative = None
    if upstream:
        positive = w.node("CLIPTextEncode", "Prompt · describe the new scene", 500, 80, {"text": prompt}, width=380, height=270)
        negative = w.node("CLIPTextEncode", "Negative prompt", 500, 420, {"text": "blur, distortion, low quality" if ltx else ""}, width=380, height=220)
        w.link(clip, 0, positive, "clip")
        w.link(clip, 0, negative, "clip")
    if family == "flux_kontext":
        guidance = w.node("FluxGuidance", "Flux guidance", 500, 710, {"guidance": 2.5}, width=380, height=100)
        w.link(positive, 0, guidance, "conditioning")
        positive = guidance
    apply_x = 1350 if ltx else 940
    apply = w.node("JWTFUnifiedRefModApply", f"Choose your saved {label} RefMod", apply_x, 80,
                   {"model": "auto (from refmod)", "refmod_1": "None", "prompt": "" if upstream else prompt,
                    "negative_prompt": "blur, distortion, low quality" if family == "moss_image" else "",
                    "edit_format": "Moss-Image-Edit" if family == "moss_image" else "Krea2 style reference" if family == "krea2" else "ai-toolkit (kv_cache off)", "ref_strength": 1.0,
                    "latent_idx": 0, "guide_strength": 0.8}, width=470, height=1050)
    if upstream:
        if ltx:
            fps = w.node("LTXVConditioning", "24 fps conditioning", 940, 80, {"frame_rate": 24}, width=330, height=160)
            w.link(positive, 0, fps, "positive")
            w.link(negative, 0, fps, "negative")
            w.link(fps, 0, apply, "positive")
            w.link(fps, 1, apply, "negative")
            latent = w.node("EmptyLTXVLatentVideo", "512×512 · 49-frame target", 940, 360,
                            {"width": 512, "height": 512, "length": 49, "batch_size": 1}, width=330, height=220)
            w.link(latent, 0, apply, "latent_in")
            w.link(vae, vae_slot, apply, "vae")
        else:
            w.link(positive, 0, apply, "positive")
            w.link(negative, 0, apply, "negative")
    else:
        w.link(clip, 0, apply, "clip")
    sample_x = apply_x + 530
    advanced = family in ("flux2", "ltxv")
    if not advanced:
        sampler = w.node("KSampler", "Sample with the saved references", sample_x, 80,
                         {"seed": 42, "steps": steps, "cfg": cfg, "sampler_name": "euler", "scheduler": scheduler, "denoise": 1.0}, height=500)
        w.link(model_source, 0, sampler, "model")
        w.link(apply, 0, sampler, "positive")
        w.link(apply, 1, sampler, "negative")
        if family == "krea2":
            target = w.node("EmptyLatentImage", "Krea fixed style-transfer target · 1024×1024", 500, 620,
                            {"width": 1024, "height": 1024, "batch_size": 1}, width=380, height=180)
            w.link(target, 0, sampler, "latent_image")
        else:
            w.link(apply, 2, sampler, "latent_image")
    else:
        # Flux2's native schedule depends on output size and step count.
        target = latent if ltx else w.node("EmptyFlux2LatentImage", "Fixed target · match Flux2Scheduler dimensions", 500, 780,
                                         {"width": 1024, "height": 1024, "batch_size": 1}, width=380, height=200)
        noise = w.node("RandomNoise", "Fixed seed", sample_x, 80, {"noise_seed": 42}, height=130)
        guider = w.node("CFGGuider", "Flux.2 guidance", sample_x, 290, {"cfg": cfg}, height=180)
        algorithm = w.node("KSamplerSelect", "Euler", sample_x, 550, {"sampler_name": "euler"}, height=100)
        schedule = w.node("LTXVScheduler" if ltx else "Flux2Scheduler", "LTX video schedule" if ltx else "Flux.2 schedule · match target dimensions", sample_x, 730,
                          {"steps": steps, "max_shift": 2.05, "base_shift": 0.95, "stretch": True, "terminal": 0.1} if ltx else {"steps": steps, "width": 1024, "height": 1024}, height=240)
        if ltx:
            w.link(target, 0, schedule, "latent")
        sampler = w.node("SamplerCustomAdvanced", "Sample with native model schedule", sample_x + 420, 80, height=280)
        w.link(model_source, 0, guider, "model")
        w.link(apply, 0, guider, "positive")
        w.link(apply, 1, guider, "negative")
        for source, field in ((noise, "noise"), (guider, "guider"), (algorithm, "sampler"), (schedule, "sigmas")):
            w.link(source, 0, sampler, field)
        w.link(apply if ltx else target, 2 if ltx else 0, sampler, "latent_image")
    sampled = sampler
    decode_x = sample_x + (840 if advanced else 420)
    if ltx:
        sampled = w.node("LTXVCropGuides", "Remove appended guide frames before decode", decode_x, 80, width=340, height=200)
        w.link(apply, 0, sampled, "positive")
        w.link(apply, 1, sampled, "negative")
        w.link(sampler, 0, sampled, "latent")
        decode_x += 400
    decode = w.node("VAEDecode", "Decode the generated result", decode_x, 80, width=300, height=150)
    w.link(sampled, 2 if ltx else 0, decode, "samples")
    w.link(vae, vae_slot, decode, "vae")
    save_type = "SaveWEBM" if ltx else "SaveImage"
    settings = {"filename_prefix": f"refmods/{family}"}
    if ltx:
        settings.update(codec="vp9", fps=24, crf=24)
    save = w.node(save_type, "Save WebM video" if ltx else "Save image", decode_x + 370, 80, settings, width=400, height=500)
    w.link(decode, 0, save, "images")
    w.group("1. Setup and matching model components", [20, 20, 460, 1410])
    w.group("2. Conditioning and edit LoRA" if edit else "2. Prompt conditioning", [480, 20, 420, 1370 if edit else 1110])
    if ltx:
        w.group("3. Video target and frame rate", [920, 20, 370, 620])
    w.group("4. Apply the saved references", [apply_x - 20, 20, 510, 1150])
    w.group("5. Sample", [sample_x - 20, 20, 820 if advanced else 400, 1030 if advanced else 610])
    w.group("6. Crop guides, decode and save" if ltx else "6. Decode and save",
            [decode_x - 20, 20, 830, 650])
    return w


def smart_selection_example(refine=False) -> Workflow:
    name = "Smart_Select_Face_Refine_Flux_2" if refine else "Smart_Select_Mask_Editor"
    w = Workflow(name, "flux2" if refine else "wevisone", "smart_face_refine" if refine else "smart_selection")
    text = (
        "# Smart selection with native WeVisOne\n\n"
        "Choose an image and install/select wevisone_vl_2b_int8_convrot.safetensors from Comfy-Org/WeVisOne-VL. "
        "CLIPLoader uses stable_diffusion as its type: current core auto-detects the WeVisOne architecture from the weights. "
        "This is a perception model, not the generator's text encoder.\n\n"
        "Smart Select can select face, person, hair or other descriptions. Segmentation returns alpha mattes; detection returns rectangular masks. "
        "Largest selects one match per image. Index uses the native detector's zero-based order; inspect the report when several subjects match. "
        "All keeps every match. No match yields an empty mask and no boxes; Region Crop stops rather than silently refining the whole image.\n\n"
        "Mask Editor lets you correct the incoming selection after a first run. A saved painting overrides the incoming mask until Use input mask is clicked. Clear saves an all-black painting. "
        "If painting outside a selected box, disconnect the boxes from Region Crop to derive the crop bounds from the edited mask instead.\n\n"
    )
    if refine:
        text += (
            "# Face-region refinement\n\n"
            "Select a Flux.2 reference bundle and matching Klein Base 4B components, including the matching VAE. The original scene prompt guides refinement. "
            "The selected face is padded and enlarged to a 768-pixel long edge on a 16-pixel grid. "
            "Its VAE-encoded pixels feed the sampler; references remain active throughout. "
            "The whole padded crop is sampled. The soft selection mask is applied only at pasteback: "
            "using that fractional matte as a latent noise mask repeatedly suppresses changes during sampling. "
            "Denoise 0.20 is a conservative redraw, not guaranteed restoration. Compare the crop at working resolution. "
            "0.35 produces stronger changes but can alter facial features or tattoo details.\n\n"
            "Region Composite restores the crop's original size and blends it into the SAME original source image. "
            "The output stays at the source image's resolution. Only the chosen frame/region is changed; other pixels and alpha are preserved. "
            "Use an enlarged input first if you also want the whole output at a higher resolution. "
            "Inspect the mask, crop and before/after comparison; face detection is not identity recognition and refinement cannot guarantee exact identity."
        )
    w.node("MarkdownNote", "Setup and selection behaviour", 40, 40, {"text": text}, width=560, height=840)
    image = w.node("LoadImage", "Source image", 40, 960, {"image": "example.png"}, width=450, height=500)
    vision = w.node("CLIPLoader", "WeVisOne perception model - separate from generator CLIP", 40, 1550,
                    {"clip_name": "wevisone_vl_2b_int8_convrot.safetensors", "type": "stable_diffusion", "device": "default"}, width=450, height=160)
    selection = w.node("JWTFSmartSelect", "Describe the region to select", 680, 40,
                       {"query": "face" if refine else "person", "task": "segmentation", "selection": "largest"}, width=430, height=310)
    w.link(vision, 0, selection, "clip")
    w.link(image, 0, selection, "images")
    editor = w.node("JWTFMaskEditor", "Review or correct the incoming mask", 1180, 40, width=650, height=700)
    w.link(image, 0, editor, "images")
    w.link(selection, 0, editor, "mask")
    report = w.node("PreviewAny", "Detection and selection report", 680, 440, width=440, height=400)
    w.link(selection, 2, report, "source")
    if not refine:
        mask_preview = w.node("PreviewImage", "Selected alpha matte", 1900, 40, width=520, height=650)
        w.link(editor, 2, mask_preview, "images")
        return w
    crop = w.node("JWTFRegionCrop", "Enlarge the selected face with context", 1900, 40,
                  {"padding": .25, "long_edge": 768}, width=400, height=240)
    w.link(image, 0, crop, "images")
    w.link(selection, 1, crop, "bboxes")
    w.link(editor, 1, crop, "mask")
    preview = w.node("PreviewImage", "Crop to be refined", 1900, 380, width=450, height=520)
    w.link(crop, 0, preview, "images")
    model = w.node("UNETLoader", "Flux.2 Klein Base 4B", 680, 980,
                   {"unet_name": PRESETS["flux2"][0], "weight_dtype": "default"}, height=120)
    clip = w.node("CLIPLoader", "Generation text encoder", 680, 1190,
                  {"clip_name": PRESETS["flux2"][1], "type": "flux2", "device": "default"}, height=160)
    vae = w.node("VAELoader", "Matching VAE for crop encoding and decode", 680, 1440,
                 {"vae_name": PRESETS["flux2"][2]}, height=120)
    positive = w.node("CLIPTextEncode", "Original scene prompt and desired face detail", 1180, 860,
                      {"text": "A natural photograph of the person shown in the reference images, seated at a cafe table in a blue shirt, holding a coffee cup. Preserve the facial features, expression and facial markings, with natural skin and beard texture."}, width=500, height=240)
    negative = w.node("CLIPTextEncode", "Negative", 1180, 1190, {"text": ""}, width=440, height=150)
    w.link(clip, 0, positive, "clip")
    w.link(clip, 0, negative, "clip")
    apply = w.node("JWTFUnifiedRefModApply", "Saved references for the person", 2400, 40,
                   {"model": "auto (from refmod)", "refmod_1": "None", "ref_strength": 1.0, "ref_on_negative": True}, width=450, height=900)
    w.link(positive, 0, apply, "positive")
    w.link(negative, 0, apply, "negative")
    encoded = w.node("VAEEncode", "Encode the actual face crop", 1900, 1000, height=130)
    w.link(crop, 0, encoded, "pixels")
    w.link(vae, 0, encoded, "vae")
    size = w.node("GetImageSize", "Actual crop dimensions", 1900, 1230, height=130)
    w.link(crop, 0, size, "image")
    schedule = w.node("Flux2Scheduler", "Size-aware full schedule", 2920, 980, {"steps": 100, "width": 768, "height": 768}, height=230)
    w.link(size, 0, schedule, "width")
    w.link(size, 1, schedule, "height")
    split = w.node("SplitSigmasDenoise", "Low-noise refinement strength", 2920, 1300, {"denoise": .20}, height=130)
    w.link(schedule, 0, split, "sigmas")
    noise = w.node("RandomNoise", "Refinement seed", 2920, 40, {"noise_seed": 7}, height=120)
    algorithm = w.node("KSamplerSelect", "Euler", 2920, 230, {"sampler_name": "euler"}, height=110)
    guider = w.node("CFGGuider", "Reference-conditioned face refinement", 2920, 430, {"cfg": 5.0}, height=180)
    w.link(model, 0, guider, "model")
    w.link(apply, 0, guider, "positive")
    w.link(apply, 1, guider, "negative")
    sampler = w.node("SamplerCustomAdvanced", "Refine crop pixels", 3370, 40, height=280)
    for source, slot, field in ((noise, 0, "noise"), (algorithm, 0, "sampler"), (guider, 0, "guider"),
                                (split, 1, "sigmas"), (encoded, 0, "latent_image")):
        w.link(source, slot, sampler, field)
    decode = w.node("VAEDecode", "Decode refined face", 3370, 440, height=130)
    w.link(sampler, 0, decode, "samples")
    w.link(vae, 0, decode, "vae")
    crop_compare = w.node("JWTFImageCompare", "Enlarged input versus sampled crop - inspect actual detail", 3370, 1250, width=650, height=750)
    w.link(crop, 0, crop_compare, "image_a")
    w.link(decode, 0, crop_compare, "image_b")
    composite = w.node("JWTFRegionComposite", "Blend back into the original image", 3810, 40,
                       {"feather": 16, "opacity": 1.0}, width=440, height=200)
    w.link(image, 0, composite, "images")
    w.link(crop, 2, composite, "region")
    w.link(decode, 0, composite, "refined_crop")
    save = w.node("SaveImage", "Save region-refined image", 4330, 40,
                  {"filename_prefix": "refmods/face_refine"}, width=450, height=600)
    w.link(composite, 0, save, "images")
    compare = w.node("JWTFImageCompare", "Original versus face-refined", 3810, 430, width=650, height=650)
    w.link(image, 0, compare, "image_a")
    w.link(composite, 0, compare, "image_b")
    return w


def refmod_upscale_example(family: str, variant: str = "base") -> Workflow:
    if family not in ("flux2", "flux3"):
        raise ValueError("The refinement examples currently cover Flux.2 and Flux 3")
    flux2 = family == "flux2"
    if variant not in ("base", "distilled") or (flux2 and variant != "base"):
        raise ValueError("Choose the matching Base or Flux 3 Distilled refinement preset")
    distilled = variant == "distilled"
    slug = "Flux_2" if flux2 else "Flux_3"
    if distilled:
        slug += "_Distilled"
    model_file, clip_file, vae_file, _, _ = PRESETS[family]
    if distilled:
        model_file = "flux3-image-klein-int8-convrot.safetensors"
    w = Workflow("RefMod_Upscale_Refine_" + slug, family, "upscale_refine")
    note = (
        "# Upscale and refine with the same references\n\n"
        "1. Select an already-generated image in Load Image. Use its original scene prompt in the positive text node.\n"
        "2. Select the SAME person's saved bundle for this model family, and the matching VAE, model and encoder. "
        "Do not use a Flux.2 bundle with Flux 3; bake a separate bundle from the source photos for that family.\n"
        "3. Start with 1.69 megapixels: approximately 1536x1152 for a 1024x768 source. Aspect ratio is retained and dimensions round to a 16-pixel grid. "
        "This is a target pixel area, so smaller inputs get enlarged more. Keep the target larger than your input.\n"
        "4. Denoise starts at 0.20. Lower it to preserve the generated face/composition more closely; raise cautiously toward 0.30 for stronger redraw. "
        "RefMod references remain active throughout the refinement. The sampler receives the VAE-encoded upscaled IMAGE, not an empty latent.\n\n"
        "Lanczos provides the initial enlargement without a required external upscaler. The diffusion pass synthesizes detail; "
        "it does not recover guaranteed original skin, beard or tattoo detail. Compare identity as well as texture. "
        "If the face occupies only a small part of a wide shot, a targeted face-crop refinement may be more effective than whole-image enlargement.\n\n"
    )
    note += (
        "Flux.2 Klein Base 4B uses Qwen3-4B, CFG 5 and a size-aware Flux2Scheduler. "
        "The 100-step schedule feeds SplitSigmasDenoise at 0.20; its LOW sigma output keeps the last 20 refinement steps. "
        "If changing this fraction, the executed step count changes too. Output width/height are wired from the resized image automatically."
        if flux2 else (
        "This graph targets flux3-image-klein-int8-convrot.safetensors, the DISTILLED checkpoint, with its named encoder, "
        "Euler/simple, CFG 1, 16 refinement steps and BasicScheduler denoise 0.20. This low-denoise refinement preset "
        "still needs generation validation with the installed distilled weights. "
        "Use a complete scene caption; the official normal-generation preset is 16 steps with no CFG guidance."
        if distilled else
        "This graph targets Flux 3 Klein Base, its named encoder, Euler/simple, CFG 1, 20 refinement steps and BasicScheduler denoise 0.20. "
        "It is a separate family-specific example; do not assume distilled or other variants use the Base settings."
        )
    )
    w.node("MarkdownNote", "Setup, refinement strength and limits", 40, 40, {"text": note}, width=600, height=800)
    image = w.node("LoadImage", "Generated image to enlarge", 40, 930, {"image": "example.png"}, width=460, height=430)
    scale = w.node("ImageScaleToTotalPixels", "Target area - about 1.5x a 1024x768 image", 710, 40,
                   {"upscale_method": "lanczos", "megapixels": 1.69, "resolution_steps": 16}, width=400, height=180)
    w.link(image, 0, scale, "image")
    model = w.node("UNETLoader", "Matching model", 40, 1440, {"unet_name": model_file, "weight_dtype": "default"}, height=120)
    clip = w.node("CLIPLoader", "Matching text encoder", 40, 1630,
                  {"clip_name": clip_file, "type": FAMILIES[family][2], "device": "default"}, height=160)
    vae = w.node("VAELoader", "Matching VAE - encode and decode", 40, 1870, {"vae_name": vae_file}, height=120)
    positive = w.node("CLIPTextEncode", "Use the original scene prompt", 710, 330,
                      {"text": "A natural photograph of the person shown in the reference images, seated at a wooden cafe table beside a large window. The person wears a blue linen shirt and holds a white coffee cup with both hands. The composition is a waist-up three-quarter view with the hands and cup clearly visible. Warm window light falls across the face and shirt, with softly blurred chairs, hanging lamps and other tables in the background. Skin has natural texture, and facial features and markings follow the reference person."}, width=430, height=280)
    negative = w.node("CLIPTextEncode", "Negative", 710, 640, {"text": ""}, width=430, height=180)
    w.link(clip, 0, positive, "clip")
    w.link(clip, 0, negative, "clip")
    apply = w.node("JWTFUnifiedRefModApply", "Same saved person references", 1210, 40,
                   {"model": "auto (from refmod)", "refmod_1": "None", "ref_strength": 1.0, "ref_on_negative": True}, width=460, height=850)
    w.link(positive, 0, apply, "positive")
    w.link(negative, 0, apply, "negative")
    encoded = w.node("VAEEncode", "Encode the enlarged generated image", 1210, 1020, width=410, height=140)
    w.link(scale, 0, encoded, "pixels")
    w.link(vae, 0, encoded, "vae")
    noise = w.node("RandomNoise", "Refinement seed", 1740, 40, {"noise_seed": 7}, height=120)
    guider = w.node("CFGGuider", "Reference-conditioned refinement", 1740, 240, {"cfg": 5.0 if flux2 else 1.0}, height=180)
    w.link(model, 0, guider, "model")
    w.link(apply, 0, guider, "positive")
    w.link(apply, 1, guider, "negative")
    algorithm = w.node("KSamplerSelect", "Euler", 1740, 500, {"sampler_name": "euler"}, height=100)
    if flux2:
        size = w.node("GetImageSize", "Actual enlarged dimensions", 710, 1020, width=360, height=130)
        w.link(scale, 0, size, "image")
        schedule = w.node("Flux2Scheduler", "Full schedule - dimensions follow the image", 1740, 680,
                          {"steps": 100, "width": 1536, "height": 1152}, height=230)
        w.link(size, 0, schedule, "width")
        w.link(size, 1, schedule, "height")
        split = w.node("SplitSigmasDenoise", "Refinement strength - LOW sigmas output", 1740, 1000, {"denoise": 0.20}, height=140)
        w.link(schedule, 0, split, "sigmas")
        sigmas, sigma_slot = split, 1
    else:
        schedule = w.node("BasicScheduler", "Refinement strength and steps", 1740, 680,
                          {"scheduler": "simple", "steps": 16 if distilled else 20, "denoise": 0.20}, height=220)
        w.link(model, 0, schedule, "model")
        sigmas, sigma_slot = schedule, 0
    sampler = w.node("SamplerCustomAdvanced", "Refine the enlarged image with RefMod", 2190, 40, width=420, height=330)
    for source, slot, field in ((noise, 0, "noise"), (guider, 0, "guider"), (algorithm, 0, "sampler"),
                                (sigmas, sigma_slot, "sigmas"), (encoded, 0, "latent_image")):
        w.link(source, slot, sampler, field)
    decode = w.node("VAEDecode", "Decode refinement", 2680, 40, width=330, height=130)
    w.link(sampler, 0, decode, "samples")
    w.link(vae, 0, decode, "vae")
    save = w.node("SaveImage", "Refined result", 3080, 40, {"filename_prefix": "refmods/upscale_refine/" + family}, width=440, height=620)
    w.link(decode, 0, save, "images")
    baseline = w.node("PreviewImage", "Before diffusion - enlarged input", 2680, 830, width=520, height=630)
    w.link(scale, 0, baseline, "images")
    return w


def character_scene_example() -> Workflow:
    # Reuse the checked Klein Base components and sampling path, with an
    # explicit output canvas and a task that changes more than the background.
    w = apply_example("flux2")
    from refmod_h3.reference_diagnostic import NEW_SCENE_PROMPT
    w.name = "RefMod_Character_New_Scene_Flux_2"
    w.purpose = "character_new_scene"
    for node in w.nodes:
        named = node["widgets_values_named"]
        if node["type"] == "CLIPTextEncode" and named["text"]:
            named["text"] = NEW_SCENE_PROMPT
            node["title"] = "Describe a new pose, composition, clothing and setting"
        elif node["type"] in ("EmptyFlux2LatentImage", "Flux2Scheduler"):
            named.update(width=1024, height=768)
            node["title"] = "Independent 1024x768 output canvas" if node["type"] == "EmptyFlux2LatentImage" else "Flux.2 schedule - matches 1024x768 target"
        elif node["type"] == "SaveImage":
            named["filename_prefix"] = "refmods/character_new_scene"
        elif node["type"] == "MarkdownNote":
            named["text"] = (
                "# Reference person in a new scene - Flux.2 Klein Base 4B\n\n"
                "Choose a saved Flux.2 bundle in Image RefMod Apply. For the SAME reference photos saved for another family, "
                "bake a separate Flux.2 bundle with flux2-vae.safetensors first; family labels do not convert latents. "
                "Use the named model, qwen_3_4b encoder and matching VAE in this graph. No edit LoRA is needed for this preset.\n\n"
                "The reference supplies appearance; the prompt describes a new full-body pose, outfit, camera view and environment. "
                "The output starts from a separate empty 1024x768 canvas, not from the reference pixels. "
                "Change the target width/height AND Flux2Scheduler dimensions together.\n\n"
                "This exact model/sampling path was checked with a saved portrait in full-weight generation. "
                "That is a starting example, not a guarantee of exact identity for every person, seed or scene. "
                "Inspect facial identity as well as whether the requested composition changed. "
                "The bundle is a reusable collection of references; it adds no identity-training capability beyond the underlying model.\n\n"
                "Sampling: Klein Base 4B, seed 42, Euler, 20-step Flux2Scheduler, CFG 5. "
                "Do not substitute distilled Klein or Flux.2 dev without updating their model components and sampling."
            )
        node["widgets_values"] = list(named.values())
    return w


def moss_diagnostic_example() -> Workflow:
    w = Workflow("RefMod_Diagnose_MOSS_Image", "moss_image", "diagnose")
    note = (
        "# MOSS: saved reference versus native editing\n\n"
        "Select your installed model, encoder, edit LoRA and matching VAE, then choose your EXISTING MOSS bundle. "
        "No source upload, export or rebake is required. Restart ComfyUI after updating the pack to load RefMod Conditioning Check.\n\n"
        "Queue once to render A (saved reference latents) and B (native MOSS encoding of the RGB references stored inside the same bundle). "
        "Both samplers share one LoRA-patched model, prompt, negative, format, seed, schedule and empty 1024x768 target. "
        "Output dimensions are independent of reference dimensions and are controlled on the check node. "
        "All references are used at full schedule strength on positive and negative. The reference preview shows the first image only.\n\n"
        "The report shows saved/fresh latent shapes and differences. Small differences can arise from 8-bit stored RGB. "
        "A different VAE can create larger differences. These numbers do not measure generation quality.\n\n"
        "If A fails and B works, investigate the saved bundle, bake settings and VAE. If both fail, the native path reproduces the failure too: "
        "investigate model capability, model/adapter loading and runtime. This workflow does not claim a fix.\n\n"
        "The defaults use stock MOSS SFT. To isolate a modified checkpoint, run with that checkpoint first, then change only the shared model to stock SFT. "
        "The default prompt requests the reference person full-body, walking sideways in a red coat at a snowy station, with a wide camera view. "
        "Check identity AND the new pose, clothing, framing and setting. A background swap around the original portrait is a failure for this task. "
        "Change the prompt once on the check node to update both branches. "
        "Results save under output/refmod_diagnostic/A_saved and B_native. Two renders are performed per queue."
    )
    w.node("MarkdownNote", "Setup and interpretation", 40, 40, {"text": note}, width=650, height=750)
    model = w.node("UNETLoader", "Shared diffusion model", 40, 850,
                   {"unet_name": PRESETS["moss_image"][0], "weight_dtype": "default"}, height=120)
    clip = w.node("CLIPLoader", "Shared text encoder", 40, 1030,
                  {"clip_name": PRESETS["moss_image"][1], "type": "moss_image", "device": "default"}, height=160)
    vae = w.node("VAELoader", "Matching VAE: native encoding and both decoders", 40, 1260,
                 {"vae_name": PRESETS["moss_image"][2]}, height=120)
    lora = w.node("LoraLoaderModelOnly", "Shared edit LoRA", 740, 850,
                  {"lora_name": "moss_image_edit_lora_rank_64_bf16.safetensors", "strength_model": 1.0}, height=160)
    patch = w.node("SkipLayerGuidanceDiTSimple", "Shared layer 22 guidance", 740, 1090,
                   {"double_layers": "", "single_layers": "22", "start_percent": 0.0, "end_percent": 1.0}, height=180)
    w.link(model, 0, lora, "model")
    w.link(lora, 0, patch, "model")
    check = w.node("JWTFRefModConditioningCheck", "Choose existing bundle and enter one edit instruction", 740, 40,
                   {"refmod": "None"}, width=470, height=650)
    w.link(clip, 0, check, "clip")
    w.link(vae, 0, check, "vae")
    preview = w.node("PreviewImage", "First stored reference", 1270, 40, width=420, height=500)
    report = w.node("PreviewAny", "Saved versus freshly encoded reference report", 1270, 650, width=530, height=550)
    w.link(check, 5, preview, "images")
    w.link(check, 6, report, "source")
    for label, y, pos, neg in (("A_saved", 40, 0, 1), ("B_native", 800, 2, 3)):
        sampler = w.node("KSampler", label + " - same seed and settings", 1870, y,
                         {"seed": 42, "steps": 30, "cfg": 4.0, "sampler_name": "euler", "scheduler": "normal", "denoise": 1.0}, height=430)
        w.link(patch, 0, sampler, "model")
        w.link(check, pos, sampler, "positive")
        w.link(check, neg, sampler, "negative")
        w.link(check, 4, sampler, "latent_image")
        decode = w.node("VAEDecode", label + " - decode", 2300, y, width=300, height=150)
        w.link(sampler, 0, decode, "samples")
        w.link(vae, 0, decode, "vae")
        save = w.node("SaveImage", label + " result", 2670, y,
                      {"filename_prefix": "refmod_diagnostic/" + label}, width=420, height=600)
        w.link(decode, 0, save, "images")
    return w


def audition_example() -> Workflow:
    w = Workflow("RefMod_Reference_Audition", "flux2", "audition")
    note = (
        "# Reference Audition · controlled reference comparisons\n\n"
        "1. Bake a Flux.2 bundle with 2–4 reference images using RefMod_Bake_Image_Families.json and its matching VAE. "
        "Choose flux2 BEFORE baking. This graph targets Klein Base 4B with its Qwen3-4B text encoder and Flux.2 VAE.\n"
        "2. Choose that saved bundle in Reference Audition. None intentionally stops execution until you choose one. "
        "Edit the positive/negative text nodes. Do not apply references upstream.\n"
        "3. Queue once. The first row uses every reference; subsequent rows omit one reference each. "
        "The seed, prompt, 512×512 target and sampler settings stay fixed. Flux2Scheduler is connected to sigmas; its steps override Audition's steps, scheduler and denoise widgets. "
        "Keep scheduler dimensions matched to the target. The Base preset uses 20 steps and CFG 5; CFG 1 disables classifier-free guidance. Five renders and a 120s soft budget are starting limits. "
        "An in-flight render finishes before the time budget is checked; skipped reference numbers appear in the report.\n"
        "4. Inspect the contact sheet. Change measures influence, NOT improvement, identity accuracy or quality. "
        "For example, compare the baseline against Without reference 2 to see what reference 2 contributes.\n"
        "5. Enter references to KEEP in Save Audition Selection, e.g. 1,3. Numbering follows the original bake order. "
        "Choose a new name, enable save, then queue again. With ComfyUI's upstream cache retained, only the saver runs. "
        "Keep seed fixed. The source bundle is preserved; overwrite is off.\n\n"
        "## Other families\n\nThis example is wired for Flux.2. To adapt it, replace the model components AND target latent together. "
        "Qwen/Fibo/MOSS/Krea need clip and the Audition prompt widgets; remove the upstream positive/negative connections and enter the prompt inside Audition. Flux uses the wired text conditions. Replace/disconnect Flux2Scheduler when moving to another family. "
        "The official MOSS adapter needs Moss-Image-Edit; the official Krea style adapter needs Krea2 style reference. Set CFG, steps and model patches for that family as in its Apply example. "
        "MOSS/Krea also need a matching edit LoRA. LTX needs clean video conditioning and a video target; use Euler. Audition fixes target noise and crops guides before decoding. "
        "H3 bundles appear as H3: <name> and need H3 prompt conditioning and a plain video target; split nested AV first. "
        "Video previews show first/middle/last frames; audio is not auditioned.\n\n"
        "Use production checkpoint settings for a final comparison. Low-step trials are for screening; findings can change with the scene and seed."
    )
    w.node("MarkdownNote", "Setup · read before queueing", 40, 60, {"text": note}, width=460, height=1000)
    model = w.node("UNETLoader", "Load Flux.2 Klein Base 4B", 40, 1160, {"unet_name": "flux-2-klein-base-4b.safetensors", "weight_dtype": "default"}, width=420, height=120)
    clip = w.node("CLIPLoader", "Load Klein Qwen3-4B text encoder", 40, 1360, {"clip_name": "qwen_3_4b.safetensors", "type": "flux2", "device": "default"}, width=420, height=160)
    vae = w.node("VAELoader", "Load matching Flux.2 VAE", 40, 1600, {"vae_name": "YOUR_FLUX2_VAE.safetensors"}, width=420, height=100)
    pos = w.node("CLIPTextEncode", "Prompt held fixed in every trial", 560, 60, {"text": "A portrait of the reference character in a sunlit greenhouse, natural light, detailed clothing."}, width=400, height=280)
    neg = w.node("CLIPTextEncode", "Negative prompt held fixed", 560, 420, {"text": ""}, width=400, height=220)
    w.link(clip, 0, pos, "clip")
    w.link(clip, 0, neg, "clip")
    latent = w.node("EmptyFlux2LatentImage", "Fixed 512×512 target · batch one", 560, 740, {"width": 512, "height": 512, "batch_size": 1}, width=400, height=200)
    audition = w.node("JWTFReferenceAudition", "All references vs individual omissions", 1040, 60,
                      {"refmod": "None", "seed": 42, "steps": 20, "cfg": 5, "max_renders": 5, "time_budget_seconds": 120}, width=500, height=1100)
    for source, output, field in ((model, 0, "model"), (vae, 0, "vae"), (latent, 0, "latent_image"), (pos, 0, "positive"), (neg, 0, "negative")):
        w.link(source, output, audition, field)
    preview = w.node("PreviewImage", "Compare labeled contact sheet", 1620, 60, width=650, height=900)
    w.link(audition, 0, preview, "images")
    report = w.node("PreviewAny", "Tested / skipped omissions and influence", 1620, 1060, width=650, height=420)
    w.link(audition, 2, report, "source")
    save = w.node("JWTFSaveAuditionSelection", "Choose refs to KEEP · save off initially", 2350, 60,
                  {"keep_refs": "all", "name": "audition_selection", "save": False, "overwrite": False}, width=440, height=320)
    w.link(audition, 1, save, "audition")
    schedule = w.node("Flux2Scheduler", "Flux.2 schedule · fixed 512×512 target", 560, 1040,
                      {"steps": 20, "width": 512, "height": 512}, width=400, height=200)
    w.link(schedule, 0, audition, "sigmas")
    path = w.node("PreviewAny", "Saved bundle path", 2350, 480, width=440, height=180)
    w.link(save, 0, path, "source")
    w.group("1. Setup and model components", [20, 20, 500, 1730])
    w.group("2. Fixed prompts, target and schedule", [540, 20, 440, 1270])
    w.group("3. Bounded audition", [1020, 20, 540, 1200])
    w.group("4. Inspect influence", [1600, 20, 690, 1500])
    w.group("5. Save a new selection", [2330, 20, 480, 700])
    return w


def main():
    if "--schemas" in sys.argv:
        # A fresh interpreter keeps core's nodes.py separate from this pack's nodes package.
        # Used by contract tests; no files are written in this mode.
        types = ("LoadImage", "VAELoader", "ImageScale", "PreviewAny", "UNETLoader", "CLIPLoader",
                 "DualCLIPLoader", "LoraLoaderModelOnly", "CLIPTextEncode", "FluxGuidance",
                 "JWTFUnifiedRefModBake", "JWTFUnifiedRefModApply", "LTXVConditioning",
                 "EmptyLTXVLatentVideo", "KSampler", "LTXVCropGuides", "VAEDecode", "SaveImage", "SaveWEBM", "MarkdownNote",
                 "EmptyFlux2LatentImage", "JWTFReferenceAudition", "JWTFSaveAuditionSelection", "PreviewImage",
                 "Flux2Scheduler", "RandomNoise", "CFGGuider", "KSamplerSelect", "SamplerCustomAdvanced")
        types += ("CheckpointLoaderSimple", "LTXVScheduler", "ModelSamplingFlux", "SkipLayerGuidanceDiTSimple", "EmptyLatentImage")
        types += ("JWTFRefModConditioningCheck",)
        types += ("VAEEncode", "ImageScaleToTotalPixels", "GetImageSize", "SplitSigmasDenoise", "BasicScheduler")
        types += ("JWTFSmartSelect", "JWTFRegionCrop", "JWTFRegionComposite", "JWTFMaskEditor", "JWTFImageCompare", "SetLatentNoiseMask")
        print(json.dumps({name: {"input": input_spec(name), "output": [str(t) for t in getattr(registry().get(name), "RETURN_TYPES", ())]}
                          for name in types}, default=str))
        return
    workflows = [bake_example(), bake_example(ltx=True), *(apply_example(family) for family in FAMILIES), audition_example(), moss_diagnostic_example(), character_scene_example(), refmod_upscale_example("flux2"), refmod_upscale_example("flux3"), refmod_upscale_example("flux3", "distilled"), smart_selection_example(), smart_selection_example(refine=True)]
    for workflow in workflows:
        path = OUT / f"{workflow.name}.json"
        path.write_text(json.dumps(workflow.result(), indent=2) + "\n", encoding="utf-8", newline="\n")
        print(path.name)


if __name__ == "__main__":
    main()
