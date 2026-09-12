from __future__ import annotations

from dataclasses import asdict, dataclass
from heapq import heappop, heappush
from math import hypot, isfinite
from typing import Any, Iterable

from .demand import DemandNode, ODDemandMatrix, ODFlow

PASSENGER_ASSIGNMENT_CONTRACT_VERSION = "1.0"


@dataclass(frozen=True)
class AssignmentLine:
    """One candidate transit line used by Passenger Assignment V1."""

    id: str
    station_ids: tuple[str, ...]
    loop: bool = False

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("assignment line id must be non-empty")
        if len(self.station_ids) < 2:
            raise ValueError("assignment line must contain at least two stations")
        if len(set(self.station_ids)) != len(self.station_ids):
            raise ValueError("assignment line station ids must be unique")
        if any(not station_id for station_id in self.station_ids):
            raise ValueError("assignment line station ids must be non-empty")
        if self.loop and len(self.station_ids) < 3:
            raise ValueError("loop line must contain at least three stations")


@dataclass(frozen=True)
class AssignedODFlow:
    origin_id: str
    destination_id: str
    trips: float
    served: bool
    generalized_cost: float | None
    ride_distance: float | None
    transfers: int | None
    station_path: tuple[str, ...]
    line_path: tuple[str, ...]

    @property
    def direct(self) -> bool:
        return self.served and self.transfers == 0


@dataclass(frozen=True)
class LineLoad:
    line_id: str
    trips: float


@dataclass(frozen=True)
class EdgeLoad:
    line_id: str
    from_station_id: str
    to_station_id: str
    trips: float


@dataclass(frozen=True)
class PassengerAssignmentResult:
    assignments: tuple[AssignedODFlow, ...]
    line_loads: tuple[LineLoad, ...]
    edge_loads: tuple[EdgeLoad, ...]
    transfer_penalty: float

    @property
    def total_trips(self) -> float:
        return sum(item.trips for item in self.assignments)

    @property
    def served_trips(self) -> float:
        return sum(item.trips for item in self.assignments if item.served)

    @property
    def unserved_trips(self) -> float:
        return self.total_trips - self.served_trips

    @property
    def direct_trips(self) -> float:
        return sum(item.trips for item in self.assignments if item.direct)

    @property
    def transfer_trips(self) -> float:
        return sum(
            item.trips
            for item in self.assignments
            if item.served and item.transfers is not None and item.transfers > 0
        )

    @property
    def weighted_generalized_cost(self) -> float:
        return sum(
            item.trips * item.generalized_cost
            for item in self.assignments
            if item.served and item.generalized_cost is not None
        )

    @property
    def weighted_ride_distance(self) -> float:
        return sum(
            item.trips * item.ride_distance
            for item in self.assignments
            if item.served and item.ride_distance is not None
        )

    def public(self) -> dict[str, Any]:
        return {
            "contract_version": PASSENGER_ASSIGNMENT_CONTRACT_VERSION,
            "transfer_penalty": self.transfer_penalty,
            "total_trips": self.total_trips,
            "served_trips": self.served_trips,
            "unserved_trips": self.unserved_trips,
            "direct_trips": self.direct_trips,
            "transfer_trips": self.transfer_trips,
            "weighted_generalized_cost": self.weighted_generalized_cost,
            "weighted_ride_distance": self.weighted_ride_distance,
            "assignments": [asdict(item) for item in self.assignments],
            "line_loads": [asdict(item) for item in self.line_loads],
            "edge_loads": [asdict(item) for item in self.edge_loads],
        }


_State = tuple[str, str]  # (station_id, line_id)
_Adjacency = dict[_State, list[tuple[_State, float, bool]]]


