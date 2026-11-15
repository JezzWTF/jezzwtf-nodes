"""Controlled leave-one-reference-out trials and a separately cached bundle selection."""
from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import time
import uuid
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageDraw, ImageFont, ImageOps
from safetensors import safe_open
from comfy_api.latest import io

from . import _comfy, library, samplers, unified
from ._types import RefModError
from .bundle import _atomic_save, bundle_metadata, load_refmod_file
from .curves import apply_rows


def sources() -> dict[str, str]:
    return {**{name: entry[0] for name, entry in unified.index().items()},
            **{f"H3: {name}": path for name, path in library.list_library().items()}}


def digest(path: str) -> str:
    hasher = hashlib.sha256()
    with open(path, "rb") as stream:
        hasher.update(_comfy.file_sha256(stream).digest())
    sidecar = os.path.splitext(path)[0] + ".json"
    if os.path.isfile(sidecar):
        with open(sidecar, "rb") as stream:
            hasher.update(_comfy.file_sha256(stream).digest())
    return hasher.hexdigest()


def clone_tree(value):
    """Each trial owns its conditioning/latent containers, including tensor storage."""
    if isinstance(value, torch.Tensor):
        return value.clone()
    if isinstance(value, dict):
        return {key: clone_tree(item) for key, item in value.items()}
    if isinstance(value, list):
        return [clone_tree(item) for item in value]
    if isinstance(value, tuple):
        return tuple(clone_tree(item) for item in value)
    return copy.deepcopy(value)


def parse_selection(text: str, count: int) -> list[int]:
    if text.strip().lower() == "all":
        return list(range(count))
    try:
        numbers = [int(part.strip()) for part in text.split(",")]
    except ValueError as exc:
        raise RefModError("keep_refs must be all or comma-separated reference numbers, for example 1,3") from exc
    if not numbers or len(set(numbers)) != len(numbers) or any(n < 1 or n > count for n in numbers):
        raise RefModError(f"Choose unique reference numbers from 1 to {count}")
    return [number - 1 for number in numbers]


