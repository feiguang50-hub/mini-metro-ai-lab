from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

from .problem import MetroPlanningState

ACTION_CONTRACT_VERSION = "1.0"


class ActionTranslationError(ValueError):
    """Raised when a semantic planning action cannot be mapped to a backend action."""


@dataclass(frozen=True)
class NoOpAction:
    pass


@dataclass(frozen=True)
class CreateLineAction:
    station_ids: tuple[str, ...]
    loop: bool = False


@dataclass(frozen=True)
class ReplaceLineAction:
    line_id: str
    station_ids: tuple[str, ...]
    loop: bool = False


@dataclass(frozen=True)
class AssignLocomotiveAction:
    line_id: str


@dataclass(frozen=True)
class AttachCarriageAction:
    line_id: str


PlanningAction: TypeAlias = (
    NoOpAction
    | CreateLineAction
    | ReplaceLineAction
    | AssignLocomotiveAction
    | AttachCarriageAction
)


@dataclass(frozen=True)
class PlanningDecision:
    """Backend-neutral decision envelope returned by algorithm plugins."""

    action: PlanningAction
    title: str
    detail: str


def _station_index(state: MetroPlanningState) -> dict[str, int]:
    return {station.id: index for index, station in enumerate(state.stations)}


def _line_index(state: MetroPlanningState) -> dict[str, int]:
    return {line.id: index for index, line in enumerate(state.lines)}


def _require_station_indices(
    state: MetroPlanningState,
    station_ids: tuple[str, ...],
) -> list[int]:
    by_id = _station_index(state)
    missing = [station_id for station_id in station_ids if station_id not in by_id]
    if missing:
        raise ActionTranslationError(f"unknown station id(s): {', '.join(missing)}")
    return [by_id[station_id] for station_id in station_ids]


def _require_line_index(state: MetroPlanningState, line_id: str) -> int:
    by_id = _line_index(state)
    try:
        return by_id[line_id]
    except KeyError as exc:
        raise ActionTranslationError(f"unknown line id: {line_id}") from exc


def to_backend_action(state: MetroPlanningState, action: PlanningAction) -> dict[str, object]:
    """Translate Action Contract V1 into the current Mini Metro backend action.

    Algorithms never need to know simulator path indexes or station indexes.
    Those ephemeral backend coordinates are resolved only at this adapter edge.
    """

    if isinstance(action, NoOpAction):
        return {"type": "noop"}

    if isinstance(action, CreateLineAction):
        return {
            "type": "create_path",
            "stations": _require_station_indices(state, action.station_ids),
            "loop": action.loop,
        }

    if isinstance(action, ReplaceLineAction):
        return {
            "type": "replace_path",
            "path_index": _require_line_index(state, action.line_id),
            "stations": _require_station_indices(state, action.station_ids),
            "loop": action.loop,
        }

    if isinstance(action, AssignLocomotiveAction):
        return {
            "type": "assign_locomotive",
            "path_index": _require_line_index(state, action.line_id),
        }

    if isinstance(action, AttachCarriageAction):
        return {
            "type": "attach_carriage",
            "path_index": _require_line_index(state, action.line_id),
        }

    raise ActionTranslationError(f"unsupported action type: {type(action).__name__}")
