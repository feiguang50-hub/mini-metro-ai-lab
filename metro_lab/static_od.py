from __future__ import annotations

import argparse
import csv
import json
import re
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime, timezone
from math import hypot, isfinite
from pathlib import Path
from random import Random
from statistics import mean
from time import perf_counter_ns
from typing import Any, Callable, Iterable, Protocol, runtime_checkable

from .assignment import (
    PASSENGER_ASSIGNMENT_CONTRACT_VERSION,
    AssignmentLine,
    PassengerAssignmentResult,
    assign_passengers,
)
from .config import ROOT
from .demand import (
    DEMAND_CONTRACT_VERSION,
    DemandNode,
    ODDemandMatrix,
    synthetic_gravity_od,
)

STATIC_OD_BENCHMARK_ID = "explicit-od-static-v1"
STATIC_OD_BENCHMARK_VERSION = "1.0"
STATIC_DESIGN_CONTRACT_VERSION = "1.0"
DEFAULT_STATIC_OD_OUTPUT_ROOT = ROOT / "output" / "static-od"


@dataclass(frozen=True)
class StaticDesignBudget:
    max_lines: int = 2
    max_stations_per_line: int = 6
    min_stations_per_line: int = 2

    def __post_init__(self) -> None:
        if self.max_lines <= 0:
            raise ValueError("max_lines must be positive")
        if self.min_stations_per_line < 2:
            raise ValueError("min_stations_per_line must be at least 2")
        if self.max_stations_per_line < self.min_stations_per_line:
            raise ValueError("max_stations_per_line must be >= min_stations_per_line")

    def public(self) -> dict[str, int]:
        return asdict(self)


@dataclass(frozen=True)
class ExplicitODStaticInstance:
    id: str
    seed: int
    nodes: tuple[DemandNode, ...]
    demand: ODDemandMatrix
    budget: StaticDesignBudget
    transfer_penalty: float

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("static instance id must be non-empty")
        node_ids = tuple(node.id for node in self.nodes)
        if len(node_ids) < 2:
            raise ValueError("static instance requires at least two nodes")
        if len(set(node_ids)) != len(node_ids):
            raise ValueError("static instance node ids must be unique")
        if tuple(self.demand.station_ids) != node_ids:
            raise ValueError("demand station order must match static instance node order")
        if not isfinite(float(self.transfer_penalty)) or self.transfer_penalty < 0:
            raise ValueError("transfer_penalty must be finite and non-negative")

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "benchmark_id": STATIC_OD_BENCHMARK_ID,
            "benchmark_version": STATIC_OD_BENCHMARK_VERSION,
            "static_design_contract": STATIC_DESIGN_CONTRACT_VERSION,
            "demand_contract": DEMAND_CONTRACT_VERSION,
            "assignment_contract": PASSENGER_ASSIGNMENT_CONTRACT_VERSION,
            "seed": self.seed,
            "nodes": [asdict(node) for node in self.nodes],
            "demand": self.demand.public(),
            "budget": self.budget.public(),
            "transfer_penalty": self.transfer_penalty,
        }


@dataclass(frozen=True)
class StaticAlgorithmMetadata:
    id: str
    name: str
    version: str
    description: str
    problem_id: str = STATIC_OD_BENCHMARK_ID
    design_contract: str = STATIC_DESIGN_CONTRACT_VERSION

    def public(self) -> dict[str, str]:
        return asdict(self)


@runtime_checkable
class StaticDesignAlgorithm(Protocol):
    metadata: StaticAlgorithmMetadata

    def design(self, instance: ExplicitODStaticInstance) -> tuple[AssignmentLine, ...]: ...


class StaticAlgorithmRegistrationError(ValueError):
    pass


StaticAlgorithmFactory = Callable[[], StaticDesignAlgorithm]


