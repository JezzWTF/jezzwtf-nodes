"""Shared helpers for testing V3 nodes without a running ComfyUI.

V3 `execute` returns an `io.NodeOutput`; these helpers give tests the plain shapes they assert on.
"""
from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

from comfy_api.latest import io


def legacy(out: Any) -> Any:
    """The old return shape of a node: a tuple of outputs, or {"ui": ..., "result": (...)} when it carries UI data."""
    if not isinstance(out, io.NodeOutput):
        return out
    if out.ui is not None:
        return {"ui": out.ui, "result": tuple(out.args)}
    return tuple(out.args)


def overrides(node: type[io.ComfyNode], method: str) -> bool:
    """True when the node defines its own `method` (fingerprint_inputs, validate_inputs, ...)."""
    return getattr(node, method).__func__ is not getattr(io.ComfyNode, method).__func__


@contextmanager
def hidden(node: type[io.ComfyNode], **values: Any) -> Iterator[None]:
    """Run a node with hidden inputs set, the way the executor does (`cls.hidden.unique_id`, ...)."""
    previous = node.__dict__.get("hidden", None)
    node.hidden = io.HiddenHolder.from_dict({getattr(io.Hidden, k): v for k, v in values.items()})
    try:
        yield
    finally:
        if previous is None:
            del node.hidden
        else:
            node.hidden = previous


def force_cpu() -> None:
    """Make ComfyUI's model management pick the CPU, so importing it works on machines without a GPU (CI)."""
    try:
        from comfy.cli_args import args  # type: ignore[import-not-found]

        args.cpu = True
    except Exception:  # noqa: BLE001 - no ComfyUI on the path: the nodes treat that as "outside ComfyUI"
        pass


force_cpu()


def install_default_hidden() -> None:
    """Give every node an empty hidden holder so `cls.hidden.unique_id` is None outside the executor."""
    io.ComfyNode.hidden = io.HiddenHolder.from_dict({})


def legacy_h(node: type[io.ComfyNode], unique_id: Any, call: Callable[[], Any]) -> Any:
    """Run `call` with the node's hidden unique_id set, returning the legacy result shape."""
    with hidden(node, unique_id=unique_id):
        return legacy(call())


def legacy_spec(node: type[io.ComfyNode]) -> dict[str, dict[str, tuple[Any, ...]]]:
    """The node's inputs in the old INPUT_TYPES shape: combos as (options, opts), hidden values as plain strings."""
    raw = node.INPUT_TYPES()
    out: dict[str, dict[str, tuple[Any, ...]]] = {}
    for section, items in raw.items():
        out[section] = {}
        for name, spec in items.items():
            if section == "hidden":
                if name not in ("prompt", "extra_pnginfo"):  # V3 adds these to every output node
                    out[section][name] = spec[0] if isinstance(spec, tuple) else spec
                continue
            kind = spec[0]
            opts = dict(spec[1]) if len(spec) > 1 else {}
            opts.pop("multiselect", None)
            if opts.get("multiline") is False:
                opts.pop("multiline")
            if kind == "COMBO":
                out[section][name] = (list(opts.pop("options", [])), opts)
            else:
                out[section][name] = (kind, opts)
    return out


def run_node(node: type[io.ComfyNode], *args: Any, **kwargs: Any) -> Any:
    """`node.execute(...)` in the legacy result shape; `unique_id=`/`dynprompt=` kwargs become hidden inputs."""
    held = {k: kwargs.pop(k) for k in ("unique_id", "dynprompt", "prompt_id") if k in kwargs and k != "prompt_id"}
    with hidden(node, **held):
        return legacy(node.execute(*args, **kwargs))