def frame_strip(images: torch.Tensor, edge: int = 240) -> Image.Image:
    if images.ndim != 4 or images.shape[0] < 1:
        raise RefModError("VAE decode must return images [frames,height,width,channels]")
    positions = sorted(set([0, (images.shape[0] - 1) // 2, images.shape[0] - 1]))
    strip = Image.new("RGB", (edge * len(positions), edge), "#111820")
    for column, index in enumerate(positions):
        pixels = images[index, ..., :3].detach().float().clamp(0, 1).cpu().numpy()
        frame = Image.fromarray(np.round(pixels * 255).astype(np.uint8))
        frame = ImageOps.contain(frame, (edge, edge), Image.Resampling.LANCZOS)
        strip.paste(frame, (column * edge + (edge - frame.width) // 2, (edge - frame.height) // 2))
    return strip


def contact_sheet(strips: list[Image.Image], cases: list[dict], skipped: list[int]) -> torch.Tensor:
    width = max(720, max(strip.width for strip in strips))
    height = 88 + sum(strip.height + 64 for strip in strips) + 42
    canvas = Image.new("RGB", (width + 40, height), "#111820")
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default(size=18)
    draw.text((20, 16), "REFERENCE AUDITION", font=font, fill="#85d8c3")
    draw.text((20, 46), "Same seed / prompt / target. Change measures influence, not quality.", fill="#bec9d5")
    y = 88
    for case, strip in zip(cases, strips):
        label = case["label"]
        delta = case["change_vs_baseline"]
        detail = f"{case['seconds']:.2f}s" + (f"   |   change {delta:.4f}" if delta is not None else "   |   baseline")
        draw.text((20, y), label, font=font, fill="#f2f5f8")
        draw.text((20, y + 26), detail, fill="#bec9d5")
        canvas.paste(strip, (20, y + 52))
        y += strip.height + 64
    footer = "Untested omissions: " + ", ".join(map(str, skipped)) if skipped else "All individual omissions completed."
    draw.text((20, y + 8), footer, fill="#bec9d5")
    return torch.from_numpy(np.asarray(canvas).copy()).float().unsqueeze(0) / 255


def check_interrupt():
    module = _comfy.optional_module("comfy.model_management")
    if module is not None:
        module.throw_exception_if_processing_interrupted()


class TargetNoise:
    """LTX appends guides along T; keep target noise independent of appended length."""
    def __init__(self, seed, shape):
        self.seed, self.shape = seed, tuple(shape)

    def generate_noise(self, latent):
        samples = latent["samples"]
        if samples.ndim != 5 or any(samples.shape[i] != self.shape[i] for i in (0, 1, 3, 4)) or samples.shape[2] < self.shape[2]:
            raise RefModError("LTX guide application changed the target grid")
        module = _comfy.optional_module("comfy.sample")
        noise = module.prepare_noise(torch.zeros(self.shape, dtype=samples.dtype, device="cpu"), self.seed, latent.get("batch_index"))
        return torch.nn.functional.pad(noise, (0, 0, 0, 0, 0, samples.shape[2] - self.shape[2]))


def sample_trial(model, positive, negative, latent, vae, *, seed, steps, cfg, sampler_name, scheduler, denoise, ltx=False, target_noise=None, sigmas=None):
    output = samplers.run_sampler(
        model=model, positive=positive, negative=negative, latent_image=latent,
        sampler_name=sampler_name, scheduler=scheduler, steps=steps, steps_to_run=-1,
        cfg=cfg, cfg_enabled=True, denoise=denoise, seed=seed,
        decode=False, tiled_decode=False, preview_fps=1, unique_id=None, dynprompt=None,
        preview=False, allow_clown=False, noise=target_noise, sigmas=sigmas,
    )
    sampled = output.args[0]
    if ltx:
        module = _comfy.optional_module("comfy_extras.nodes_lt")
        crop = getattr(module, "LTXVCropGuides", None)
        if crop is None:
            raise RefModError("Update ComfyUI: LTX audition needs LTXV Crop Guides")
        sampled = _comfy.call_node(crop, positive=positive, negative=negative, latent=sampled)[2]
    return samplers.decode_latent(sampled, vae, None, False)[0]


class JWTFReferenceAudition(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="JWTFReferenceAudition", display_name="Reference Audition", category="JezzWTF/refmod",
            description="Render all references, then omit each reference in turn using the same seed, prompt and target latent. Supports image/LTX bundles and H3 bundles. A render cap and between-render time budget bound the sweep. Visual change measures influence, never quality. Use Save Audition Selection to keep your chosen references without rerunning trials.",
            inputs=[
                io.Model.Input("model"), io.Vae.Input("vae"), io.Latent.Input("latent_image", tooltip="Fixed target for every trial. Use a clean, batch-one latent matching the model, without pre-applied references or LTX guide frames."),
                io.Combo.Input("refmod", options=[unified.NONE] + sorted(sources()), default=unified.NONE),
                io.Int.Input("seed", default=42, min=0, max=0xffffffffffffffff),
                io.Int.Input("steps", default=12, min=1, max=1000),
                io.Float.Input("cfg", default=4, min=0, max=100, step=0.1),
                io.Combo.Input("sampler_name", options=samplers.base_samplers(), default="euler"),
                io.Combo.Input("scheduler", options=samplers.base_schedulers(), default="simple"),
                io.Float.Input("denoise", default=1, min=0.01, max=1, step=0.01),
                io.Int.Input("max_renders", default=5, min=1, max=81, tooltip="Includes the full-reference baseline. Reference omissions run in source order; untested numbers appear in the report."),
                io.Float.Input("time_budget_seconds", default=120, min=0, max=86400, tooltip="Soft wall-time budget: finish the current render, then stop. 0 disables the time limit; max_renders still applies."),
                io.Clip.Input("clip", optional=True),
                io.String.Input("prompt", default="", multiline=True, optional=True),
                io.String.Input("negative_prompt", default="", multiline=True, optional=True),
                io.Conditioning.Input("positive", optional=True, tooltip="Clean prompt conditioning for Flux, LTX or H3. Do not apply references upstream."),
                io.Conditioning.Input("negative", optional=True),
                io.Combo.Input("edit_format", options=list(unified.EDIT_FORMATS), default="ai-toolkit (kv_cache off)", optional=True),
                io.Float.Input("ref_strength", default=1, min=0, max=1, step=0.01, optional=True, tooltip="Image reference schedule; LTX guide strength; H3 retention. Held fixed across trials."),
                io.Boolean.Input("ref_on_negative", default=True, optional=True),
                io.Int.Input("latent_idx", default=0, min=0, max=10000, optional=True, tooltip="LTX guide start, in latent frames."),
                io.Sigmas.Input("sigmas", optional=True, tooltip="Exact schedule from your working generation workflow, e.g. Flux2Scheduler. Overrides steps, scheduler and denoise widgets for every trial."),
            ],
            outputs=[io.Image.Output("contact_sheet"), io.Custom("JWTF_REF_AUDITION").Output("audition"), io.String.Output("report")],
            is_output_node=True,
        )

    @classmethod
    def fingerprint_inputs(cls, refmod=unified.NONE, **kwargs):
        path = sources().get(refmod)
        return library.file_stamp(path) if path else "missing"

    @classmethod
    def execute(cls, model, vae, latent_image, refmod, seed=42, steps=12, cfg=4,
                sampler_name="euler", scheduler="simple", denoise=1, max_renders=5,
                time_budget_seconds=120, clip=None, prompt="", negative_prompt="", positive=None,
                negative=None, edit_format="ai-toolkit (kv_cache off)", ref_strength=1,
                ref_on_negative=True, latent_idx=0, sigmas=None):
        if not 1 <= max_renders <= 81 or not math.isfinite(time_budget_seconds) or time_budget_seconds < 0:
            raise RefModError("Use max_renders 1–81 and a finite non-negative time budget")
        if sigmas is not None and (sigmas.ndim != 1 or sigmas.numel() < 2 or not torch.isfinite(sigmas).all() or (sigmas < 0).any() or (sigmas[1:] > sigmas[:-1]).any()):
            raise RefModError("sigmas must be a finite, non-negative, descending 1-D schedule with at least two entries")
        samples = latent_image.get("samples")
        if not isinstance(samples, torch.Tensor) or samples.is_nested or samples.ndim not in (4, 5) or samples.shape[0] != 1:
            raise RefModError("Audition needs a plain batch-one image/video target latent; split nested AV latents first")
        for cond in (positive, negative):
            if cond and isinstance(cond, list) and any(any(entry[1].get(key) is not None for key in ("reference_latents", "minimax_refs", "guide_attention_entries", "keyframe_idxs")) for entry in cond):
                raise RefModError("Connect clean prompt conditioning: remove upstream references/guides")
        path = sources().get(refmod)
        if path is None:
            raise RefModError("Choose a saved reference bundle before running Reference Audition")
        source_hash = digest(path)
        found = unified.detect(path)
        if found:
            handler, lats, imgs = unified.load_refs(path)
            count, family = len(lats), handler.key
            mods = None
        else:
            mods = load_refmod_file(path)
            count, family = len(mods), "h3"
            if positive is None:
                raise RefModError("H3 audition needs clean positive conditioning")
        if not count:
            raise RefModError("The source bundle contains no references")
        if found and count > handler.max_refs:
            raise RefModError(f"{handler.label} supports at most {handler.max_refs} references")
        if family == "ltxv" and sampler_name != "euler":
            raise RefModError("LTX audition uses euler so guide-count changes cannot alter stochastic sampler noise")
        if digest(path) != source_hash:
            raise RefModError("Source changed while loading; queue again")
        started = time.perf_counter()
        cases, strips = [], []
        baseline = None
        target_noise = TargetNoise(seed, samples.shape) if family == "ltxv" else None
        stop_reason = "complete"
        for omitted in [None, *range(count)]:
            check_interrupt()
            if len(cases) >= max_renders:
                stop_reason = "render_limit"
                break
            if cases and time_budget_seconds and time.perf_counter() - started >= time_budget_seconds:
                stop_reason = "time_budget"
                break
            tick = time.perf_counter()
            keep = [i for i in range(count) if i != omitted]
            pos, neg = clone_tree(positive), clone_tree(negative)
            latent = clone_tree(latent_image)
            if mods is not None:
                rows = [(mods[i], 1.0) for i in keep]
                pos, _ = apply_rows(pos, rows, retention=ref_strength)
                if ref_on_negative and neg is not None:
                    neg, _ = apply_rows(neg, rows, retention=ref_strength)
            else:
                selected_lats = [lats[i].clone().to(_comfy.intermediate_device()) for i in keep]
                selected_imgs = [imgs[i].clone() for i in keep] if handler.stores_images else []
                if family == "ltxv":
                    pos, neg, latent = unified.apply_ltx(pos, neg, latent, vae, selected_lats, latent_idx, ref_strength)
                else:
                    ctx = unified.ApplyContext(clip, prompt, negative_prompt, pos, neg, ref_strength, ref_on_negative, edit_format)
                    pos, neg = handler.build(handler, ctx, selected_lats, selected_imgs)
            images = sample_trial(model, pos, neg, latent, vae, seed=seed, steps=steps, cfg=cfg,
                                  sampler_name=sampler_name, scheduler=scheduler, denoise=denoise, ltx=family == "ltxv", target_noise=target_noise,
                                  sigmas=sigmas.clone() if sigmas is not None else None)
            strip = frame_strip(images)
            pixels = np.asarray(strip).astype(np.float32) / 255
            if baseline is None:
                baseline = pixels
                delta = None
            else:
                if pixels.shape != baseline.shape:
                    raise RefModError("Trial output dimensions changed; use a fixed target latent")
                delta = float(np.abs(pixels - baseline).mean())
            cases.append({"label": "All references" if omitted is None else f"Without reference {omitted + 1}",
                          "omitted": None if omitted is None else omitted + 1, "kept": [i + 1 for i in keep],
                          "seconds": round(time.perf_counter() - tick, 4), "change_vs_baseline": delta})
            strips.append(strip)
            del images, pos, neg, latent
        tested = {case["omitted"] for case in cases}
        skipped = [i + 1 for i in range(count) if i + 1 not in tested]
        data = {"version": 1, "source": refmod, "path": os.path.abspath(path), "sha256": source_hash,
                "family": family, "reference_count": count,
                "references": [{"number": i + 1, "name": mod.name, "kind": mod.kind} for i, mod in enumerate(mods)] if mods is not None else [{"number": i + 1, "latent_shape": list(lat.shape)} for i, lat in enumerate(lats)],
                "seed": seed, "steps": steps, "cfg": cfg, "prompt": prompt, "negative_prompt": negative_prompt,
                "ref_strength": ref_strength, "ref_on_negative": ref_on_negative, "edit_format": edit_format, "latent_idx": latent_idx,
                "sampler": sampler_name, "scheduler": scheduler, "denoise": denoise,
                "sampling_schedule": {"source": "external sigmas", "values": sigmas.detach().cpu().tolist()} if sigmas is not None else {"source": "widgets"},
                "target_shape": list(samples.shape), "cases": cases, "untested": skipped,
                "stop_reason": stop_reason, "seconds": round(time.perf_counter() - started, 4),
                "metric": "Mean absolute RGB change on evenly spaced preview frames (0–1), including letterboxing. Influence only; not quality or identity accuracy. Video is a frame-strip comparison; audio is not scored."}
        sheet = contact_sheet(strips, cases, skipped)
        folder = os.path.join(_comfy.temp_dir(), "jezzwtf_audition")
        os.makedirs(folder, exist_ok=True)
        filename = f"audition_{uuid.uuid4().hex}.png"
        Image.fromarray((sheet[0].numpy() * 255).round().astype(np.uint8)).save(os.path.join(folder, filename))
        report = json.dumps({key: value for key, value in data.items() if key != "path"}, indent=2)
        return io.NodeOutput(sheet, data, report, ui={"images": [{"filename": filename, "subfolder": "jezzwtf_audition", "type": "temp"}], "text": [report]})


class JWTFSaveAuditionSelection(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="JWTFSaveAuditionSelection", display_name="Save Audition Selection", category="JezzWTF/refmod",
            description="Save chosen references as a compatible new bundle, without rerunning the upstream audition. Source order is numbered from 1. Saving is off by default; the original bundle is always preserved.",
            inputs=[io.Custom("JWTF_REF_AUDITION").Input("audition"),
                    io.String.Input("keep_refs", default="all", tooltip="Comma-separated 1-based source indices, e.g. 1,3; or all. Order is preserved as entered."),
                    io.String.Input("name", default="audition_selection"),
                    io.Boolean.Input("save", default=False), io.Boolean.Input("overwrite", default=False)],
            outputs=[io.String.Output("path"), io.String.Output("info")], is_output_node=True,
        )

    @classmethod
    def execute(cls, audition, keep_refs="all", name="audition_selection", save=False, overwrite=False):
        keep = parse_selection(keep_refs, int(audition["reference_count"]))
        if not save:
            info = f"Not saved. Keep references {', '.join(str(i + 1) for i in keep)}; enable save to write a new bundle."
            return io.NodeOutput("", info, ui={"text": [info]})
        source = audition["path"]
        if digest(source) != audition["sha256"]:
            raise RefModError("Source bundle changed since audition; rerun the audition before saving")
        found = unified.detect(source)
        if found:
            handler, meta = found
            dest = unified.unified_output_path(name, "", handler)
            with safe_open(source, framework="pt", device="cpu") as fh:
                metadata = dict(fh.metadata() or {})
                tensors = {}
                for new, old in enumerate(keep):
                    for prefix in ("lat", "img"):
                        key = f"{prefix}_{old}"
                        if key in fh.keys():
                            tensors[f"{prefix}_{new}"] = fh.get_tensor(key).contiguous()
            meta = dict(meta)
            for key in ("sizes", "shapes", "ref_sizes"):
                if isinstance(meta.get(key), list) and len(meta[key]) == audition["reference_count"]:
                    meta[key] = [meta[key][i] for i in keep]
            meta.update(count=len(keep), name=name, audition_source=audition["source"], audition_keep=[i + 1 for i in keep])
            if "img_0" in tensors:
                meta["thumb"] = unified.thumb_b64(tensors["img_0"].float() / 255)
            elif keep[0] != 0:
                meta.pop("thumb", None)
            metadata[handler.meta_key] = json.dumps(meta)
        else:
            dest = library.mod_output_path(name, "audition")
            mods = load_refmod_file(source, keep)
            tensors = {f"ref_{i}": mod.latent.cpu().contiguous() for i, mod in enumerate(mods)}
            metadata = bundle_metadata(name, mods)
        if os.path.normcase(os.path.realpath(dest)) == os.path.normcase(os.path.realpath(source)):
            raise RefModError("Choose a different name; the audition source must be preserved")
        if digest(source) != audition["sha256"]:
            raise RefModError("Source changed while reading; rerun the audition")
        reserved = False
        if not overwrite:
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            try:
                with open(dest, "xb"):
                    pass
            except FileExistsError as exc:
                raise RefModError("Destination exists; choose a new name or enable overwrite") from exc
            reserved = True
        try:
            _atomic_save(tensors, metadata, dest)
        except BaseException:
            if reserved:
                Path(dest).unlink(missing_ok=True)
            raise
        unified.invalidate(dest)
        info = f"Saved {len(keep)} references: {', '.join(str(i + 1) for i in keep)}"
        return io.NodeOutput(dest, info, ui={"text": [info, dest]})


NODES = [JWTFReferenceAudition, JWTFSaveAuditionSelection]
