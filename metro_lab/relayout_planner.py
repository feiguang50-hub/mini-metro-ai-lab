from __future__ import annotations

from math import inf
from typing import Any

from .planner import Decision
from .rescue_planner import BalancedGreedyV21Planner


class BalancedGreedyV22Planner(BalancedGreedyV21Planner):
    """V2.2 candidate: V2.1 plus evidence-gated 2-opt relayout.

    The pinned upstream's own large-sample experiments found that rebuilding for
    tiny geometric gains thrashes, while a roughly 15-20% route-length saving
    is the useful regime. We therefore compute a complete 2-opt local optimum
    in memory and submit one atomic ``replace_path`` only when the whole target
    is more than 20% shorter than the live route.

    No rollout, hidden engine state, future RNG, or private passenger wait clock
    is used. The first station remains anchored (matching the upstream probe),
    while the other endpoint may change if that is part of the shorter order.
    """

    name = "Balanced Greedy V2.2 Relayout"
    EPSILON = 1e-6
    MIN_STATIONS = 5
    MIN_SAVING_RATIO = 0.20

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
    def _two_opt_target(
        cls,
        path: dict[str, Any],
        station_by_id: dict[str, dict[str, Any]],
    ) -> tuple[float, float, list[str]] | None:
        """Return ``(saving_ratio, improvement_px, locally_optimal_route)``.

        This mirrors the upstream experiment's repeated 2-opt probe rather than
        acting on the first tiny improvement. Index 0 stays anchored; the tail
        may move. The target is computed without mutating the live engine.
        """
        if bool(path.get("is_looped", False)):
            return None
        route = [str(station_id) for station_id in path.get("station_ids", ())]
        if len(route) < cls.MIN_STATIONS or len(set(route)) != len(route):
            return None

        current_length = cls._route_length(route, station_by_id)
        if current_length in (0.0, inf):
            return None

        best = list(route)
        best_length = current_length
        improved = True
        while improved:
            improved = False
            # Same neighborhood as the upstream probe: keep the first station
            # anchored, reverse any later segment, including one ending at tail.
            for i in range(len(best) - 1):
                for j in range(i + 2, len(best)):
                    candidate = [
                        *best[: i + 1],
                        *reversed(best[i + 1 : j + 1]),
                        *best[j + 1 :],
                    ]
                    value = cls._route_length(candidate, station_by_id)
                    if value < best_length - cls.EPSILON:
                        best = candidate
                        best_length = value
                        improved = True

        improvement = current_length - best_length
        if improvement <= cls.EPSILON:
            return None
        return improvement / current_length, improvement, best

    def _best_relayout(
        self,
        paths: list[dict[str, Any]],
        station_by_id: dict[str, dict[str, Any]],
    ) -> tuple[float, float, int, list[str]] | None:
        best: tuple[float, float, int, list[str]] | None = None
        for path_index, path in enumerate(paths):
            candidate = self._two_opt_target(path, station_by_id)
            if candidate is None:
                continue
            saving_ratio, improvement, route = candidate
            if saving_ratio <= self.MIN_SAVING_RATIO:
                continue
            signature = (
                str(path.get("id", path_index)),
                tuple(str(item) for item in path.get("station_ids", ())),
                tuple(route),
            )
            if signature in self._attempted_relayouts:
                continue
            item = (saving_ratio, improvement, path_index, route)
            if best is None or (saving_ratio, improvement, -path_index) > (
                best[0],
                best[1],
                -best[2],
            ):
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

        saving_ratio, improvement, path_index, route_ids = best
        station_index = {str(station["id"]): idx for idx, station in enumerate(stations)}
        if any(station_id not in station_index for station_id in route_ids):
            return decision

        path = paths[path_index]
        before_route_ids = [str(item) for item in path.get("station_ids", ())]
        signature = (
            str(path.get("id", path_index)),
            tuple(before_route_ids),
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
                "_lab_kind": "relayout-2opt",
                "_lab_improvement_px": round(float(improvement), 3),
                "_lab_saving_ratio": round(float(saving_ratio), 6),
                "_lab_before_route": before_route_ids,
                "_lab_after_route": list(route_ids),
            },
            "2-opt 重排线路",
            (
                f"第 {path_index + 1} 条线路可整体缩短 {saving_ratio:.1%} "
                f"（约 {improvement:.1f}px），超过 20% 研究门槛。"
            ),
        )