class StaticAlgorithmRegistry:
    def __init__(self) -> None:
        self._factories: dict[str, StaticAlgorithmFactory] = {}
        self._metadata: dict[str, StaticAlgorithmMetadata] = {}

    def register(self, factory: StaticAlgorithmFactory) -> StaticAlgorithmMetadata:
        algorithm = factory()
        if not isinstance(algorithm, StaticDesignAlgorithm):
            raise StaticAlgorithmRegistrationError("factory must return a StaticDesignAlgorithm")
        metadata = algorithm.metadata
        if not metadata.id or metadata.id.strip() != metadata.id:
            raise StaticAlgorithmRegistrationError("algorithm id must be a non-empty trimmed string")
        if metadata.problem_id != STATIC_OD_BENCHMARK_ID:
            raise StaticAlgorithmRegistrationError("algorithm problem_id does not match Static OD V1")
        if metadata.design_contract != STATIC_DESIGN_CONTRACT_VERSION:
            raise StaticAlgorithmRegistrationError("algorithm design contract is incompatible")
        if metadata.id in self._factories:
            raise StaticAlgorithmRegistrationError(f"duplicate static algorithm id: {metadata.id}")
        self._factories[metadata.id] = factory
        self._metadata[metadata.id] = metadata
        return metadata

    def create(self, algorithm_id: str) -> StaticDesignAlgorithm:
        try:
            return self._factories[algorithm_id]()
        except KeyError as exc:
            raise KeyError(f"unknown static OD algorithm: {algorithm_id}") from exc

    def metadata(self) -> tuple[StaticAlgorithmMetadata, ...]:
        return tuple(self._metadata[key] for key in sorted(self._metadata))

    def ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._factories))


def synthetic_static_od_instance(
    seed: int,
    *,
    station_count: int = 10,
    total_trips: float = 1000.0,
    density: float = 0.65,
    distance_decay: float = 1.25,
    budget: StaticDesignBudget | None = None,
    transfer_penalty: float = 20.0,
) -> ExplicitODStaticInstance:
    """Create one deterministic synthetic geometry + explicit OD instance."""

    if station_count < 2:
        raise ValueError("station_count must be at least 2")
    design_budget = budget or StaticDesignBudget()
    if design_budget.max_lines * (design_budget.max_stations_per_line - 1) + 1 < station_count:
        raise ValueError(
            "design budget cannot connect every station even with one shared transfer station per line"
        )

    rng = Random(seed)
    nodes = tuple(
        DemandNode(
            id=f"S{index:02d}",
            x=round(rng.uniform(0.0, 100.0), 6),
            y=round(rng.uniform(0.0, 100.0), 6),
            production_weight=round(rng.uniform(0.65, 1.55), 6),
            attraction_weight=round(rng.uniform(0.65, 1.55), 6),
        )
        for index in range(station_count)
    )
    demand = synthetic_gravity_od(
        nodes,
        seed=seed ^ 0x5F3759DF,
        total_trips=total_trips,
        density=density,
        distance_decay=distance_decay,
    )
    return ExplicitODStaticInstance(
        id=f"synthetic-od-seed-{seed}",
        seed=seed,
        nodes=nodes,
        demand=demand,
        budget=design_budget,
        transfer_penalty=float(transfer_penalty),
    )


def validate_line_plan(
    instance: ExplicitODStaticInstance,
    lines: Iterable[AssignmentLine],
) -> tuple[AssignmentLine, ...]:
    plan = tuple(lines)
    if not plan:
        raise ValueError("static line plan must contain at least one line")
    if len(plan) > instance.budget.max_lines:
        raise ValueError("static line plan exceeds max_lines")
    if len({line.id for line in plan}) != len(plan):
        raise ValueError("static line ids must be unique")
    known = {node.id for node in instance.nodes}
    for line in plan:
        if len(line.station_ids) < instance.budget.min_stations_per_line:
            raise ValueError(f"line {line.id} is shorter than the design minimum")
        if len(line.station_ids) > instance.budget.max_stations_per_line:
            raise ValueError(f"line {line.id} exceeds max_stations_per_line")
        unknown = set(line.station_ids) - known
        if unknown:
            raise ValueError(f"line {line.id} references unknown stations: {sorted(unknown)}")
    return plan


def _nearest_order(nodes: tuple[DemandNode, ...]) -> tuple[str, ...]:
    by_id = {node.id: node for node in nodes}
    centroid_x = mean(node.x for node in nodes)
    centroid_y = mean(node.y for node in nodes)
    start = min(
        nodes,
        key=lambda node: (hypot(node.x - centroid_x, node.y - centroid_y), node.id),
    )
    order = [start.id]
    remaining = set(by_id) - {start.id}
    while remaining:
        current = by_id[order[-1]]
        nxt = min(
            remaining,
            key=lambda station_id: (
                hypot(current.x - by_id[station_id].x, current.y - by_id[station_id].y),
                station_id,
            ),
        )
        order.append(nxt)
        remaining.remove(nxt)
    return tuple(order)


