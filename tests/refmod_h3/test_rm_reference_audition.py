"""Controlled ablations, partial sweeps and lossless subset saves without model weights."""
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
import torch
from PIL import Image

from fakes import FakeClip, FakeImageVAE
from refmod_h3 import reference_audition as a, unified
from refmod_h3._types import RefModError
from refmod_h3.bundle import RefMod, load_refmod_file, write_bundle
from v3_helpers import legacy


@pytest.fixture
def trials(refmod_root, monkeypatch, tmp_path):
    images = torch.stack([torch.full((64, 64, 3), value) for value in (.2, .5, .8)])
    path = unified.JWTFUnifiedRefModBake.execute("qwen21", images, "source", 64, "", False, vae=FakeImageVAE(64)).args[0]
    calls = []
    def sample(model, pos, neg, latent, vae, **settings):
        refs = pos[0][1].get("reference_latents", [])
        calls.append({"latents": [float(lat.mean()) for lat in refs], "n_images": pos[0][1]["n_images"],
                      "settings": settings, "target": latent["samples"].clone()})
        latent["samples"].add_(99)
        return torch.full((1, 32, 48, 3), len(refs) / 4)
    monkeypatch.setattr(a, "sample_trial", sample)
    monkeypatch.setattr(a._comfy, "temp_dir", lambda: str(tmp_path))
    clip = FakeClip()
    target = {"samples": torch.zeros(1, 64, 4, 4), "noise_mask": torch.ones(1, 1, 4, 4)}
    def run(**kwargs):
        return a.JWTFReferenceAudition.execute(object(), object(), target, "qwen21/source", clip=clip, prompt="A portrait", **kwargs)
    return SimpleNamespace(run=run, calls=calls, path=path, clip=clip, target=target)


def test_each_omission_reencodes_vision_and_keeps_noise_target_fixed(trials):
    out = trials.run()
    sheet, data, report = out.args
    assert len(trials.calls) == 4
    assert [call["n_images"] for call in trials.calls] == [3, 2, 2, 2]
    assert [[round(v, 1) for v in call["latents"]] for call in trials.calls] == [[.2, .5, .8], [.5, .8], [.2, .8], [.2, .5]]
    assert all(torch.equal(call["target"], trials.target["samples"]) for call in trials.calls)
    assert not torch.count_nonzero(trials.target["samples"])
    assert all(call["settings"] == trials.calls[0]["settings"] for call in trials.calls)
    assert [case["omitted"] for case in data["cases"]] == [None, 1, 2, 3]
    assert data["cases"][0]["change_vs_baseline"] is None
    assert data["cases"][1]["change_vs_baseline"] > 0
    assert data["untested"] == [] and data["stop_reason"] == "complete"
    assert sheet.ndim == 4 and sheet.shape[0] == 1 and "Influence only" in report
    descriptor = out.ui["images"][0]
    assert descriptor["type"] == "temp"
    assert len(json.loads(report)["references"]) == 3


def test_caps_report_unmeasured_refs_without_fake_scores(trials):
    data = trials.run(max_renders=2).args[1]
    assert len(trials.calls) == 2 and data["untested"] == [2, 3]
    assert data["stop_reason"] == "render_limit"


def test_soft_deadline_finishes_baseline_then_stops(trials, monkeypatch):
    ticks = iter([0, 0, 2, 3, 4])
    monkeypatch.setattr(a.time, "perf_counter", lambda: next(ticks))
    data = trials.run(time_budget_seconds=1).args[1]
    assert len(trials.calls) == 1 and data["untested"] == [1, 2, 3]
    assert data["stop_reason"] == "time_budget"


def test_cancellation_propagates_instead_of_partial_success(trials, monkeypatch):
    class Cancelled(Exception):
        pass
    def interrupt():
        raise Cancelled()
    monkeypatch.setattr(a, "check_interrupt", interrupt)
    with pytest.raises(Cancelled):
        trials.run()
    assert not trials.calls


