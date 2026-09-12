from __future__ import annotations

from dataclasses import asdict, dataclass
from math import isfinite
from typing import Iterable

from .assignment import AssignmentLine
from .demand import DemandNode

INFRASTRUCTURE_CONTRACT_VERSION = "1.0"
_EPSILON = 1e-9


@dataclass(frozen=True)
class BarrierSegment:
    """Finite straight infrastructure barrier used by the V1 benchmark.

    A barrier may impose a fixed crossing cost or make direct crossing
    infeasible. This deliberately models only geometry that can change the
    network optimum; it is not a construction-process simulator.
    """

    id: str
    x1: float
    y1: float
    x2: float
    y2: float
    crossing_cost: float = 0.0
    forbidden: bool = False

    def __post_init__(self) -> None:
        if not self.id or self.id.strip() != self.id:
            raise ValueError("barrier id must be a non-empty trimmed string")
        values = (self.x1, self.y1, self.x2, self.y2, self.crossing_cost)
        if any(not isfinite(float(value)) for value in values):
            raise ValueError("barrier coordinates and crossing cost must be finite")
        if abs(self.x1 - self.x2) <= _EPSILON and abs(self.y1 - self.y2) <= _EPSILON:
            raise ValueError("barrier segment must have non-zero length")
        if self.crossing_cost < 0:
            raise ValueError("barrier crossing_cost must be non-negative")

    def public(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class InfrastructureModel:
    unit_length_cost: float = 1.0
    barriers: tuple[BarrierSegment, ...] = ()

    def __post_init__(self) -> None:
        if not isfinite(float(self.unit_length_cost)) or self.unit_length_cost < 0:
            raise ValueError("unit_length_cost must be finite and non-negative")
        ids = [barrier.id for barrier in self.barriers]
        if len(ids) != len(set(ids)):
            raise ValueError("barrier ids must be unique")

    def public(self) -> dict[str, object]:
        return {
            "contract_version": INFRASTRUCTURE_CONTRACT_VERSION,
            "unit_length_cost": self.unit_length_cost,
            "barriers": [barrier.public() for barrier in self.barriers],
        }


@dataclass(frozen=True)
class InfrastructureEvaluation:
    total_length: float
    length_cost: float
    barrier_crossings: int
    crossing_cost: float
    construction_cost: float
    forbidden_crossings: int
    feasible: bool


def _orientation(ax: float, ay: float, bx: float, by: float, cx: float, cy: float) -> float:
    return (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)


def _on_segment(ax: float, ay: float, bx: float, by: float, px: float, py: float) -> bool:
    return (
        min(ax, bx) - _EPSILON <= px <= max(ax, bx) + _EPSILON
        and min(ay, by) - _EPSILON <= py <= max(ay, by) + _EPSILON
        and abs(_orientation(ax, ay, bx, by, px, py)) <= _EPSILON
    )


def segments_intersect(
    ax: float,
    ay: float,
    bx: float,
    by: float,
    cx: float,
    cy: float,
    dx: float,
    dy: float,
) -> bool:
    o1 = _orientation(ax, ay, bx, by, cx, cy)
    o2 = _orientation(ax, ay, bx, by, dx, dy)
    o3 = _orientation(cx, cy, dx, dy, ax, ay)
    o4 = _orientation(cx, cy, dx, dy, bx, by)

    if ((o1 > _EPSILON and o2 < -_EPSILON) or (o1 < -_EPSILON and o2 > _EPSILON)) and (
        (o3 > _EPSILON and o4 < -_EPSILON) or (o3 < -_EPSILON and o4 > _EPSILON)
    ):
        return True
    return (
        (abs(o1) <= _EPSILON and _on_segment(ax, ay, bx, by, cx, cy))
        or (abs(o2) <= _EPSILON and _on_segment(ax, ay, bx, by, dx, dy))
        or (abs(o3) <= _EPSILON and _on_segment(cx, cy, dx, dy, ax, ay))
        or (abs(o4) <= _EPSILON and _on_segment(cx, cy, dx, dy, bx, by))
    )


def segment_barriers(
    left: DemandNode,
    right: DemandNode,
    model: InfrastructureModel,
) -> tuple[BarrierSegment, ...]:
    return tuple(
        barrier
        for barrier in model.barriers
        if segments_intersect(
            left.x,
            left.y,
            right.x,
            right.y,
            barrier.x1,
            barrier.y1,
            barrier.x2,
            barrier.y2,
        )
    )


def segment_infrastructure_cost(
    left: DemandNode,
    right: DemandNode,
    model: InfrastructureModel,
) -> tuple[float, int, int]:
    from math import hypot

    length = hypot(left.x - right.x, left.y - right.y)
    barriers = segment_barriers(left, right, model)
    cost = length * model.unit_length_cost + sum(item.crossing_cost for item in barriers)
    forbidden = sum(1 for item in barriers if item.forbidden)
    return cost, len(barriers), forbidden


def evaluate_infrastructure(
    nodes: Iterable[DemandNode],
    lines: Iterable[AssignmentLine],
    model: InfrastructureModel,
) -> InfrastructureEvaluation:
    from math import hypot

    by_id = {node.id: node for node in nodes}
    total_length = 0.0
    crossing_cost = 0.0
    crossings = 0
    forbidden = 0

    for line in lines:
        pairs = list(zip(line.station_ids, line.station_ids[1:]))
        if line.loop:
            pairs.append((line.station_ids[-1], line.station_ids[0]))
        for left_id, right_id in pairs:
            try:
                left = by_id[left_id]
                right = by_id[right_id]
            except KeyError as exc:
                raise ValueError(f"unknown station in infrastructure evaluation: {exc.args[0]}") from exc
            total_length += hypot(left.x - right.x, left.y - right.y)
            hit = segment_barriers(left, right, model)
            crossings += len(hit)
            crossing_cost += sum(item.crossing_cost for item in hit)
            forbidden += sum(1 for item in hit if item.forbidden)

    length_cost = total_length * model.unit_length_cost
    return InfrastructureEvaluation(
        total_length=total_length,
        length_cost=length_cost,
        barrier_crossings=crossings,
        crossing_cost=crossing_cost,
        construction_cost=length_cost + crossing_cost,
        forbidden_crossings=forbidden,
        feasible=(forbidden == 0),
    )