def _demand_order(instance: ExplicitODStaticInstance) -> tuple[str, ...]:
    nodes = {node.id: node for node in instance.nodes}
    demand = instance.demand
    importance = {
        station_id: demand.outbound(station_id) + demand.inbound(station_id)
        for station_id in demand.station_ids
    }
    start = min(demand.station_ids, key=lambda station_id: (-importance[station_id], station_id))
    order = [start]
    remaining = set(demand.station_ids) - {start}
    while remaining:
        current_id = order[-1]
        current = nodes[current_id]

        def score(candidate_id: str) -> tuple[float, float, str]:
            candidate = nodes[candidate_id]
            pair_demand = demand.flow(current_id, candidate_id) + demand.flow(candidate_id, current_id)
            distance = hypot(current.x - candidate.x, current.y - candidate.y)
            affinity = pair_demand / (1.0 + distance)
            return (-affinity, distance, candidate_id)

        nxt = min(remaining, key=score)
        order.append(nxt)
        remaining.remove(nxt)
    return tuple(order)


def _split_order_into_lines(
    order: tuple[str, ...],
    budget: StaticDesignBudget,
    *,
    prefix: str,
) -> tuple[AssignmentLine, ...]:
    if len(order) < 2:
        raise ValueError("at least two stations are required")
    lines: list[AssignmentLine] = []
    cursor = 0
    line_index = 1
    while cursor < len(order) - 1:
        if line_index > budget.max_lines:
            raise ValueError("design budget cannot represent the proposed station order")
        end = min(len(order), cursor + budget.max_stations_per_line)
        station_ids = order[cursor:end]
        if len(station_ids) < budget.min_stations_per_line:
            if not lines:
                raise ValueError("cannot construct a legal line plan")
            previous = lines.pop()
            merged = previous.station_ids + station_ids[1:]
            if len(merged) > budget.max_stations_per_line:
                raise ValueError("design budget cannot cover station order")
            lines.append(AssignmentLine(previous.id, merged))
            break
        lines.append(AssignmentLine(f"{prefix}-{line_index}", station_ids))
        if end == len(order):
            break
        cursor = end - 1  # share one transfer station between consecutive lines
        line_index += 1
    return tuple(lines)


class GeometryNearestV1:
    metadata = StaticAlgorithmMetadata(
        id="geometry-nearest-v1",
        name="Geometry Nearest V1",
        version="1.0",
        description="Nearest-neighbor station ordering using geometry only; ignores OD demand.",
    )

    def design(self, instance: ExplicitODStaticInstance) -> tuple[AssignmentLine, ...]:
        return _split_order_into_lines(
            _nearest_order(instance.nodes),
            instance.budget,
            prefix="geometry",
        )


class ODDemandChainV1:
    metadata = StaticAlgorithmMetadata(
        id="od-demand-chain-v1",
        name="OD Demand Chain V1",
        version="1.0",
        description="Demand-aware greedy ordering using directional OD affinity and distance.",
    )

    def design(self, instance: ExplicitODStaticInstance) -> tuple[AssignmentLine, ...]:
        return _split_order_into_lines(
            _demand_order(instance),
            instance.budget,
            prefix="demand",
        )


STATIC_ALGORITHMS = StaticAlgorithmRegistry()
STATIC_ALGORITHMS.register(GeometryNearestV1)
STATIC_ALGORITHMS.register(ODDemandChainV1)


@dataclass(frozen=True)
class StaticODEpisodeResult:
    algorithm: str
    seed: int
    line_count: int
    total_line_length: float
    total_trips: float
    served_trips: float
    unserved_trips: float
    coverage_rate: float
    direct_trips: float
    transfer_trips: float
    direct_trip_rate: float
    transfer_trip_rate: float
    mean_generalized_cost_served: float
    mean_ride_distance_served: float
    max_line_load_share: float
    design_compute_ms: float
    lines: tuple[AssignmentLine, ...]


@dataclass(frozen=True)
class StaticODSummary:
    algorithm: str
    episodes: int
    mean_coverage_rate: float
    mean_direct_trip_rate: float
    mean_transfer_trip_rate: float
    mean_generalized_cost_served: float
    mean_ride_distance_served: float
    mean_total_line_length: float
    mean_max_line_load_share: float
    mean_design_compute_ms: float


def _line_length(nodes: dict[str, DemandNode], line: AssignmentLine) -> float:
    pairs = list(zip(line.station_ids, line.station_ids[1:]))
    if line.loop:
        pairs.append((line.station_ids[-1], line.station_ids[0]))
    return sum(
        hypot(nodes[left].x - nodes[right].x, nodes[left].y - nodes[right].y)
        for left, right in pairs
    )