def _validate_network(nodes: tuple[DemandNode, ...], lines: tuple[AssignmentLine, ...]) -> None:
    node_ids = {node.id for node in nodes}
    if len(node_ids) != len(nodes):
        raise ValueError("assignment node ids must be unique")
    line_ids = {line.id for line in lines}
    if len(line_ids) != len(lines):
        raise ValueError("assignment line ids must be unique")
    for line in lines:
        unknown = [station_id for station_id in line.station_ids if station_id not in node_ids]
        if unknown:
            raise ValueError(f"line {line.id} references unknown stations: {unknown}")


def _build_graph(
    nodes: tuple[DemandNode, ...],
    lines: tuple[AssignmentLine, ...],
    transfer_penalty: float,
) -> tuple[_Adjacency, dict[str, tuple[str, ...]], dict[str, DemandNode]]:
    node_by_id = {node.id: node for node in nodes}
    lines_by_station: dict[str, list[str]] = {node.id: [] for node in nodes}
    adjacency: _Adjacency = {}

    def ensure(state: _State) -> None:
        adjacency.setdefault(state, [])

    def ride_edge(line_id: str, left_id: str, right_id: str) -> None:
        left = node_by_id[left_id]
        right = node_by_id[right_id]
        distance = hypot(left.x - right.x, left.y - right.y)
        left_state = (left_id, line_id)
        right_state = (right_id, line_id)
        ensure(left_state)
        ensure(right_state)
        adjacency[left_state].append((right_state, distance, False))
        adjacency[right_state].append((left_state, distance, False))

    for line in lines:
        for station_id in line.station_ids:
            lines_by_station[station_id].append(line.id)
            ensure((station_id, line.id))
        for left_id, right_id in zip(line.station_ids, line.station_ids[1:]):
            ride_edge(line.id, left_id, right_id)
        if line.loop:
            ride_edge(line.id, line.station_ids[-1], line.station_ids[0])

    for station_id, line_ids in lines_by_station.items():
        ordered = sorted(line_ids)
        for source_line in ordered:
            source = (station_id, source_line)
            for target_line in ordered:
                if source_line == target_line:
                    continue
                adjacency[source].append(((station_id, target_line), transfer_penalty, True))

    for state in adjacency:
        adjacency[state].sort(key=lambda edge: (edge[0][0], edge[0][1], edge[2], edge[1]))

    return adjacency, {station: tuple(sorted(ids)) for station, ids in lines_by_station.items()}, node_by_id


def _shortest_assignment(
    flow: ODFlow,
    adjacency: _Adjacency,
    lines_by_station: dict[str, tuple[str, ...]],
) -> tuple[list[_State], float, int] | None:
    origin_lines = lines_by_station.get(flow.origin_id, ())
    destination_lines = set(lines_by_station.get(flow.destination_id, ()))
    if not origin_lines or not destination_lines:
        return None

    best: dict[_State, tuple[float, int, int]] = {}
    predecessor: dict[_State, _State | None] = {}
    heap: list[tuple[float, int, int, str, str]] = []

    for line_id in origin_lines:
        state = (flow.origin_id, line_id)
        key = (0.0, 0, 0)
        best[state] = key
        predecessor[state] = None
        heappush(heap, (*key, state[0], state[1]))

    destination_state: _State | None = None
    destination_key: tuple[float, int, int] | None = None

    while heap:
        cost, transfers, hops, station_id, line_id = heappop(heap)
        state = (station_id, line_id)
        key = (cost, transfers, hops)
        if best.get(state) != key:
            continue
        if station_id == flow.destination_id and line_id in destination_lines:
            destination_state = state
            destination_key = key
            break

        for next_state, edge_cost, is_transfer in adjacency.get(state, ()):
            candidate = (
                cost + edge_cost,
                transfers + (1 if is_transfer else 0),
                hops + 1,
            )
            current = best.get(next_state)
            if current is not None and candidate >= current:
                continue
            best[next_state] = candidate
            predecessor[next_state] = state
            heappush(heap, (*candidate, next_state[0], next_state[1]))

    if destination_state is None or destination_key is None:
        return None

    states: list[_State] = []
    cursor: _State | None = destination_state
    while cursor is not None:
        states.append(cursor)
        cursor = predecessor[cursor]
    states.reverse()
    return states, destination_key[0], destination_key[1]


