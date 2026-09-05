from __future__ import annotations

from typing import Any


STATION_SPAWN_INTERVAL_MS = 45_000


def configure_timed_station_progression(env: Any) -> None:
    """Use a deterministic clock for station unlocks in live viewers.

    The pinned engine unlocks stations at delivery totals 10, 30, 60, ... .
    A 15-minute viewer run therefore exposes only four or five stations.  The
    viewer profile keeps the engine's pre-generated seeded station pool, but
    reveals one station every fixed amount of simulated time instead.
    """
    mediator = env.mediator
    progression = mediator._progression
    progression.station_unlock_milestones = [
        2_147_483_647 + index for index in range(mediator.num_stations - mediator.initial_num_stations)
    ]
    progression.set_unlocked_num_stations(mediator.initial_num_stations)
    mediator.unlocked_num_stations = mediator.initial_num_stations
    mediator.stations = mediator.all_stations[: mediator.initial_num_stations]


def advance_timed_station_progression(env: Any) -> bool:
    """Reveal stations due at the current simulated time.

    Returns True when at least one station became visible, so callers can
    refresh the observation produced immediately before this update.
    """
    mediator = env.mediator
    target = min(
        mediator.num_stations,
        mediator.initial_num_stations + mediator.time_ms // STATION_SPAWN_INTERVAL_MS,
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


def timed_station_status(env: Any) -> dict[str, int | None]:
    mediator = env.mediator
    count = len(mediator.stations)
    if count >= mediator.num_stations:
        next_at = None
    else:
        next_at = (count - mediator.initial_num_stations + 1) * STATION_SPAWN_INTERVAL_MS
    return {
        "station_count": count,
        "station_limit": mediator.num_stations,
        "station_spawn_interval_ms": STATION_SPAWN_INTERVAL_MS,
        "next_station_at_ms": next_at,
        "next_station_in_ms": None if next_at is None else max(0, next_at - mediator.time_ms),
    }
