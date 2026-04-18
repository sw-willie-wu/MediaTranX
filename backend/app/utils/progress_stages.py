"""Stage-weighted progress helper.

Three services (audio/transcribe, audio/lyrics, video/subtitle) previously
hand-rolled identical stage-weight math — compute (start, end) per stage from
relative weights with a fixed-fraction final stage, then a closure maps
stage-local 0..1 into overall 0..1. This collapses that into one class.
"""
from __future__ import annotations

import logging
from typing import Callable

logger = logging.getLogger(__name__)


class StageProgress:
    """Map stage-local progress (0..1) into an overall progress range.

    `weights` are relative integer weights — caller's intent-level units that
    get normalized internally. `final_weight` is a fraction of overall (0..1)
    reserved for the final stage (typically file I/O at 0.05).

    Unknown stage names pass local progress through unchanged with a warning.
    """

    def __init__(
        self,
        callback: Callable[[float, str], None],
        weights: dict[str, int],
        *,
        final_stage: str = "write",
        final_weight: float = 0.05,
    ) -> None:
        if not weights:
            raise ValueError("StageProgress requires at least one weighted stage")
        if final_stage in weights:
            raise ValueError(
                f"final_stage {final_stage!r} collides with a weighted stage name; "
                f"rename one of them"
            )

        self._cb = callback
        self._final_stage = final_stage
        total = sum(weights.values())
        pre_final = 1.0 - final_weight

        stages: dict[str, tuple[float, float]] = {}
        cursor = 0.0
        for name, w in weights.items():
            span = (w / total) * pre_final
            stages[name] = (cursor, cursor + span)
            cursor += span
        stages[final_stage] = (pre_final, 1.0)
        self._stages = stages

    def stage(self, name: str, local_p: float, msg: str) -> None:
        """Report local progress (0..1) within the named stage."""
        rng = self._stages.get(name)
        if rng is None:
            logger.warning(f"StageProgress: unknown stage {name!r}, passing through")
            self._cb(local_p, msg)
            return
        s, e = rng
        self._cb(s + local_p * (e - s), msg)

    def range(self, name: str) -> tuple[float, float]:
        """Return (start, end) overall range for a named stage. Raises KeyError if unknown."""
        return self._stages[name]