def assign_passengers(
    demand: ODDemandMatrix,
    nodes: Iterable[DemandNode],
    lines: Iterable[AssignmentLine],
    *,
    transfer_penalty: float = 5.0,
) -> PassengerAssignmentResult:
    """Assign every OD pair to one deterministic minimum-generalized-cost path.

    V1 is a static all-or-nothing assignment. Ride cost is Euclidean segment
    distance. Every line change at the same station adds ``transfer_penalty``.
    Capacity, frequency, waiting time, crowding and stochastic route choice are
    deliberately outside this contract.
    """

    if not isfinite(float(transfer_penalty)) or transfer_penalty < 0:
        raise ValueError("transfer_penalty must be finite and non-negative")

    node_tuple = tuple(nodes)
    line_tuple = tuple(lines)
    _validate_network(node_tuple, line_tuple)
    node_by_id = {node.id: node for node in node_tuple}
    missing_demand_nodes = [station_id for station_id in demand.station_ids if station_id not in node_by_id]
    if missing_demand_nodes:
        raise ValueError(f"demand references unknown assignment nodes: {missing_demand_nodes}")

    adjacency, lines_by_station, node_by_id = _build_graph(
        node_tuple,
        line_tuple,
        transfer_penalty,
    )

    assignments: list[AssignedODFlow] = []
    line_loads: dict[str, float] = {}
    edge_loads: dict[tuple[str, str, str], float] = {}

    for flow in demand.flows:
        shortest = _shortest_assignment(flow, adjacency, lines_by_station)
        if shortest is None:
            assignments.append(
                AssignedODFlow(
                    origin_id=flow.origin_id,
                    destination_id=flow.destination_id,
                    trips=flow.trips,
                    served=False,
                    generalized_cost=None,
                    ride_distance=None,
                    transfers=None,
                    station_path=(),
                    line_path=(),
                )
            )
            continue

        states, generalized_cost, transfers = shortest
        ride_distance = 0.0
        station_path: list[str] = [states[0][0]]
        line_path: list[str] = [states[0][1]]

        for current, nxt in zip(states, states[1:]):
            current_station, current_line = current
            next_station, next_line = nxt
            if current_station == next_station:
                if current_line != next_line and line_path[-1] != next_line:
                    line_path.append(next_line)
                continue

            left = node_by_id[current_station]
            right = node_by_id[next_station]
            distance = hypot(left.x - right.x, left.y - right.y)
            ride_distance += distance
            station_path.append(next_station)
            edge_key = (current_line, current_station, next_station)
            edge_loads[edge_key] = edge_loads.get(edge_key, 0.0) + flow.trips

        for line_id in line_path:
            line_loads[line_id] = line_loads.get(line_id, 0.0) + flow.trips

        assignments.append(
            AssignedODFlow(
                origin_id=flow.origin_id,
                destination_id=flow.destination_id,
                trips=flow.trips,
                served=True,
                generalized_cost=generalized_cost,
                ride_distance=ride_distance,
                transfers=transfers,
                station_path=tuple(station_path),
                line_path=tuple(line_path),
            )
        )

    return PassengerAssignmentResult(
        assignments=tuple(assignments),
        line_loads=tuple(
            LineLoad(line_id=line_id, trips=trips)
            for line_id, trips in sorted(line_loads.items())
        ),
        edge_loads=tuple(
            EdgeLoad(
                line_id=line_id,
                from_station_id=from_station_id,
                to_station_id=to_station_id,
                trips=trips,
            )
            for (line_id, from_station_id, to_station_id), trips in sorted(edge_loads.items())
        ),
        transfer_penalty=float(transfer_penalty),
    )