def test_saver_roundtrips_selected_tensors_metadata_and_preserves_source(trials):
    data = trials.run().args[1]
    original = Path(trials.path).read_bytes()
    h, lats, imgs = unified.load_refs(trials.path)
    dry = a.JWTFSaveAuditionSelection.execute(data, "3,1", "selected")
    assert dry.args[0] == ""
    saved = a.JWTFSaveAuditionSelection.execute(data, "3,1", "selected", True).args[0]
    _, actual_lats, actual_imgs = unified.load_refs(saved)
    assert all(torch.equal(v, expected) for v, expected in zip(actual_lats, [lats[2], lats[0]]))
    assert all(torch.equal(v, expected) for v, expected in zip(actual_imgs, [imgs[2], imgs[0]]))
    meta = unified.detect(saved)[1]
    assert len(meta["sizes"]) == meta["count"] == 2 and meta["audition_keep"] == [3, 1]
    assert Path(trials.path).read_bytes() == original
    assert len(trials.calls) == 4  # Saver never samples.
    with pytest.raises(RefModError, match="Destination exists"):
        a.JWTFSaveAuditionSelection.execute(data, "1", "selected", True)
    a.JWTFSaveAuditionSelection.execute(data, "1", "selected", True, True)
    assert len(unified.load_refs(saved)[1]) == 1
    with pytest.raises(RefModError, match="source must be preserved"):
        a.JWTFSaveAuditionSelection.execute(data, "1", "source", True, True)


@pytest.mark.parametrize("selection", ["", "0", "4", "1,1", "-1", "one", "1,"])
def test_bad_selection_never_writes(trials, selection):
    data = trials.run(max_renders=1).args[1]
    with pytest.raises(RefModError):
        a.JWTFSaveAuditionSelection.execute(data, selection, "selected", True)


