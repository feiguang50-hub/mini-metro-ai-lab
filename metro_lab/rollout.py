from __future__ import annotations

import copy
import random
from dataclasses import dataclass
from typing import Any

import numpy as np

from .config import TICK_MS
from .engine import _load_engine


@dataclass(frozen=True)
class RolloutSnapshot:
    """A quiescent game snapshot that can seed isolated planning futures.

    The save document deliberately contains the engine RNG state because exact
    save/load fidelity requires it. Search code must therefore never score an
    action by restoring this document verbatim: doing so would replay the same
    hidden future that the live episode will experience.
    """

    document: dict[str, Any]
    dt_ms: int
    reward_mode: str
    source_time_ms: int


def _load_snapshot_codec():
    # `_load_engine` owns the pinned-engine sys.path boundary. Import save/load
    # only after that boundary has been established so this module never
    # accidentally resolves another python_mini_metro checkout.
    MiniMetroEnv, _engine_config = _load_engine()
    from save_game import serialize_game  # type: ignore
    from save_load import deserialize_game  # type: ignore

    return MiniMetroEnv, serialize_game, deserialize_game


def capture_rollout_snapshot(env: Any) -> RolloutSnapshot:
    """Capture the current board without exposing an oracle-future API."""

    _MiniMetroEnv, serialize_game, _deserialize_game = _load_snapshot_codec()
    dt_ms = env.dt_ms_default if env.dt_ms_default is not None else TICK_MS
    document = serialize_game(env.mediator)
    return RolloutSnapshot(
        document=document,
        dt_ms=int(dt_ms),
        reward_mode=str(env.reward_mode),
        source_time_ms=int(env.mediator.time_ms),
    )


def sample_future_keys(master_seed: int, count: int) -> tuple[int, ...]:
    """Generate deterministic future keys shared by every candidate action.

    Candidate A and candidate B at one decision point must receive the SAME key
    list. That is common-random-numbers evaluation: future noise is paired so
    action differences are easier to distinguish from spawn luck.
    """

    if count <= 0:
        raise ValueError("future sample count must be positive")
    rng = np.random.default_rng(int(master_seed))
    return tuple(
        int(value)
        for value in rng.integers(0, 2**31 - 1, size=int(count), dtype=np.int64)
    )


def _reseed_document(document: dict[str, Any], future_key: int) -> dict[str, Any]:
    """Copy one board and replace only its stochastic future."""

    variant = copy.deepcopy(document)
    key = int(future_key)
    variant["rng"] = {
        "python": random.Random(key).getstate(),
        "numpy": np.random.default_rng(key).bit_generator.state,
    }
    return variant


def _restore(snapshot: RolloutSnapshot, document: dict[str, Any]):
    MiniMetroEnv, _serialize_game, deserialize_game = _load_snapshot_codec()
    env = MiniMetroEnv(dt_ms=snapshot.dt_ms, reward_mode=snapshot.reward_mode)
    env.mediator = deserialize_game(document)
    # A rollout starts measuring reward from the captured state, not from the
    # temporary environment constructor's blank city.
    env.last_deliveries = env.mediator.deliveries
    env.last_line_credits = env.mediator.line_credits
    return env


def restore_sampled_future(snapshot: RolloutSnapshot, future_key: int):
    """Create an isolated rollout with a future the live agent could not know.

    This is the only non-test restore entry point. Search planners should never
    receive an exact-restored environment whose RNG came from the live episode.
    """

    return _restore(snapshot, _reseed_document(snapshot.document, future_key))


def _restore_exact_for_test(snapshot: RolloutSnapshot):
    """Exact save/load round-trip used only to prove snapshot fidelity in tests."""

    return _restore(snapshot, copy.deepcopy(snapshot.document))
