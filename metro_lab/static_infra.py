from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime, timezone
from math import hypot
from pathlib import Path
from random import Random
from statistics import mean
from typing import Any, Iterable

from .assignment import AssignmentLine
from .config import ROOT
from .infrastructure import (
    INFRASTRUCTURE_CONTRACT_VERSION,
    BarrierSegment,
    InfrastructureModel,
    evaluate_infrastructure,
    segment_infrastructure_cost,
)
from .static_od import (
    STATIC_ALGORITHMS,
    STATIC_DESIGN_CONTRACT_VERSION,
    ExplicitODStaticInstance,
    StaticAlgorithmMetadata,
    StaticDesignBudget,
    evaluate_static_plan,
    synthetic_static_od_instance,
)

STATIC_INFRA_BENCHMARK_ID = "explicit-od-infrastructure-v1"
STATIC_INFRA_BENCHMARK_VERSION = "1.0"
DEFAULT_STATIC_INFRA_OUTPUT_ROOT = ROOT / "output" / "static-infrastructure"


@dataclass(frozen=True)
class ExplicitODInfrastructureInstance:
    base: ExplicitODStaticInstance
    infrastructure: InfrastructureModel

    @property
    def id(self) -> str:
        return f"infra-{self.base.id}"

    @property
    def seed(self) -> int:
        return self.base.seed

    @property
    def nodes(self):
        return self.base.nodes

    @property
    def demand(self):
        return self.base.demand

    @property
    def budget(self):
        return self.base.budget

    @property
    def transfer_penalty(self) -> float:
        return self.base.transfer_penalty

    def public(self) -> dict[str, Any]:
        data = self.base.public()
        data["id"] = self.id
        data["benchmark_id"] = STATIC_INFRA_BENCHMARK_ID
        data["benchmark_version"] = STATIC_INFRA_BENCHMARK_VERSION
        data["infrastructure"] = self.infrastructure.public()
        return data


def synthetic_infrastructure_instance(
    seed: int,
    *,
    station_count: int = 10,
    total_trips: float = 1000.0,
    density: float = 0.65,
    distance_decay: float = 1.25,
    max_lines: int = 2,
    max_stations_per_line: int = 6,
    transfer_penalty: float = 20.0,
    unit_length_cost: float = 1.0,
    barrier_crossing_cost: float = 80.0,
    forbidden_barrier: bool = False,
) -> ExplicitODInfrastructureInstance:
    base = synthetic_static_od_instance(
        seed,
        station_count=station_count,
        total_trips=total_trips,
        density=density,
        distance_decay=distance_decay,
        budget=StaticDesignBudget(
            max_lines=max_lines,
            max_stations_per_line=max_stations_per_line,
        ),
        transfer_penalty=transfer_penalty,
    )
    rng = Random(seed ^ 0x9E3779B9)
    barrier_x = round(50.0 + rng.uniform(-8.0, 8.0), 6)
    model = InfrastructureModel(
        unit_length_cost=unit_length_cost,
        barriers=(
            BarrierSegment(
                id="river-corridor",
                x1=barrier_x,
                y1=-10.0,
                x2=barrier_x,
                y2=110.0,
                crossing_cost=barrier_crossing_cost,
                forbidden=forbidden_barrier,
            ),
        ),
    )
    return ExplicitODInfrastructureInstance(base=base, infrastructure=model)


def _split_order(
    order: tuple[str, ...],
    budget: StaticDesignBudget,
    *,
    prefix: str,
) -> tuple[AssignmentLine, ...]:
    lines: list[AssignmentLine] = []
    cursor = 0
    index = 1
    while cursor < len(order) - 1:
        if index > budget.max_lines:
            raise ValueError("design budget cannot represent station order")
        end = min(len(order), cursor + budget.max_stations_per_line)
        part = order[cursor:end]
        if len(part) < budget.min_stations_per_line:
            raise ValueError("cannot construct legal infrastructure line plan")
        lines.append(AssignmentLine(f"{prefix}-{index}", part))
        if end == len(order):
            break
        cursor = end - 1
        index += 1
    return tuple(lines)


