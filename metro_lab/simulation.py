from __future__ import annotations

from dataclasses import dataclass
from typing import Any

SIMULATION_PROTOCOL_VERSION = 2


@dataclass(frozen=True)
class StepOutcome:
    """Result of one planner round under the fixed-dt evaluation protocol."""

    observation: dict[str, Any]
    done: bool
    action_ok: bool
    fallback_used: bool
    elapsed_ms: int


def advance_fixed_dt(
    env: Any,
    observation: dict[str, Any],
    action: dict[str, Any],
    *,
    dt_ms: int,
) -> StepOutcome:
    """Advance exactly one simulation tick unless the game has ended.

    The pinned engine intentionally does not advance time for a rejected action.
    Evaluation must not reward that rejection with a shorter exposure to traffic,
    so a rejected action spends the same round as a noop. ``action_ok`` always
    describes the planner's original action, not the fallback noop.
    """

    if dt_ms <= 0:
        raise ValueError("dt_ms must be positive")
    if not isinstance(action, dict):
        raise ValueError("action must be a dict")

    before_ms = int(observation["structured"].get("time_ms", 0))
    next_observation, _reward, done, info = env.step(action, dt_ms=dt_ms)
    action_ok = bool(info.get("action_ok", False))
    fallback_used = False

    if not action_ok and not done:
        next_observation, _reward, done, _fallback_info = env.step(
            {"type": "noop"}, dt_ms=dt_ms
        )
        fallback_used = True

    after_ms = int(next_observation["structured"].get("time_ms", 0))
    elapsed_ms = after_ms - before_ms
    if not done and elapsed_ms != dt_ms:
        raise RuntimeError(
            "fixed-dt protocol violation: "
            f"expected {dt_ms} ms, observed {elapsed_ms} ms"
        )
    if elapsed_ms < 0:
        raise RuntimeError("simulation time moved backwards")

    return StepOutcome(
        observation=next_observation,
        done=bool(done),
        action_ok=action_ok,
        fallback_used=fallback_used,
        elapsed_ms=elapsed_ms,
    )