def test_changed_source_rejected_even_with_identical_size_and_timestamps(trials):
    data = trials.run(max_renders=1).args[1]
    stat = os.stat(trials.path)
    content = bytearray(Path(trials.path).read_bytes())
    content[-1] ^= 1
    Path(trials.path).write_bytes(content)
    os.utime(trials.path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    with pytest.raises(RefModError, match="changed since audition"):
        a.JWTFSaveAuditionSelection.execute(data, "1", "selected", True)


def test_h3_injection_subset_save_and_final_reference_omission(refmod_root, monkeypatch, tmp_path):
    path = str(Path(refmod_root) / "h3.safetensors")
    mod = RefMod(name="face", kind="image", latent=torch.zeros(1, 24, 1, 4, 4))
    write_bundle(path, "h3", [mod])
    counts = []
    def sample(model, pos, neg, latent, vae, **kwargs):
        counts.append(len(pos[0][1].get("minimax_refs", [])))
        return torch.zeros(5, 16, 16, 3)
    monkeypatch.setattr(a, "sample_trial", sample)
    monkeypatch.setattr(a._comfy, "temp_dir", lambda: str(tmp_path))
    cond = [[torch.zeros(1), {}]]
    data = a.JWTFReferenceAudition.execute(object(), object(), {"samples": torch.zeros(1, 24, 2, 4, 4)},
                                          "H3: h3", positive=cond).args[1]
    assert counts == [1, 0] and cond[0][1] == {}
    dest = a.JWTFSaveAuditionSelection.execute(data, "1", "h3_selected", True).args[0]
    assert load_refmod_file(dest)[0].name == "face"
    assert data["references"][0]["name"] == "face"


def test_native_ltx_guide_crop_happens_before_decode(monkeypatch):
    from comfy_extras import nodes_lt
    pos = [[torch.zeros(1), {"keyframe_idxs": torch.zeros(1, 3, 4, 2),
                              "guide_attention_entries": [{"pre_filter_count": 1, "latent_shape": [1, 1, 1]}]}]]
    # Ask the real crop node how many guide frames this metadata describes.
    latent = {"samples": torch.zeros(1, 128, 3, 2, 2)}
    monkeypatch.setattr(a.samplers, "run_sampler", lambda **kw: SimpleNamespace(args=[kw["latent_image"]]))
    shapes = []
    def decode(sampled, *args):
        shapes.append(sampled["samples"].shape)
        return torch.zeros(1, 8, 8, 3), None
    monkeypatch.setattr(a.samplers, "decode_latent", decode)
    a.sample_trial(object(), pos, pos, latent, object(), seed=1, steps=1, cfg=1,
                   sampler_name="euler", scheduler="simple", denoise=1, ltx=True)
    assert shapes[0][2] == 2


def test_preview_strip_uses_beginning_middle_end():
    video = torch.stack([torch.full((8, 8, 3), n / 4) for n in range(5)])
    strip = a.frame_strip(video, edge=8)
    assert strip.size == (24, 8)
    assert [strip.getpixel((x, 0))[0] for x in (0, 8, 16)] == [0, 128, 255]


def test_ltx_target_noise_identical_when_guide_count_changes():
    fixed = a.TargetNoise(42, (1, 128, 3, 2, 2))
    baseline = fixed.generate_noise({"samples": torch.zeros(1, 128, 6, 2, 2)})
    omission = fixed.generate_noise({"samples": torch.zeros(1, 128, 5, 2, 2)})
    assert torch.equal(baseline[:, :, :3], omission[:, :, :3])
    assert torch.count_nonzero(baseline[:, :, :3])
    assert not torch.count_nonzero(baseline[:, :, 3:])
    assert not torch.count_nonzero(omission[:, :, 3:])


@pytest.mark.parametrize("family", list(unified.HANDLERS))
def test_saved_subset_is_loadable_by_every_image_ltx_handler(refmod_root, family):
    h = unified.HANDLERS[family]
    shape = (1, h.latent_channels, 1, 4, 4) if family in ("ltxv", "krea2") else (1, h.latent_channels, 4, 4)
    edge = 4 * h.spatial_downscale
    encs = [unified.Encoded(torch.full(shape, n + .25), torch.full((1, edge, edge, 3), n / 2) if h.stores_images else None, (edge, edge)) for n in range(3)]
    tensors, metadata = unified.build_file(h, "source", encs, 64, torch.zeros(1, 64, 64, 3))
    path = unified.unified_output_path("source", "", h)
    a._atomic_save(tensors, metadata, path)
    data = {"path": path, "sha256": a.digest(path), "source": f"{family}/source", "reference_count": 3}
    dest = a.JWTFSaveAuditionSelection.execute(data, "3,1", "subset", True).args[0]
    actual_h, latents, images = unified.load_refs(dest)
    assert actual_h.key == family and len(latents) == 2
    assert torch.equal(latents[0], encs[2].lat)
    assert torch.equal(latents[1], encs[0].lat)
    assert len(images) == (2 if h.stores_images else 0)


def test_clean_conditioning_required(trials):
    with pytest.raises(RefModError, match="clean prompt"):
        a.JWTFReferenceAudition.execute(object(), object(), trials.target, "qwen21/source",
                                        positive=[[torch.zeros(1), {"reference_latents": [torch.zeros(1)]}]])


def test_external_sigmas_reused_exactly_for_every_trial(trials):
    sigmas = torch.tensor([1., .8, .2, 0.])
    data = trials.run(sigmas=sigmas).args[1]
    assert all(torch.equal(call["settings"]["sigmas"], sigmas) for call in trials.calls)
    assert data["sampling_schedule"]["source"] == "external sigmas"


@pytest.mark.parametrize("sigmas", [torch.tensor([0.]), torch.tensor([0., 1.]), torch.tensor([1., float("nan")]), torch.tensor([[1., 0.]]), torch.tensor([1., -1.])])
def test_invalid_sigma_schedule_fails_before_any_render(trials, sigmas):
    with pytest.raises(RefModError, match="sigmas must be"):
        trials.run(sigmas=sigmas)
    assert not trials.calls


def test_file_sha256_matches_hashlib_across_chunks(tmp_path):
    data = bytes(range(256)) * 9000  # larger than one 1 MiB read
    path = tmp_path / "blob.bin"
    path.write_bytes(data)
    with open(path, "rb") as stream:
        assert a._comfy.file_sha256(stream).hexdigest() == __import__("hashlib").sha256(data).hexdigest()
