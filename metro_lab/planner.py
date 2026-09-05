from __future__ import annotations

from dataclasses import dataclass
from math import hypot
from typing import Any

Action = dict[str, Any]


@dataclass(frozen=True)
class Decision:
    action: Action
    title: str
    detail: str


class GreedyPlanner:
    """Transparent V1 baseline focused on stable, understandable decisions."""

    name = "Greedy Planner V1"

    def __init__(self) -> None:
        self._last_topology_ms = -10_000
        self._topology_cooldown_ms = 700

    def reset(self, observation: dict[str, Any]) -> None:
        del observation
        self._last_topology_ms = -10_000

    @staticmethod
    def _s(observation: dict[str, Any]) -> dict[str, Any]:
        return observation["structured"]

    @staticmethod
    def _distance(a: dict[str, Any], b: dict[str, Any]) -> float:
        ax, ay = a["position"]
        bx, by = b["position"]
        return hypot(float(ax) - float(bx), float(ay) - float(by))

    @staticmethod
    def _path_pressure(path: dict[str, Any], station_by_id: dict[str, dict[str, Any]]) -> int:
        return sum(int(station_by_id[sid]["passenger_count"]) for sid in path["station_ids"] if sid in station_by_id)

    def _initial_route(self, stations: list[dict[str, Any]]) -> list[int]:
        count = min(3, len(stations))
        if count <= 1:
            return list(range(count))
        remaining = set(range(1, count))
        route = [0]
        while remaining:
            current = stations[route[-1]]
            nxt = min(remaining, key=lambda idx: self._distance(current, stations[idx]))
            route.append(nxt)
            remaining.remove(nxt)
        return route

    def _best_insertion(
        self,
        path: dict[str, Any],
        station: dict[str, Any],
        station_index: dict[str, int],
        station_by_id: dict[str, dict[str, Any]],
    ) -> tuple[float, list[int]] | None:
        ids = list(path["station_ids"])
        if len(ids) < 2 or any(sid not in station_index for sid in ids):
            return None

        candidates: list[tuple[float, list[str]]] = []
        first = station_by_id[ids[0]]
        last = station_by_id[ids[-1]]
        candidates.append((self._distance(station, first), [station["id"], *ids]))
        candidates.append((self._distance(last, station), [*ids, station["id"]]))

        for pos in range(len(ids) - 1):
            a = station_by_id[ids[pos]]
            b = station_by_id[ids[pos + 1]]
            extra = self._distance(a, station) + self._distance(station, b) - self._distance(a, b)
            candidates.append((extra, [*ids[: pos + 1], station["id"], *ids[pos + 1 :]]))

        cost, route_ids = min(candidates, key=lambda item: item[0])
        return cost, [station_index[sid] for sid in route_ids]

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
                "建立第一条线路",
                f"连接开局的 {len(route)} 个站点，先形成最短可运行骨架。",
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
                    "投放机车",
                    f"第 {empty + 1} 条线路还没有列车，优先让它开始服务。",
                )

        station_index = {station["id"]: idx for idx, station in enumerate(stations)}
        station_by_id = {station["id"]: station for station in stations}
        served = {sid for path in paths for sid in path["station_ids"]}
        unserved = [station for station in stations if station["id"] not in served]

        if unserved and paths and now - self._last_topology_ms >= self._topology_cooldown_ms:
            best: tuple[float, int, list[int], dict[str, Any]] | None = None
            for station in unserved:
                for path_idx, path in enumerate(paths):
                    insertion = self._best_insertion(path, station, station_index, station_by_id)
                    if insertion is None:
                        continue
                    cost, route = insertion
                    candidate = (cost, path_idx, route, station)
                    if best is None or cost < best[0]:
                        best = candidate
            if best is not None:
                cost, path_idx, route, station = best
                self._last_topology_ms = now
                return Decision(
                    {"type": "replace_path", "path_index": path_idx, "stations": route, "loop": False},
                    "接入新站",
                    f"把新站接入第 {path_idx + 1} 条线路，估计额外绕行 {cost:.0f} 像素。",
                )

        if paths:
            pressures = [self._path_pressure(path, station_by_id) for path in paths]
            busiest_idx = max(range(len(paths)), key=pressures.__getitem__)
            busiest_pressure = pressures[busiest_idx]

            if int(fleet["carriages_available"]) > 0 and busiest_pressure >= 6:
                return Decision(
                    {"type": "attach_carriage", "path_index": busiest_idx},
                    "增加车厢",
                    f"第 {busiest_idx + 1} 条线路累计候车 {busiest_pressure} 人，优先扩容。",
                )

            if int(fleet["locomotives_available"]) > 0 and busiest_pressure >= 4:
                return Decision(
                    {"type": "assign_locomotive", "path_index": busiest_idx},
                    "增派机车",
                    f"第 {busiest_idx + 1} 条线路压力最高，追加一列车分担客流。",
                )

        return Decision(
            {"type": "noop"},
            "继续观察",
            "当前没有值得打断网络运行的高收益调整。",
        )