def evaluate_static_plan(
    instance: ExplicitODStaticInstance,
    algorithm_id: str,
    lines: Iterable[AssignmentLine],
    *,
    design_compute_ms: float = 0.0,
) -> StaticODEpisodeResult:
    plan = validate_line_plan(instance, lines)
    assignment = assign_passengers(
        instance.demand,
        instance.nodes,
        plan,
        transfer_penalty=instance.transfer_penalty,
    )
    nodes = {node.id: node for node in instance.nodes}
    total_line_length = sum(_line_length(nodes, line) for line in plan)
    total = assignment.total_trips
    served = assignment.served_trips
    direct = assignment.direct_trips
    transfer = assignment.transfer_trips
    max_line_load = max((item.trips for item in assignment.line_loads), default=0.0)
    return StaticODEpisodeResult(
        algorithm=algorithm_id,
        seed=instance.seed,
        line_count=len(plan),
        total_line_length=total_line_length,
        total_trips=total,
        served_trips=served,
        unserved_trips=assignment.unserved_trips,
        coverage_rate=(served / total if total else 0.0),
        direct_trips=direct,
        transfer_trips=transfer,
        direct_trip_rate=(direct / total if total else 0.0),
        transfer_trip_rate=(transfer / total if total else 0.0),
        mean_generalized_cost_served=(
            assignment.weighted_generalized_cost / served if served else 0.0
        ),
        mean_ride_distance_served=(
            assignment.weighted_ride_distance / served if served else 0.0
        ),
        max_line_load_share=(max_line_load / total if total else 0.0),
        design_compute_ms=float(design_compute_ms),
        lines=plan,
    )


def run_static_algorithm(
    instance: ExplicitODStaticInstance,
    algorithm_id: str,
) -> StaticODEpisodeResult:
    algorithm = STATIC_ALGORITHMS.create(algorithm_id)
    start = perf_counter_ns()
    plan = algorithm.design(instance)
    elapsed_ms = (perf_counter_ns() - start) / 1_000_000.0
    return evaluate_static_plan(
        instance,
        algorithm_id,
        plan,
        design_compute_ms=elapsed_ms,
    )


def summarize_static_results(results: Iterable[StaticODEpisodeResult]) -> tuple[StaticODSummary, ...]:
    groups: dict[str, list[StaticODEpisodeResult]] = {}
    for result in results:
        groups.setdefault(result.algorithm, []).append(result)
    summaries = []
    for algorithm_id in sorted(groups):
        rows = groups[algorithm_id]
        summaries.append(
            StaticODSummary(
                algorithm=algorithm_id,
                episodes=len(rows),
                mean_coverage_rate=mean(row.coverage_rate for row in rows),
                mean_direct_trip_rate=mean(row.direct_trip_rate for row in rows),
                mean_transfer_trip_rate=mean(row.transfer_trip_rate for row in rows),
                mean_generalized_cost_served=mean(row.mean_generalized_cost_served for row in rows),
                mean_ride_distance_served=mean(row.mean_ride_distance_served for row in rows),
                mean_total_line_length=mean(row.total_line_length for row in rows),
                mean_max_line_load_share=mean(row.max_line_load_share for row in rows),
                mean_design_compute_ms=mean(row.design_compute_ms for row in rows),
            )
        )
    return tuple(summaries)


def _jsonable(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return _jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    return value


def _safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip()).strip("-.")
    return slug or "run"


