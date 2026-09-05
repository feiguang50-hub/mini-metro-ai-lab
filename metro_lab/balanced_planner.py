from __future__ import annotations

from typing import Any

from .planner import Decision, GreedyPlanner


class BalancedGreedyPlanner(GreedyPlanner):
    """V2 heuristic that balances geometry, line load, diversity and network spread."""

    name = "Balanced Greedy V2"

    def __init__(self) -> None:
        super().__init__()
        self._topology_cooldown_ms = 900

    @staticmethod
    def _shape(station: dict[str, Any]) -> str:
        return str(station.get("shape_type", "unknown"))

    def _initial_route(self, stations: list[dict[str, Any]]) -> list[int]:
        count = min(3, len(stations))
        if count <= 1:
            return list(range(count))

        best_route: list[int] | None = None
        best_score: tuple[int, float] | None = None
        indices = list(range(len(stations)))
        for start in indices:
            route = [start]
            remaining = [idx for idx in indices if idx != start]
            while remaining and len(route) < count:
                used_shapes = {self._shape(stations[idx]) for idx in route}
                current = stations[route[-1]]
                nxt = min(
                    remaining,
                    key=lambda idx: (
                        self._shape(stations[idx]) in used_shapes,
                        self._distance(current, stations[idx]),
                    ),
                )
                route.append(nxt)
                remaining.remove(nxt)
            shapes = len({self._shape(stations[idx]) for idx in route})
            length = sum(self._distance(stations[a], stations[b]) for a, b in zip(route, route[1:]))
            score = (-shapes, length)
            if best_score is None or score < best_score:
                best_score = score
                best_route = route
        return best_route or list(range(count))

    def _balanced_insertion(
        self,
        path: dict[str, Any],
        station: dict[str, Any],
        station_index: dict[str, int],
        station_by_id: dict[str, dict[str, Any]],
    ) -> tuple[float, list[int]] | None:
        base = self._best_insertion(path, station, station_index, station_by_id)
        if base is None:
            return None
        extra_distance, route = base
        pressure = self._path_pressure(path, station_by_id)
        length_penalty = max(0, len(path.get("station_ids", [])) - 4) * 24.0
        pressure_penalty = pressure * 14.0

        existing_shapes = [
            self._shape(station_by_id[sid])
            for sid in path.get("station_ids", [])
            if sid in station_by_id
        ]
        shape_bonus = -42.0 if self._shape(station) not in existing_shapes else 18.0
        return extra_distance + length_penalty + pressure_penalty + shape_bonus, route

    def _new_line_candidate(
        self,
        station: dict[str, Any],
        stations: list[dict[str, Any]],
        station_index: dict[str, int],
    ) -> list[int] | None:
        if len(stations) < 2:
            return None
        others = [item for item in stations if item["id"] != station["id"]]
        if not others:
            return None

        nearest = min(others, key=lambda item: self._distance(station, item))
        route_ids = [station["id"], nearest["id"]]

        third_candidates = [item for item in others if item["id"] != nearest["id"]]
        if third_candidates:
            used_shapes = {self._shape(station), self._shape(nearest)}
            third = min(
                third_candidates,
                key=lambda item: (
                    self._shape(item) in used_shapes,
                    self._distance(nearest, item),
                ),
            )
            route_ids.append(third["id"])
        return [station_index[sid] for sid in route_ids]

    def act(self, observation: dict[str, Any]) -> Decision:
        s = self._s(observation)
        stations = list(s["stations"])
        paths = list(s["paths"])
        metros = list(s["metros"])
        fleet = s["fleet"]
        now = int(s["time_ms"])

        if len(stations) >= 2 and not paths:
            route = self._initial_route(stations)
            self._last_topology_ms = now
            return Decision(
                {"type": "create_path", "stations": route, "loop": False},
                "建立均衡骨架",
                "优先覆盖不同站型，同时控制首条线路的几何长度。",
            )

        if paths and int(fleet["locomotives_available"]) > 0:
            metro_count: dict[str, int] = {path["id"]: 0 for path in paths}
            for metro in metros:
                pid = metro.get("path_id")
                if pid in metro_count:
                    metro_count[pid] += 1
            empty = next((idx for idx, path in enumerate(paths) if metro_count[path["id"]] == 0), None)
            if empty is not None:
                return Decision(
                    {"type": "assign_locomotive", "path_index": empty},
                    "启动新线路",
                    f"第 {empty + 1} 条线路尚未服务，先投放机车。",
                )

        station_index = {station["id"]: idx for idx, station in enumerate(stations)}
        station_by_id = {station["id"]: station for station in stations}
        served = {sid for path in paths for sid in path["station_ids"]}
        unserved = [station for station in stations if station["id"] not in served]

        if unserved and paths and now - self._last_topology_ms >= self._topology_cooldown_ms:
            unlocked = int(s.get("unlocked_num_paths", len(paths)))
            longest = max((len(path.get("station_ids", [])) for path in paths), default=0)
            can_open_line = len(paths) < unlocked

            if can_open_line and (longest >= 5 or len(unserved) >= 2):
                target = max(
                    unserved,
                    key=lambda station: min(
                        self._distance(station, station_by_id[sid])
                        for sid in served
                        if sid in station_by_id
                    ) if served else 0,
                )
                route = self._new_line_candidate(target, stations, station_index)
                if route is not None:
                    self._last_topology_ms = now
                    return Decision(
                        {"type": "create_path", "stations": route, "loop": False},
                        "新开分流线路",
                        "现有线路已偏长或新增站集中，另开线路降低单线负担。",
                    )

            best: tuple[float, int, list[int], dict[str, Any]] | None = None
            for station in unserved:
                for path_idx, path in enumerate(paths):
                    candidate = self._balanced_insertion(path, station, station_index, station_by_id)
                    if candidate is None:
                        continue
                    score, route = candidate
                    item = (score, path_idx, route, station)
                    if best is None or score < best[0]:
                        best = item
            if best is not None:
                score, path_idx, route, station = best
                self._last_topology_ms = now
                return Decision(
                    {"type": "replace_path", "path_index": path_idx, "stations": route, "loop": False},
                    "均衡接入新站",
                    f"综合绕行、线路长度、站型和客流后，选择第 {path_idx + 1} 条线路，综合代价 {score:.0f}。",
                )

        if paths:
            pressures = [self._path_pressure(path, station_by_id) for path in paths]
            busiest_idx = max(range(len(paths)), key=pressures.__getitem__)
            busiest_pressure = pressures[busiest_idx]
            average_pressure = sum(pressures) / max(1, len(pressures))

            if int(fleet["carriages_available"]) > 0 and busiest_pressure >= max(5, average_pressure + 2):
                return Decision(
                    {"type": "attach_carriage", "path_index": busiest_idx},
                    "定点扩容",
                    f"第 {busiest_idx + 1} 条线路压力 {busiest_pressure}，明显高于网络平均 {average_pressure:.1f}。",
                )

            if int(fleet["locomotives_available"]) > 0 and busiest_pressure >= max(4, average_pressure + 1):
                return Decision(
                    {"type": "assign_locomotive", "path_index": busiest_idx},
                    "均衡增派机车",
                    f"把额外运力投向相对最拥堵的第 {busiest_idx + 1} 条线路。",
                )

        return Decision(
            {"type": "noop"},
            "保持网络稳定",
            "当前没有足够高收益的调整，避免为局部变化频繁重构线路。",
        )
