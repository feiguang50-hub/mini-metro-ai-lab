from __future__ import annotations

from dataclasses import dataclass
from math import hypot
from statistics import mean
from typing import Any

from .planner import Decision, GreedyPlanner
from .pressure import passenger_pressure
from .rollout import RolloutSnapshot, restore_sampled_future
from .scenarios import advance_scenario
from .simulation import advance_fixed_dt

Action = dict[str, Any]


@dataclass(frozen=True)
class CandidateScore:
    action: Action
    expected_deliveries: float
    expected_survival_ms: float
    expected_peak_risk: float
    valid_rate: float
    samples: int

    @property
    def ranking_key(self) -> tuple[float, float, float, float]:
        # Deliveries are the primary objective. Survival and lower risk break
        # ties; validity is last because Protocol V2 already charges rejected
        # actions a full tick and we must not secretly invent a new reward.
        return (
            self.expected_deliveries,
            self.expected_survival_ms,
            -self.expected_peak_risk,
            self.valid_rate,
        )


@dataclass(frozen=True)
class ProbeResult:
    baseline_action: Action
    best: CandidateScore
    scores: tuple[CandidateScore, ...]


def _action_key(action: Action) -> tuple:
    return tuple(sorted((str(key), repr(value)) for key, value in action.items()))


def _distance(a: dict[str, Any], b: dict[str, Any]) -> float:
    ax, ay = a["position"]
    bx, by = b["position"]
    return hypot(float(ax) - float(bx), float(ay) - float(by))


def _insertion_candidates(
    observation: dict[str, Any], *, per_path_limit: int = 2
) -> list[Action]:
    s = observation["structured"]
    stations = list(s["stations"])
    paths = list(s["paths"])
    if not stations or not paths:
        return []

    station_index = {station["id"]: idx for idx, station in enumerate(stations)}
    station_by_id = {station["id"]: station for station in stations}
    served = {sid for path in paths for sid in path["station_ids"]}
    unserved = [station for station in stations if station["id"] not in served]
    actions: list[Action] = []

    for path_index, path in enumerate(paths):
        ids = list(path["station_ids"])
        if len(ids) < 2 or any(sid not in station_index for sid in ids):
            continue
        scored: list[tuple[float, Action]] = []
        for station in unserved:
            # Prepend / append and every internal insertion are all considered,
            # then only a tiny geometry-ranked subset is exposed to the probe.
            variants: list[tuple[float, list[str]]] = []
            first = station_by_id[ids[0]]
            last = station_by_id[ids[-1]]
            variants.append((_distance(station, first), [station["id"], *ids]))
            variants.append((_distance(last, station), [*ids, station["id"]]))
            for pos in range(len(ids) - 1):
                a = station_by_id[ids[pos]]
                b = station_by_id[ids[pos + 1]]
                extra = _distance(a, station) + _distance(station, b) - _distance(a, b)
                variants.append((extra, [*ids[: pos + 1], station["id"], *ids[pos + 1 :]]))
            for cost, route_ids in variants:
                scored.append(
                    (
                        cost,
                        {
                            "type": "replace_path",
                            "path_index": path_index,
                            "stations": [station_index[sid] for sid in route_ids],
                            "loop": False,
                        },
                    )
                )
        scored.sort(key=lambda item: (item[0], _action_key(item[1])))
        actions.extend(action for _cost, action in scored[:per_path_limit])
    return actions


def generate_candidates(
    observation: dict[str, Any], baseline: Decision, *, max_candidates: int = 8
) -> tuple[Action, ...]:
    """Small deterministic candidate set for one-decision search diagnostics.

    This is deliberately conservative: it includes the baseline and WAIT, then
    resource-placement alternatives and a few nearest insertion alternatives.
    The probe tests whether stochastic evaluation contains signal; it is not a
    claim that this is the final Beam/MPC action generator.
    """

    if max_candidates < 2:
        raise ValueError("max_candidates must be at least 2")
    s = observation["structured"]
    paths = list(s["paths"])
    fleet = s["fleet"]

    actions: list[Action] = [dict(baseline.action), {"type": "noop"}]
    if int(fleet["locomotives_available"]) > 0:
        actions.extend(
            {"type": "assign_locomotive", "path_index": idx}
            for idx in range(len(paths))
        )
    if int(fleet["carriages_available"]) > 0:
        actions.extend(
            {"type": "attach_carriage", "path_index": idx}
            for idx in range(len(paths))
        )
    actions.extend(_insertion_candidates(observation))

    unique: list[Action] = []
    seen: set[tuple] = set()
    for action in actions:
        key = _action_key(action)
        if key in seen:
            continue
        seen.add(key)
        unique.append(action)
        if len(unique) >= max_candidates:
            break
    return tuple(unique)


