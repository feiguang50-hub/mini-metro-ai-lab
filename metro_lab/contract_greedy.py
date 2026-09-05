from __future__ import annotations

from math import hypot

from .planner import Decision
from .plugin import AlgorithmMetadata
from .problem import LineState, MetroPlanningState, StationState


class ContractGreedyV1:
    """Greedy V1 expressed only against Problem Contract V1.

    This is a migration witness, not a new algorithm. Its behavior is expected
    to remain strictly equivalent to the legacy observation-based GreedyPlanner
    until the old path is retired.
    """

    metadata = AlgorithmMetadata(
        id="greedy-v1-contract",
        name="Greedy Planner V1 (Problem Contract)",
        version="1.0-migration",
        family="heuristic",
        description="Behavioral-equivalence port of Greedy V1 to Problem Contract V1.",
    )

    def __init__(self) -> None:
        self._last_topology_ms = -10_000
        self._topology_cooldown_ms = 700

    def reset(self, state: MetroPlanningState) -> None:
        del state
        self._last_topology_ms = -10_000

    @staticmethod
    def _distance(a: StationState, b: StationState) -> float:
        return hypot(a.x - b.x, a.y - b.y)

    @staticmethod
    def _line_pressure(line: LineState, station_by_id: dict[str, StationState]) -> int:
        return sum(
            station_by_id[sid].passenger_count
            for sid in line.station_ids
            if sid in station_by_id
        )

    def _initial_route(self, stations: tuple[StationState, ...]) -> list[int]:
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
        line: LineState,
        station: StationState,
        station_index: dict[str, int],
        station_by_id: dict[str, StationState],
    ) -> tuple[float, list[int]] | None:
        ids = list(line.station_ids)
        if len(ids) < 2 or any(sid not in station_index for sid in ids):
            return None

        candidates: list[tuple[float, list[str]]] = []
        first = station_by_id[ids[0]]
        last = station_by_id[ids[-1]]
        candidates.append((self._distance(station, first), [station.id, *ids]))
        candidates.append((self._distance(last, station), [*ids, station.id]))

        for pos in range(len(ids) - 1):
            a = station_by_id[ids[pos]]
            b = station_by_id[ids[pos + 1]]
            extra = self._distance(a, station) + self._distance(station, b) - self._distance(a, b)
            candidates.append((extra, [*ids[: pos + 1], station.id, *ids[pos + 1 :]]))

        cost, route_ids = min(candidates, key=lambda item: item[0])
        return cost, [station_index[sid] for sid in route_ids]

    def act(self, state: MetroPlanningState) -> Decision:
        stations = state.stations
        lines = state.lines
        vehicles = state.vehicles
        fleet = state.fleet
        now = state.time_ms

        if len(stations) >= 2 and not lines:
            route = self._initial_route(stations)
            self._last_topology_ms = now
            return Decision(
                {"type": "create_path", "stations": route, "loop": False},
                "建立第一条线路",
                f"连接开局的 {len(route)} 个站点，先形成最短可运行骨架。",
            )

        if lines and fleet.locomotives_available > 0:
            metro_count: dict[str, int] = {line.id: 0 for line in lines}
            for vehicle in vehicles:
                if vehicle.path_id in metro_count:
                    metro_count[vehicle.path_id] += 1
            empty = next(
                (idx for idx, line in enumerate(lines) if metro_count[line.id] == 0),
                None,
            )
            if empty is not None:
                return Decision(
                    {"type": "assign_locomotive", "path_index": empty},
                    "投放机车",
                    f"第 {empty + 1} 条线路还没有列车，优先让它开始服务。",
                )

        station_index = {station.id: station.index for station in stations}
        station_by_id = state.station_by_id
        served = state.served_station_ids
        unserved = [station for station in stations if station.id not in served]

        if unserved and lines and now - self._last_topology_ms >= self._topology_cooldown_ms:
            best: tuple[float, int, list[int], StationState] | None = None
            for station in unserved:
                for line_idx, line in enumerate(lines):
                    insertion = self._best_insertion(line, station, station_index, station_by_id)
                    if insertion is None:
                        continue
                    cost, route = insertion
                    candidate = (cost, line_idx, route, station)
                    if best is None or cost < best[0]:
                        best = candidate
            if best is not None:
                cost, line_idx, route, station = best
                del station
                self._last_topology_ms = now
                return Decision(
                    {
                        "type": "replace_path",
                        "path_index": line_idx,
                        "stations": route,
                        "loop": False,
                    },
                    "接入新站",
                    f"把新站接入第 {line_idx + 1} 条线路，估计额外绕行 {cost:.0f} 像素。",
                )

        if lines:
            pressures = [self._line_pressure(line, station_by_id) for line in lines]
            busiest_idx = max(range(len(lines)), key=pressures.__getitem__)
            busiest_pressure = pressures[busiest_idx]

            if fleet.carriages_available > 0 and busiest_pressure >= 6:
                return Decision(
                    {"type": "attach_carriage", "path_index": busiest_idx},
                    "增加车厢",
                    f"第 {busiest_idx + 1} 条线路累计候车 {busiest_pressure} 人，优先扩容。",
                )

            if fleet.locomotives_available > 0 and busiest_pressure >= 4:
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