class InfrastructureAwareNearestV1:
    metadata = StaticAlgorithmMetadata(
        id="infrastructure-aware-nearest-v1",
        name="Infrastructure Aware Nearest V1",
        version="1.0",
        description="Nearest-neighbor ordering that internalizes V1 length and barrier crossing cost.",
    )

    def design(self, instance) -> tuple[AssignmentLine, ...]:
        model = getattr(instance, "infrastructure", None)
        if model is None:
            raise ValueError("infrastructure-aware-nearest-v1 requires an infrastructure instance")
        nodes = {node.id: node for node in instance.nodes}
        centroid_x = mean(node.x for node in instance.nodes)
        centroid_y = mean(node.y for node in instance.nodes)
        start = min(
            instance.nodes,
            key=lambda node: (hypot(node.x - centroid_x, node.y - centroid_y), node.id),
        )
        order = [start.id]
        remaining = set(nodes) - {start.id}
        while remaining:
            left = nodes[order[-1]]

            def score(candidate_id: str):
                right = nodes[candidate_id]
                cost, crossings, forbidden = segment_infrastructure_cost(left, right, model)
                return (
                    forbidden,
                    cost,
                    crossings,
                    hypot(left.x - right.x, left.y - right.y),
                    candidate_id,
                )

            nxt = min(remaining, key=score)
            order.append(nxt)
            remaining.remove(nxt)
        return _split_order(tuple(order), instance.budget, prefix="infra")


if "infrastructure-aware-nearest-v1" not in STATIC_ALGORITHMS.ids():
    STATIC_ALGORITHMS.register(InfrastructureAwareNearestV1)


@dataclass(frozen=True)
class InfrastructureEpisodeResult:
    algorithm: str
    seed: int
    feasible: bool
    forbidden_crossings: int
    barrier_crossings: int
    construction_cost: float
    crossing_cost: float
    total_line_length: float
    coverage_rate: float
    direct_trip_rate: float
    transfer_trip_rate: float
    mean_generalized_cost_served: float
    mean_ride_distance_served: float
    design_compute_ms: float
    lines: tuple[AssignmentLine, ...]


@dataclass(frozen=True)
class InfrastructureSummary:
    algorithm: str
    episodes: int
    feasibility_rate: float
    mean_barrier_crossings: float
    mean_construction_cost: float
    mean_crossing_cost: float
    mean_total_line_length: float
    mean_coverage_rate: float
    mean_direct_trip_rate: float
    mean_generalized_cost_served: float
    mean_design_compute_ms: float


def run_infrastructure_algorithm(
    instance: ExplicitODInfrastructureInstance,
    algorithm_id: str,
) -> InfrastructureEpisodeResult:
    from time import perf_counter_ns

    algorithm = STATIC_ALGORITHMS.create(algorithm_id)
    start = perf_counter_ns()
    plan = algorithm.design(instance)
    elapsed_ms = (perf_counter_ns() - start) / 1_000_000.0
    passenger = evaluate_static_plan(
        instance,
        algorithm_id,
        plan,
        design_compute_ms=elapsed_ms,
    )
    infra = evaluate_infrastructure(instance.nodes, passenger.lines, instance.infrastructure)
    return InfrastructureEpisodeResult(
        algorithm=algorithm_id,
        seed=instance.seed,
        feasible=infra.feasible,
        forbidden_crossings=infra.forbidden_crossings,
        barrier_crossings=infra.barrier_crossings,
        construction_cost=infra.construction_cost,
        crossing_cost=infra.crossing_cost,
        total_line_length=infra.total_length,
        coverage_rate=passenger.coverage_rate,
        direct_trip_rate=passenger.direct_trip_rate,
        transfer_trip_rate=passenger.transfer_trip_rate,
        mean_generalized_cost_served=passenger.mean_generalized_cost_served,
        mean_ride_distance_served=passenger.mean_ride_distance_served,
        design_compute_ms=elapsed_ms,
        lines=passenger.lines,
    )


