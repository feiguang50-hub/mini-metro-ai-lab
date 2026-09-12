from __future__ import annotations

from dataclasses import asdict, dataclass
from math import hypot, isfinite
from random import Random
from typing import Any, Iterable

DEMAND_CONTRACT_VERSION = "1.0"
DEFAULT_DEMAND_PERIOD_SECONDS = 3600


@dataclass(frozen=True)
class DemandNode:
    """One origin/destination node used by an explicit demand instance."""

    id: str
    x: float
    y: float
    production_weight: float = 1.0
    attraction_weight: float = 1.0

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("demand node id must be non-empty")
        for name, value in (
            ("x", self.x),
            ("y", self.y),
            ("production_weight", self.production_weight),
            ("attraction_weight", self.attraction_weight),
        ):
            if not isfinite(float(value)):
                raise ValueError(f"{name} must be finite")
        if self.production_weight <= 0 or self.attraction_weight <= 0:
            raise ValueError("demand node weights must be positive")


@dataclass(frozen=True)
class ODFlow:
    """Directional demand from one origin to one destination per demand period."""

    origin_id: str
    destination_id: str
    trips: float

    def __post_init__(self) -> None:
        if not self.origin_id or not self.destination_id:
            raise ValueError("OD flow endpoints must be non-empty")
        if self.origin_id == self.destination_id:
            raise ValueError("OD flow cannot be a self-loop")
        if not isfinite(float(self.trips)) or self.trips <= 0:
            raise ValueError("OD flow trips must be positive and finite")


@dataclass(frozen=True)
class ODDemandMatrix:
    """Sparse, directional origin-destination demand matrix.

    Missing OD pairs have zero demand. ``trips`` are interpreted over
    ``period_seconds`` so the same contract can represent hourly demand or a
    shorter/longer fixed planning interval without changing units implicitly.
    """

    station_ids: tuple[str, ...]
    flows: tuple[ODFlow, ...]
    period_seconds: int = DEFAULT_DEMAND_PERIOD_SECONDS
    source: str = "explicit"
    seed: int | None = None

    def __post_init__(self) -> None:
        if self.period_seconds <= 0:
            raise ValueError("demand period must be positive")
        if len(set(self.station_ids)) != len(self.station_ids):
            raise ValueError("station ids must be unique")
        if any(not station_id for station_id in self.station_ids):
            raise ValueError("station ids must be non-empty")

        station_set = set(self.station_ids)
        seen: set[tuple[str, str]] = set()
        for flow in self.flows:
            key = (flow.origin_id, flow.destination_id)
            if key in seen:
                raise ValueError(f"duplicate OD pair: {flow.origin_id}->{flow.destination_id}")
            seen.add(key)
            if flow.origin_id not in station_set or flow.destination_id not in station_set:
                raise ValueError(
                    f"OD pair references unknown station: {flow.origin_id}->{flow.destination_id}"
                )

    @property
    def total_trips(self) -> float:
        return sum(flow.trips for flow in self.flows)

    def flow(self, origin_id: str, destination_id: str) -> float:
        for item in self.flows:
            if item.origin_id == origin_id and item.destination_id == destination_id:
                return item.trips
        return 0.0

    def outbound(self, origin_id: str) -> float:
        return sum(item.trips for item in self.flows if item.origin_id == origin_id)

    def inbound(self, destination_id: str) -> float:
        return sum(item.trips for item in self.flows if item.destination_id == destination_id)

    def public(self) -> dict[str, Any]:
        return {
            "contract_version": DEMAND_CONTRACT_VERSION,
            "period_seconds": self.period_seconds,
            "source": self.source,
            "seed": self.seed,
            "station_ids": list(self.station_ids),
            "flows": [asdict(flow) for flow in self.flows],
            "total_trips": self.total_trips,
        }


def explicit_od_matrix(
    station_ids: Iterable[str],
    flows: Iterable[ODFlow],
    *,
    period_seconds: int = DEFAULT_DEMAND_PERIOD_SECONDS,
    source: str = "explicit",
) -> ODDemandMatrix:
    """Build a validated explicit OD matrix without simulator-specific state."""

    return ODDemandMatrix(
        station_ids=tuple(station_ids),
        flows=tuple(flows),
        period_seconds=period_seconds,
        source=source,
    )


def synthetic_gravity_od(
    nodes: Iterable[DemandNode],
    *,
    seed: int,
    total_trips: float = 1000.0,
    density: float = 0.5,
    distance_decay: float = 1.5,
    period_seconds: int = DEFAULT_DEMAND_PERIOD_SECONDS,
) -> ODDemandMatrix:
    """Generate a deterministic synthetic OD instance for controlled research.

    This is intentionally a benchmark generator, not a calibrated travel-demand
    model. It uses a gravity-style score from node production/attraction weights
    and Euclidean distance, then a seeded directional multiplier and sparsity
    mask. Real OD data can replace this generator while preserving the same
    ``ODDemandMatrix`` contract.
    """

    node_list = tuple(nodes)
    if len(node_list) < 2:
        raise ValueError("synthetic OD generation requires at least two nodes")
    if len({node.id for node in node_list}) != len(node_list):
        raise ValueError("demand node ids must be unique")
    if not isfinite(float(total_trips)) or total_trips <= 0:
        raise ValueError("total_trips must be positive and finite")
    if not (0 < density <= 1):
        raise ValueError("density must be in (0, 1]")
    if not isfinite(float(distance_decay)) or distance_decay < 0:
        raise ValueError("distance_decay must be finite and non-negative")

    rng = Random(seed)
    scored: list[tuple[str, str, float]] = []
    for origin in node_list:
        for destination in node_list:
            if origin.id == destination.id:
                continue
            if rng.random() > density:
                continue
            distance = hypot(origin.x - destination.x, origin.y - destination.y)
            directional_multiplier = 0.75 + 0.5 * rng.random()
            impedance = (1.0 + distance) ** distance_decay
            score = (
                origin.production_weight
                * destination.attraction_weight
                * directional_multiplier
                / impedance
            )
            scored.append((origin.id, destination.id, score))

    if not scored:
        # Keep the generator total and deterministic even for a very sparse mask.
        origin, destination = node_list[0], node_list[1]
        scored.append((origin.id, destination.id, 1.0))

    score_sum = sum(score for _, _, score in scored)
    flows = tuple(
        ODFlow(origin_id=origin_id, destination_id=destination_id, trips=total_trips * score / score_sum)
        for origin_id, destination_id, score in scored
    )
    return ODDemandMatrix(
        station_ids=tuple(node.id for node in node_list),
        flows=flows,
        period_seconds=period_seconds,
        source="synthetic-gravity-v1",
        seed=seed,
    )
