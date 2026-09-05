from __future__ import annotations

from dataclasses import dataclass
from typing import Any

PROBLEM_CONTRACT_VERSION = "1.0"
PROBLEM_ID = "metro-line-planning"


@dataclass(frozen=True)
class StationState:
    """Backend-neutral station state exposed to planning algorithms."""

    id: str
    index: int
    x: float
    y: float
    shape: str
    passenger_count: int


@dataclass(frozen=True)
class LineState:
    """One currently active metro line."""

    id: str
    index: int
    station_ids: tuple[str, ...]
    loop: bool


@dataclass(frozen=True)
class VehicleState:
    """Minimal vehicle placement needed by line-planning algorithms."""

    id: str
    path_id: str | None


@dataclass(frozen=True)
class FleetState:
    locomotives_available: int
    carriages_available: int


@dataclass(frozen=True)
class MetroPlanningState:
    """Canonical V1 state for the metro line-planning problem.

    This is deliberately smaller than a simulator snapshot. The problem API
    should expose information that is part of the mathematical decision
    problem, not implementation details of one simulation backend.
    """

    problem_id: str
    contract_version: str
    time_ms: int
    is_terminal: bool
    deliveries: int
    line_credits: int
    unlocked_line_count: int | None
    stations: tuple[StationState, ...]
    lines: tuple[LineState, ...]
    vehicles: tuple[VehicleState, ...]
    fleet: FleetState

    @property
    def station_by_id(self) -> dict[str, StationState]:
        return {station.id: station for station in self.stations}

    @property
    def served_station_ids(self) -> frozenset[str]:
        return frozenset(sid for line in self.lines for sid in line.station_ids)


def _shape_name(value: Any) -> str:
    if value is None:
        return "unknown"
    raw = getattr(value, "value", value)
    return str(raw)


def state_from_observation(observation: dict[str, Any]) -> MetroPlanningState:
    """Project one simulator observation onto Problem Contract V1.

    The adapter consumes only the public structured observation. It must not
    inspect ``env.mediator`` or any other privileged backend state, otherwise a
    plugin could accidentally become simulator-specific or gain hidden
    information unavailable to competing algorithms.
    """

    if not isinstance(observation, dict) or not isinstance(observation.get("structured"), dict):
        raise ValueError("observation must contain a structured mapping")

    structured = observation["structured"]
    station_rows = list(structured.get("stations", []))
    line_rows = list(structured.get("paths", []))
    vehicle_rows = list(structured.get("metros", []))
    fleet_row = structured.get("fleet", {})

    stations: list[StationState] = []
    for index, row in enumerate(station_rows):
        position = row.get("position", (0.0, 0.0))
        if not isinstance(position, (list, tuple)) or len(position) != 2:
            raise ValueError(f"station {index} has invalid position")
        stations.append(
            StationState(
                id=str(row["id"]),
                index=index,
                x=float(position[0]),
                y=float(position[1]),
                shape=_shape_name(row.get("shape_type")),
                passenger_count=int(row.get("passenger_count", 0)),
            )
        )

    lines = tuple(
        LineState(
            id=str(row["id"]),
            index=index,
            station_ids=tuple(str(sid) for sid in row.get("station_ids", ())),
            loop=bool(row.get("loop", False)),
        )
        for index, row in enumerate(line_rows)
    )

    vehicles = tuple(
        VehicleState(
            id=str(row.get("id", index)),
            path_id=None if row.get("path_id") is None else str(row.get("path_id")),
        )
        for index, row in enumerate(vehicle_rows)
    )

    unlocked = structured.get("unlocked_num_paths")
    unlocked_line_count = None if unlocked is None else int(unlocked)

    return MetroPlanningState(
        problem_id=PROBLEM_ID,
        contract_version=PROBLEM_CONTRACT_VERSION,
        time_ms=int(structured.get("time_ms", 0)),
        is_terminal=bool(structured.get("is_game_over", False)),
        deliveries=int(structured.get("deliveries", 0)),
        line_credits=int(structured.get("line_credits", 0)),
        unlocked_line_count=unlocked_line_count,
        stations=tuple(stations),
        lines=lines,
        vehicles=vehicles,
        fleet=FleetState(
            locomotives_available=int(fleet_row.get("locomotives_available", 0)),
            carriages_available=int(fleet_row.get("carriages_available", 0)),
        ),
    )
