"""Interruption and progress hooks. ComfyUI is optional: outside it both degrade to no-ops."""
from __future__ import annotations

from collections.abc import Callable


def check_interrupt() -> None:
    """Raise ComfyUI's interrupt exception when the user pressed Cancel; no-op outside ComfyUI."""
    try:
        import comfy.model_management as mm  # type: ignore[import-not-found]
    except Exception:
        return
    mm.throw_exception_if_processing_interrupted()


class Progress:
    """`comfy.utils.ProgressBar` when present, otherwise a silent counter. The total can be raised later."""

    def __init__(self, total: int) -> None:
        self.total = max(1, int(total))
        self.value = 0
        self._bar: object | None = None
        try:
            import comfy.utils  # type: ignore[import-not-found]

            self._bar = comfy.utils.ProgressBar(self.total)
        except Exception:
            self._bar = None

    def update_to(self, value: int, total: int | None = None) -> None:
        if total is not None:
            self.total = max(1, int(total))
        self.value = max(0, min(int(value), self.total))
        update = getattr(self._bar, "update_absolute", None)
        if callable(update):
            try:
                update(self.value, self.total)
            except Exception:
                pass

    def step(self) -> None:
        self.update_to(self.value + 1)


Check = Callable[[], None]
