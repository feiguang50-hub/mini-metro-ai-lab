from __future__ import annotations

from typing import Any

from .scenarios import (
    STRESS_SCENARIO_ID,
    STRESS_STATION_SPAWN_INTERVAL_MS,
    advance_scenario,
    configure_scenario,
    scenario_status,
)

# Backward-compatible name used by viewer tests and UI contracts.
STATION_SPAWN_INTERVAL_MS = STRESS_STATION_SPAWN_INTERVAL_MS


def configure_timed_station_progression(env: Any) -> None:
    """Configure the browser viewer with the versioned Stress V1 profile."""
    configure_scenario(env, STRESS_SCENARIO_ID)


def advance_timed_station_progression(env: Any) -> bool:
    """Reveal viewer stations due under Stress V1."""
    return advance_scenario(env, STRESS_SCENARIO_ID)


def timed_station_status(env: Any) -> dict[str, Any]:
    """Return viewer progression status from the shared scenario registry."""
    return scenario_status(env, STRESS_SCENARIO_ID)