@dataclass(frozen=True)
class StaticODArtifacts:
    run_id: str
    run_dir: Path
    config: dict[str, Any]

    @classmethod
    def create(
        cls,
        output_root: Path,
        *,
        algorithms: Iterable[str],
        seeds: Iterable[int],
        instance_parameters: dict[str, Any],
    ) -> "StaticODArtifacts":
        algorithm_ids = [str(item) for item in algorithms]
        seed_values = [int(item) for item in seeds]
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        label = "-vs-".join(_safe_slug(item) for item in algorithm_ids) or "static-od"
        run_id = f"{timestamp}-{STATIC_OD_BENCHMARK_ID}-{label}"
        output_root = Path(output_root)
        output_root.mkdir(parents=True, exist_ok=True)
        run_dir = output_root / run_id
        suffix = 2
        while run_dir.exists():
            run_dir = output_root / f"{run_id}-{suffix:02d}"
            suffix += 1
        run_dir.mkdir(parents=True)
        run_id = run_dir.name
        config = {
            "schema_version": 1,
            "benchmark_id": STATIC_OD_BENCHMARK_ID,
            "benchmark_version": STATIC_OD_BENCHMARK_VERSION,
            "static_design_contract": STATIC_DESIGN_CONTRACT_VERSION,
            "demand_contract": DEMAND_CONTRACT_VERSION,
            "assignment_contract": PASSENGER_ASSIGNMENT_CONTRACT_VERSION,
            "problem_family_id": STATIC_OD_BENCHMARK_ID,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "algorithms": algorithm_ids,
            "algorithm_specs": [STATIC_ALGORITHMS.create(item).metadata.public() for item in algorithm_ids],
            "seeds": seed_values,
            "instance_parameters": _jsonable(instance_parameters),
        }
        (run_dir / "config.json").write_text(
            json.dumps(config, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return cls(run_id=run_id, run_dir=run_dir, config=config)

    def finalize(
        self,
        results: Iterable[StaticODEpisodeResult],
        summaries: Iterable[StaticODSummary],
        instances: Iterable[ExplicitODStaticInstance],
    ) -> None:
        result_rows = [_jsonable(item) for item in results]
        summary_rows = [_jsonable(item) for item in summaries]
        instance_rows = [_jsonable(item.public()) for item in instances]
        payload = {
            "schema_version": 1,
            "run_id": self.run_id,
            "config": self.config,
            "instances": instance_rows,
            "results": result_rows,
            "summaries": summary_rows,
        }
        (self.run_dir / "results.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        self._write_csv(result_rows)
        self._write_summary(summary_rows)

    def _write_csv(self, rows: list[dict[str, Any]]) -> None:
        path = self.run_dir / "episodes.csv"
        scalar_fields = [
            "algorithm",
            "seed",
            "line_count",
            "total_line_length",
            "total_trips",
            "served_trips",
            "unserved_trips",
            "coverage_rate",
            "direct_trips",
            "transfer_trips",
            "direct_trip_rate",
            "transfer_trip_rate",
            "mean_generalized_cost_served",
            "mean_ride_distance_served",
            "max_line_load_share",
            "design_compute_ms",
        ]
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=scalar_fields)
            writer.writeheader()
            for row in rows:
                writer.writerow({field: row.get(field) for field in scalar_fields})

    def _write_summary(self, rows: list[dict[str, Any]]) -> None:
        lines = [
            f"# Explicit OD Static V1 · {self.run_id}",
            "",
            f"- Benchmark: `{STATIC_OD_BENCHMARK_ID}` v{STATIC_OD_BENCHMARK_VERSION}",
            f"- Static design contract: `v{STATIC_DESIGN_CONTRACT_VERSION}`",
            f"- Demand contract: `v{DEMAND_CONTRACT_VERSION}`",
            f"- Passenger assignment contract: `v{PASSENGER_ASSIGNMENT_CONTRACT_VERSION}`",
            f"- Seeds: {', '.join(str(seed) for seed in self.config['seeds'])}",
            "",
            "## Separate evaluation metrics",
            "",
            "| Algorithm | Coverage | Direct | Transfer | Mean gen. cost | Mean ride dist | Line length | Max line load | Design ms |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
        for row in rows:
            lines.append(
                "| {algorithm} | {coverage:.1%} | {direct:.1%} | {transfer:.1%} | {cost:.3f} | "
                "{ride:.3f} | {length:.3f} | {load:.1%} | {compute:.4f} |".format(
                    algorithm=row["algorithm"],
                    coverage=float(row["mean_coverage_rate"]),
                    direct=float(row["mean_direct_trip_rate"]),
                    transfer=float(row["mean_transfer_trip_rate"]),
                    cost=float(row["mean_generalized_cost_served"]),
                    ride=float(row["mean_ride_distance_served"]),
                    length=float(row["mean_total_line_length"]),
                    load=float(row["mean_max_line_load_share"]),
                    compute=float(row["mean_design_compute_ms"]),
                )
            )
        lines.extend(
            [
                "",
                "## Ranking discipline",
                "",
                "No weighted composite score is defined in V1. Coverage, passenger generalized cost, "
                "directness, load concentration, operator-side line length, and compute cost remain "
                "separate so trade-offs stay auditable.",
                "",
                "`results.json` stores the complete generated station geometry and OD matrix for every seed, "
                "so each benchmark instance is exactly reproducible.",
                "",
            ]
        )
        (self.run_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8")


def run_static_benchmark(
    algorithms: Iterable[str],
    seeds: Iterable[int],
    *,
    station_count: int = 10,
    total_trips: float = 1000.0,
    density: float = 0.65,
    distance_decay: float = 1.25,
    max_lines: int = 2,
    max_stations_per_line: int = 6,
    transfer_penalty: float = 20.0,
) -> tuple[tuple[StaticODEpisodeResult, ...], tuple[ExplicitODStaticInstance, ...]]:
    algorithm_ids = tuple(algorithms)
    seed_values = tuple(int(seed) for seed in seeds)
    if not algorithm_ids:
        raise ValueError("at least one static algorithm is required")
    unknown = sorted(set(algorithm_ids) - set(STATIC_ALGORITHMS.ids()))
    if unknown:
        raise ValueError(f"unknown static algorithms: {unknown}")
    if not seed_values:
        raise ValueError("at least one seed is required")
    budget = StaticDesignBudget(
        max_lines=max_lines,
        max_stations_per_line=max_stations_per_line,
    )
    instances = tuple(
        synthetic_static_od_instance(
            seed,
            station_count=station_count,
            total_trips=total_trips,
            density=density,
            distance_decay=distance_decay,
            budget=budget,
            transfer_penalty=transfer_penalty,
        )
        for seed in seed_values
    )
    results = tuple(
        run_static_algorithm(instance, algorithm_id)
        for instance in instances
        for algorithm_id in algorithm_ids
    )
    return results, instances


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Explicit OD Static V1 benchmark")
    parser.add_argument(
        "--algorithms",
        nargs="+",
        default=["geometry-nearest-v1", "od-demand-chain-v1"],
        choices=STATIC_ALGORITHMS.ids(),
    )
    parser.add_argument("--seeds", nargs="+", type=int, default=[42, 314, 2026, 4096, 65537])
    parser.add_argument("--station-count", type=int, default=10)
    parser.add_argument("--total-trips", type=float, default=1000.0)
    parser.add_argument("--density", type=float, default=0.65)
    parser.add_argument("--distance-decay", type=float, default=1.25)
    parser.add_argument("--max-lines", type=int, default=2)
    parser.add_argument("--max-stations-per-line", type=int, default=6)
    parser.add_argument("--transfer-penalty", type=float, default=20.0)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_STATIC_OD_OUTPUT_ROOT)
    parser.add_argument("--no-save", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    results, instances = run_static_benchmark(
        args.algorithms,
        args.seeds,
        station_count=args.station_count,
        total_trips=args.total_trips,
        density=args.density,
        distance_decay=args.distance_decay,
        max_lines=args.max_lines,
        max_stations_per_line=args.max_stations_per_line,
        transfer_penalty=args.transfer_penalty,
    )
    summaries = summarize_static_results(results)

    run_dir: Path | None = None
    if not args.no_save:
        parameters = {
            "station_count": args.station_count,
            "total_trips": args.total_trips,
            "density": args.density,
            "distance_decay": args.distance_decay,
            "max_lines": args.max_lines,
            "max_stations_per_line": args.max_stations_per_line,
            "transfer_penalty": args.transfer_penalty,
        }
        artifacts = StaticODArtifacts.create(
            args.output_root,
            algorithms=args.algorithms,
            seeds=args.seeds,
            instance_parameters=parameters,
        )
        artifacts.finalize(results, summaries, instances)
        run_dir = artifacts.run_dir

    if args.json_output:
        print(
            json.dumps(
                {
                    "benchmark_id": STATIC_OD_BENCHMARK_ID,
                    "results": _jsonable(results),
                    "summaries": _jsonable(summaries),
                    "run_dir": None if run_dir is None else str(run_dir),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    print("\nExplicit OD Static V1")
    print("No composite score: passenger and operator metrics are reported separately.\n")
    for row in summaries:
        print(
            f"{row.algorithm}: coverage={row.mean_coverage_rate:.1%} "
            f"direct={row.mean_direct_trip_rate:.1%} "
            f"gen_cost={row.mean_generalized_cost_served:.3f} "
            f"line_length={row.mean_total_line_length:.3f} "
            f"design_ms={row.mean_design_compute_ms:.4f}"
        )
    if run_dir is not None:
        print(f"\nArtifacts: {run_dir}")