def _rollout_candidate(
    snapshot: RolloutSnapshot,
    action: Action,
    *,
    future_key: int,
    scenario_id: str,
    horizon_ms: int,
) -> tuple[int, int, float, bool]:
    env = restore_sampled_future(snapshot, future_key)
    planner = GreedyPlanner()
    observation = env.observe()
    planner.reset(observation)
    start_deliveries = int(observation["structured"]["deliveries"])
    start_ms = int(observation["structured"]["time_ms"])
    peak_risk = float(passenger_pressure(env).risk_pct)

    first = advance_fixed_dt(env, observation, action, dt_ms=snapshot.dt_ms)
    observation = first.observation
    if advance_scenario(env, scenario_id):
        observation = env.observe()
    peak_risk = max(peak_risk, float(passenger_pressure(env).risk_pct))
    first_ok = first.action_ok

    target_ms = start_ms + int(horizon_ms)
    while not first.done and int(observation["structured"]["time_ms"]) < target_ms:
        decision = planner.act(observation)
        outcome = advance_fixed_dt(env, observation, decision.action, dt_ms=snapshot.dt_ms)
        observation = outcome.observation
        if advance_scenario(env, scenario_id):
            observation = env.observe()
        peak_risk = max(peak_risk, float(passenger_pressure(env).risk_pct))
        if outcome.done:
            break

    end_ms = int(observation["structured"]["time_ms"])
    deliveries = int(observation["structured"]["deliveries"]) - start_deliveries
    return deliveries, end_ms - start_ms, peak_risk, bool(first_ok)


def score_candidates(
    snapshot: RolloutSnapshot,
    candidates: tuple[Action, ...],
    *,
    future_keys: tuple[int, ...],
    scenario_id: str,
    horizon_ms: int,
) -> tuple[CandidateScore, ...]:
    if not candidates:
        raise ValueError("at least one candidate is required")
    if not future_keys:
        raise ValueError("at least one sampled future is required")
    if horizon_ms <= 0:
        raise ValueError("horizon_ms must be positive")

    scores: list[CandidateScore] = []
    for action in candidates:
        samples = [
            _rollout_candidate(
                snapshot,
                action,
                future_key=key,
                scenario_id=scenario_id,
                horizon_ms=horizon_ms,
            )
            for key in future_keys
        ]
        scores.append(
            CandidateScore(
                action=dict(action),
                expected_deliveries=mean(sample[0] for sample in samples),
                expected_survival_ms=mean(sample[1] for sample in samples),
                expected_peak_risk=mean(sample[2] for sample in samples),
                valid_rate=mean(1.0 if sample[3] else 0.0 for sample in samples),
                samples=len(samples),
            )
        )
    return tuple(scores)


def run_probe(
    snapshot: RolloutSnapshot,
    observation: dict[str, Any],
    baseline: Decision,
    *,
    future_keys: tuple[int, ...],
    scenario_id: str,
    horizon_ms: int = 120_000,
    max_candidates: int = 8,
) -> ProbeResult:
    candidates = generate_candidates(
        observation,
        baseline,
        max_candidates=max_candidates,
    )
    scores = score_candidates(
        snapshot,
        candidates,
        future_keys=future_keys,
        scenario_id=scenario_id,
        horizon_ms=horizon_ms,
    )
    best = max(scores, key=lambda score: (score.ranking_key, tuple(reversed(_action_key(score.action)))))
    return ProbeResult(
        baseline_action=dict(baseline.action),
        best=best,
        scores=scores,
    )