def run_infrastructure_benchmark(
    algorithms: Iterable[str],
    seeds: Iterable[int],
    **instance_kwargs,
) -> tuple[tuple[InfrastructureEpisodeResult, ...], tuple[ExplicitODInfrastructureInstance, ...]]:
    algorithm_ids = tuple(algorithms)
    seed_values = tuple(int(seed) for seed in seeds)
    if not algorithm_ids:
        raise ValueError("at least one infrastructure algorithm is required")
    unknown = sorted(set(algorithm_ids) - set(STATIC_ALGORITHMS.ids()))
    if unknown:
        raise ValueError(f"unknown static algorithms: {unknown}")
    if not seed_values:
        raise ValueError("at least one seed is required")
    instances = tuple(synthetic_infrastructure_instance(seed, **instance_kwargs) for seed in seed_values)
    results = tuple(
        run_infrastructure_algorithm(instance, algorithm_id)
        for instance in instances
        for algorithm_id in algorithm_ids
    )
    return results, instances


def summarize_infrastructure_results(
    results: Iterable[InfrastructureEpisodeResult],
) -> tuple[InfrastructureSummary, ...]:
    groups: dict[str, list[InfrastructureEpisodeResult]] = {}
    for row in results:
        groups.setdefault(row.algorithm, []).append(row)
    return tuple(
        InfrastructureSummary(
            algorithm=algorithm_id,
            episodes=len(rows),
            feasibility_rate=mean(1.0 if row.feasible else 0.0 for row in rows),
            mean_barrier_crossings=mean(row.barrier_crossings for row in rows),
            mean_construction_cost=mean(row.construction_cost for row in rows),
            mean_crossing_cost=mean(row.crossing_cost for row in rows),
            mean_total_line_length=mean(row.total_line_length for row in rows),
            mean_coverage_rate=mean(row.coverage_rate for row in rows),
            mean_direct_trip_rate=mean(row.direct_trip_rate for row in rows),
            mean_generalized_cost_served=mean(row.mean_generalized_cost_served for row in rows),
            mean_design_compute_ms=mean(row.design_compute_ms for row in rows),
        )
        for algorithm_id, rows in sorted(groups.items())
    )


