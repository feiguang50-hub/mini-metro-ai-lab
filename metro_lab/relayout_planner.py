from __future__ import annotations

from math import inf
from typing import Any

from .planner import Decision
from .rescue_planner import BalancedGreedyV21Planner


class BalancedGreedyV22Planner(BalancedGreedyV21Planner):
    """V2.2 candidate: V2.1 plus conservative geometry-only 2-opt relayout.

    The relayout layer runs only after V2.1 has declined to act and only when
    every active station is already served. It preserves an open line's two
    endpoints and station set, reverses one internal segment, and accepts the
    move only when Euclidean route length strictly decreases.

    No rollout, hidden engine state, future RNG, or passenger wait clock is used.
    A proposed transition is remembered by its before/after signature so an
    engine-rejected move is not hammered every tick.
    """

    name = "Balanced Greedy V2.2 Relayout"
    EPSILON = 1e-6

    def __init__(self) -> None:
        super().__init__()
        self._attempted_relayouts: set[
            tuple[str, tuple[str, ...], tuple[str, ...]]
        ] = set()

    def reset(self, observation: dict[str, Any]) -> None:
        super().reset(observation)
        self._attempted_relayouts.clear()

    @classmethod
    def _route_length(
        cls,
        route_ids: list[str],
        station_by_id: dict[str, dict[str, Any]],
    ) -> float:
        if any(station_id not in station_by_id for station_id in route_ids):
            return inf
        return sum(
            cls._distance(station_by_id[first], station_by_id[second])
            for first, second in zip(route_ids, route_ids[1:])
        )

    @classmethod
    def _best_two_opt_for_path(
        cls,
        path: dict[str, Any],
        station_by_id: dict[str, dict[str, Any]],
    ) -> tuple[float, list[str]] | None:
        """Return the best endpoint-preserving internal 2-opt move.

        This is intentionally narrower than a general TSP 2-opt neighborhood:
        open-line endpoints stay fixed so the candidate does not silently alter
        which stations have terminal service characteristics.
        """
        if bool(path.get("is_looped", False)):
            return None
        route = [str(station_id) for station_id in path.get("station_ids", ())]
        if len(route) < 4 or len(set(route)) != len(route):
            return None

        current_length = cls._route_length(route, station_by_id)
        if current_length == inf:
            return None

        best_improvement = cls.EPSILON
        best_route: list[str] | None = None

        # Keep index 0 and index n-1 fixed. Reversing route[i:j+1] is the
        # standard 2-opt reconnection for the two boundary edges around it.
        for i in range(1, len(route) - 2):
            for j in range(i + 1, len(route) - 1):
                candidate = [*route[:i], *reversed(route[i : j + 1]), *route[j + 1 :]]
                improvement = current_length - cls._route_length(candidate, station_by_id)
                if improvement > best_improvement:
                    best_improvement = improvement
                    best_route = candidate

        if best_route is None:
            return None
        return best_improvement, best_route

    def _best_relayout(
        self,
        paths: list[dict[str, Any]],
        station_by_id: dict[str, dict[str, Any]],
    ) -> tuple[float, int, list[str]] | None:
        best: tuple[float, int, list[str]] | None = None
        for path_index, path in enumerate(paths):
            candidate = self._best_two_opt_for_path(path, station_by_id)
            if candidate is None:
                continue
            improvement, route = candidate
            signature = (
                str(path.get("id", path_index)),
                tuple(str(item) for item in path.get("station_ids", ())),
                tuple(route),
            )
            if signature in self._attempted_relayouts:
                continue
            item = (improvement, path_index, route)
            if best is None or improvement > best[0] + self.EPSILON:
                best = item
        return best

    def act(self, observation: dict[str, Any]) -> Decision:
        decision = super().act(observation)
        if decision.action.get("type") != "noop":
            return decision

        state = self._s(observation)
        stations = list(state.get("stations", ()))
        paths = list(state.get("paths", ()))
        if not stations or not paths:
            return decision

        station_by_id = {str(station["id"]): station for station in stations}
        served = {
            str(station_id)
            for path in paths
            for station_id in path.get("station_ids", ())
        }
        if any(str(station["id"]) not in served for station in stations):
            return decision

        best = self._best_relayout(paths, station_by_id)
        if best is None:
            return decision

        improvement, path_index, route_ids = best
        station_index = {str(station["id"]): idx for idx, station in enumerate(stations)}
        if any(station_id not in station_index for station_id in route_ids):
            return decision

        path = paths[path_index]
        signature = (
            str(path.get("id", path_index)),
            tuple(str(item) for item in path.get("station_ids", ())),
            tuple(route_ids),
        )
        self._attempted_relayouts.add(signature)
        self._last_topology_ms = int(state.get("time_ms", 0))
        route_indices = [station_index[station_id] for station_id in route_ids]
        return Decision(
            {
                "type": "replace_path",
                "path_index": path_index,
                "stations": route_indices,
                "loop": False,
            },
            "2-opt 缩短线路",
            f"第 {path_index + 1} 条线路保持端点不变，预计减少约 {improvement:.1f} 像素绕行。",
        )
