from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .balanced_planner import BalancedGreedyPlanner
from .planner import Decision


@dataclass(frozen=True)
class WaitingEpisode:
    station_id: str
    started_ms: int


class BalancedGreedyV21Planner(BalancedGreedyPlanner):
    """Balanced V2.1: keep V2 topology, repair high-pressure fleet control.

    The pinned engine does not expose passenger ``wait_ms`` in its public
    observation.  We therefore reconstruct a player-visible approximation from
    passenger IDs: a waiting episode starts when an ID first appears at a
    station and resets when the ID leaves or changes station.

    V2's relative fleet thresholds were impossible to satisfy on a one-line
    network (the busiest line is also the average line).  V2.1 adds an absolute
    pressure / waiting-age rescue layer after V2 declines to act.  The rescue
    layer intentionally avoids topology changes: under pressure it spends
    available capacity on the line that contains the oldest waiting riders.
    """

    name = "Balanced Greedy V2.1 Rescue"

    WARNING_WAIT_MS = 25_000
    CRITICAL_WAIT_MS = 30_000
    RESCUE_ACTION_COOLDOWN_MS = 900

    def __init__(self) -> None:
        super().__init__()
        self._waiting: dict[str, WaitingEpisode] = {}
        self._last_rescue_ms = -10_000

    def reset(self, observation: dict[str, Any]) -> None:
        super().reset(observation)
        self._waiting.clear()
        self._last_rescue_ms = -10_000
        self._update_waiting(observation)

    def _update_waiting(self, observation: dict[str, Any]) -> dict[str, int]:
        state = self._s(observation)
        now = int(state.get("time_ms", 0))
        current: dict[str, str] = {}
        for station in state.get("stations", ()):
            station_id = str(station["id"])
            for passenger_id in station.get("passenger_ids", ()):
                current[str(passenger_id)] = station_id

        next_waiting: dict[str, WaitingEpisode] = {}
        ages: dict[str, int] = {}
        for passenger_id, station_id in current.items():
            previous = self._waiting.get(passenger_id)
            if previous is None or previous.station_id != station_id:
                episode = WaitingEpisode(station_id=station_id, started_ms=now)
            else:
                episode = previous
            next_waiting[passenger_id] = episode
            ages[passenger_id] = max(0, now - episode.started_ms)

        self._waiting = next_waiting
        return ages

    @staticmethod
    def _path_metro_counts(paths: list[dict[str, Any]], metros: list[dict[str, Any]]) -> list[int]:
        counts = {path["id"]: 0 for path in paths}
        for metro in metros:
            path_id = metro.get("path_id")
            if path_id in counts:
                counts[path_id] += 1
        return [counts[path["id"]] for path in paths]

    def _rescue_target(
        self,
        paths: list[dict[str, Any]],
        stations: list[dict[str, Any]],
        ages: dict[str, int],
    ) -> tuple[int, int, int] | None:
        """Return ``(path_index, oldest_wait_ms, waiting_count)``.

        Age is the primary signal because it is what eventually ends the game;
        queue size breaks ties so the rescue still reacts before riders become
        old enough to be critical.
        """
        station_by_id = {station["id"]: station for station in stations}
        best: tuple[int, int, int] | None = None
        best_key: tuple[int, int, int] | None = None
        for path_index, path in enumerate(paths):
            passenger_ids = [
                str(passenger_id)
                for station_id in path.get("station_ids", ())
                if station_id in station_by_id
                for passenger_id in station_by_id[station_id].get("passenger_ids", ())
            ]
            oldest = max((ages.get(passenger_id, 0) for passenger_id in passenger_ids), default=0)
            waiting = len(passenger_ids)
            key = (oldest, waiting, -path_index)
            if best_key is None or key > best_key:
                best_key = key
                best = (path_index, oldest, waiting)
        return best

    def _rescue(
        self,
        observation: dict[str, Any],
        ages: dict[str, int],
    ) -> Decision | None:
        state = self._s(observation)
        paths = list(state.get("paths", ()))
        stations = list(state.get("stations", ()))
        metros = list(state.get("metros", ()))
        fleet = state.get("fleet", {})
        now = int(state.get("time_ms", 0))
        if not paths or now - self._last_rescue_ms < self.RESCUE_ACTION_COOLDOWN_MS:
            return None

        target = self._rescue_target(paths, stations, ages)
        if target is None:
            return None
        path_index, oldest_ms, waiting_count = target
        metro_counts = self._path_metro_counts(paths, metros)
        locomotives = int(fleet.get("locomotives_available", 0))
        carriages = int(fleet.get("carriages_available", 0))

        # Near the engine's 40-second deadline, visit frequency is the first
        # priority.  A fresh locomotive can reach the stranded rider sooner than
        # adding capacity to an existing train that may be on the far side of a
        # long route.
        if locomotives > 0 and oldest_ms >= self.CRITICAL_WAIT_MS:
            self._last_rescue_ms = now
            return Decision(
                {"type": "assign_locomotive", "path_index": path_index},
                "临界救火：增派机车",
                f"第 {path_index + 1} 条线路最久候车约 {oldest_ms / 1000:.1f}s，优先提高到站频率。",
            )

        # Away from the deadline, retain V1's proven capacity-first ordering.
        if carriages > 0 and metro_counts[path_index] > 0 and (
            waiting_count >= 6 or oldest_ms >= self.WARNING_WAIT_MS
        ):
            self._last_rescue_ms = now
            return Decision(
                {"type": "attach_carriage", "path_index": path_index},
                "定点救火：增加车厢",
                f"第 {path_index + 1} 条线路候车 {waiting_count} 人，最久约 {oldest_ms / 1000:.1f}s。",
            )

        if locomotives > 0 and (waiting_count >= 4 or oldest_ms >= self.WARNING_WAIT_MS):
            self._last_rescue_ms = now
            return Decision(
                {"type": "assign_locomotive", "path_index": path_index},
                "定点救火：增派机车",
                f"第 {path_index + 1} 条线路候车 {waiting_count} 人，最久约 {oldest_ms / 1000:.1f}s。",
            )
        return None

    def act(self, observation: dict[str, Any]) -> Decision:
        ages = self._update_waiting(observation)

        # V2 remains responsible for creating/serving the basic network and for
        # low-pressure topology choices.  Rescue only fills the exact hole that
        # Stress V1 exposed: V2 can decline fleet expansion forever on a single
        # line because its relative threshold compares that line with itself.
        decision = super().act(observation)
        if decision.action.get("type") != "noop":
            return decision

        rescue = self._rescue(observation, ages)
        if rescue is not None:
            return rescue
        return decision