def _jsonable(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return _jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


@dataclass(frozen=True)
class InfrastructureArtifacts:
    run_id: str
    run_dir: Path
    config: dict[str, Any]

    @classmethod
    def create(cls, output_root: Path, *, algorithms, seeds, instance_parameters):
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        run_id = f"{timestamp}-{STATIC_INFRA_BENCHMARK_ID}"
        run_dir = Path(output_root) / run_id
        suffix = 2
        while run_dir.exists():
            run_dir = Path(output_root) / f"{run_id}-{suffix:02d}"
            suffix += 1
        run_dir.mkdir(parents=True, exist_ok=False)
        config = {
            "schema_version": 1,
            "benchmark_id": STATIC_INFRA_BENCHMARK_ID,
            "benchmark_version": STATIC_INFRA_BENCHMARK_VERSION,
            "static_design_contract": STATIC_DESIGN_CONTRACT_VERSION,
            "infrastructure_contract": INFRASTRUCTURE_CONTRACT_VERSION,
            "algorithms": list(algorithms),
            "seeds": [int(seed) for seed in seeds],
            "instance_parameters": _jsonable(instance_parameters),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        (run_dir / "config.json").write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return cls(run_id=run_dir.name, run_dir=run_dir, config=config)

    def finalize(self, results, summaries, instances):
        result_rows = [_jsonable(row) for row in results]
        summary_rows = [_jsonable(row) for row in summaries]
        payload = {
            "schema_version": 1,
            "run_id": self.run_id,
            "config": self.config,
            "instances": [instance.public() for instance in instances],
            "results": result_rows,
            "summaries": summary_rows,
        }
        (self.run_dir / "results.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        scalar_fields = [
            "algorithm", "seed", "feasible", "forbidden_crossings", "barrier_crossings",
            "construction_cost", "crossing_cost", "total_line_length", "coverage_rate",
            "direct_trip_rate", "transfer_trip_rate", "mean_generalized_cost_served",
            "mean_ride_distance_served", "design_compute_ms",
        ]
        with (self.run_dir / "episodes.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=scalar_fields)
            writer.writeheader()
            for row in result_rows:
                writer.writerow({field: row.get(field) for field in scalar_fields})
        lines = [
            f"# Explicit OD Infrastructure V1 · {self.run_id}",
            "",
            "Passenger service and infrastructure cost remain separate metrics; no weighted composite score is defined.",
            "",
            "| Algorithm | Feasible | Crossings | Construction cost | Coverage | Direct | Gen. cost | Line length | Design ms |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
        for row in summary_rows:
            lines.append(
                "| {algorithm} | {feasibility_rate:.1%} | {mean_barrier_crossings:.2f} | {mean_construction_cost:.3f} | "
                "{mean_coverage_rate:.1%} | {mean_direct_trip_rate:.1%} | {mean_generalized_cost_served:.3f} | "
                "{mean_total_line_length:.3f} | {mean_design_compute_ms:.4f} |".format(**row)
            )
        (self.run_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Explicit OD Infrastructure V1 benchmark")
    parser.add_argument(
        "--algorithms",
        nargs="+",
        default=["geometry-nearest-v1", "infrastructure-aware-nearest-v1"],
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
    parser.add_argument("--unit-length-cost", type=float, default=1.0)
    parser.add_argument("--barrier-crossing-cost", type=float, default=80.0)
    parser.add_argument("--forbidden-barrier", action="store_true")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_STATIC_INFRA_OUTPUT_ROOT)
    parser.add_argument("--no-save", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    parameters = {
        "station_count": args.station_count,
        "total_trips": args.total_trips,
        "density": args.density,
        "distance_decay": args.distance_decay,
        "max_lines": args.max_lines,
        "max_stations_per_line": args.max_stations_per_line,
        "transfer_penalty": args.transfer_penalty,
        "unit_length_cost": args.unit_length_cost,
        "barrier_crossing_cost": args.barrier_crossing_cost,
        "forbidden_barrier": args.forbidden_barrier,
    }
    results, instances = run_infrastructure_benchmark(args.algorithms, args.seeds, **parameters)
    summaries = summarize_infrastructure_results(results)
    run_dir = None
    if not args.no_save:
        artifacts = InfrastructureArtifacts.create(
            args.output_root,
            algorithms=args.algorithms,
            seeds=args.seeds,
            instance_parameters=parameters,
        )
        artifacts.finalize(results, summaries, instances)
        run_dir = artifacts.run_dir
    payload = {
        "benchmark_id": STATIC_INFRA_BENCHMARK_ID,
        "summaries": _jsonable(summaries),
        "run_dir": None if run_dir is None else str(run_dir),
    }
    if args.json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    print("\nExplicit OD Infrastructure V1")
    print("No composite score: service and infrastructure cost are reported separately.\n")
    for row in summaries:
        print(
            f"{row.algorithm}: feasible={row.feasibility_rate:.1%} crossings={row.mean_barrier_crossings:.2f} "
            f"construction={row.mean_construction_cost:.3f} coverage={row.mean_coverage_rate:.1%} "
            f"gen_cost={row.mean_generalized_cost_served:.3f}"
        )
    if run_dir is not None:
        print(f"\nArtifacts: {run_dir}")
