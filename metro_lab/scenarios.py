from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

CLASSIC_SCENARIO_ID = "classic-v1"
STRESS_SCENARIO_ID = "stress-v1"
DEFAULT_SCENARIO_ID = CLASSIC_SCENARIO_ID
STRESS_STATION_SPAWN_INTERVAL_MS = 45_000


@dataclass(frozen=True)
class ScenarioSpec:
    id: str
    name: str
    version: str
    summary: str
    station_spawn_interval_ms: int | None = None

    def public(self) -> dict[str, Any]:
        return asdict(self)


SCENARIO_SPECS: tuple[ScenarioSpec, ...] = (
    ScenarioSpec(
        id=CLASSIC_SCENARIO_ID,
        name="Classic V1",
        version="1.0",
        summary="固定上游原始站点推进逻辑，用于历史兼容基线。",
    ),
    ScenarioSpec(
        id=STRESS_SCENARIO_ID,
        name="Stress V1",
        version="1.0",
        summary="固定 Seed 站点池，开局保留初始站点，之后每 45 秒模拟时间开放一个新站直到上限。",
        station_spawn_interval_ms=STRESS_STATION_SPAWN_INTERVAL_MS,
    ),
)

SCENARIOS = {spec.id: spec for spec in SCENARIO_SPECS}


def get_scenario_spec(scenario_id: str) -> ScenarioSpec:
    try:
        return SCENARIOS[scenario_id]
    except KeyError as exc:
        raise ValueError(f"unknown scenario: {scenario_id}") from exc


def scenario_catalog() -> list[dict[str, Any]]:
    return [spec.public() for spec in SCENARIO_SPECS]


def scenario_ids() -> list[str]:
    return [spec.id for spec in SCENARIO_SPECS]


def _configure_timed_stations(env: Any, interval_ms: int) -> None:
    if interval_ms <= 0:
        raise ValueError("station spawn interval must be positive")
    mediator = env.mediator
    progression = mediator._progression
    progression.station_unlock_milestones = [
        2_147_483_647 + index
        for index in range(mediator.num_stations - mediator.initial_num_stations)
    ]
    progression.set_unlocked_num_stations(mediator.initial_num_stations)
    mediator.unlocked_num_stations = mediator.initial_num_stations
    mediator.stations = mediator.all_stations[: mediator.initial_num_stations]


def configure_scenario(env: Any, scenario_id: str) -> bool:
    """Configure a deterministic scenario on a freshly-reset environment.

    Returns True when the visible observation was mutated and callers should
    refresh `env.observe()` before resetting a planner.
    """
    spec = get_scenario_spec(scenario_id)
    if spec.station_spawn_interval_ms is None:
        return False
    _configure_timed_stations(env, spec.station_spawn_interval_ms)
    return True


def advance_scenario(env: Any, scenario_id: str) -> bool:
    """Apply scenario events due at the current simulated clock."""
    spec = get_scenario_spec(scenario_id)
    interval_ms = spec.station_spawn_interval_ms
    if interval_ms is None:
        return False

    mediator = env.mediator
    target = min(
        mediator.num_stations,
        mediator.initial_num_stations + mediator.time_ms // interval_ms,
    )
    if target <= len(mediator.stations):
        return False

    newly_unlocked = mediator.all_stations[len(mediator.stations) : target]
    mediator.stations = mediator.all_stations[:target]
    mediator._progression.set_unlocked_num_stations(target)
    mediator.unlocked_num_stations = target
    mediator.initialize_station_spawning_state(newly_unlocked)
    for station in newly_unlocked:
        station.start_unlock_blink(mediator.time_ms)
    return True


def scenario_status(env: Any, scenario_id: str) -> dict[str, Any]:
    spec = get_scenario_spec(scenario_id)
    mediator = env.mediator
    count = len(mediator.stations)
    interval_ms = spec.station_spawn_interval_ms
    next_at: int | None = None
    if interval_ms is not None and count < mediator.num_stations:
        next_at = (count - mediator.initial_num_stations + 1) * interval_ms

    return {
        "scenario_id": spec.id,
        "scenario_name": spec.name,
        "station_count": count,
        "station_limit": mediator.num_stations,
        "station_spawn_interval_ms": interval_ms,
        "next_station_at_ms": next_at,
        "next_station_in_ms": (
            None if next_at is None else max(0, next_at - mediator.time_ms)
        ),
    }
