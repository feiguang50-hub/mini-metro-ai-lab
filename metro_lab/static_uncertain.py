from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict, dataclass, is_dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, pstdev
from time import perf_counter_ns
from typing import Any, Iterable

from .assignment import assign_passengers
from .config import ROOT
from .static_od import (
    STATIC_ALGORITHMS,
    STATIC_DESIGN_CONTRACT_VERSION,
    ExplicitODStaticInstance,
    StaticDesignBudget,
    synthetic_static_od_instance,
    validate_line_plan,
)
from .uncertainty import UNCERTAINTY_CONTRACT_VERSION, DemandScenarioSet, build_demand_scenarios

STATIC_UNCERTAINTY_BENCHMARK_ID = "explicit-od-uncertainty-v1"
STATIC_UNCERTAINTY_BENCHMARK_VERSION = "1.0"
DEFAULT_STATIC_UNCERTAINTY_OUTPUT_ROOT = ROOT / "output" / "static-uncertainty"


@dataclass(frozen=True)
class UncertainStaticInstance:
    nominal: ExplicitODStaticInstance
    evaluation_scenarios: DemandScenarioSet

    @property
    def seed(self) -> int:
        return self.nominal.seed

    def public(self) -> dict[str, Any]:
        return {
            "benchmark_id": STATIC_UNCERTAINTY_BENCHMARK_ID,
            "benchmark_version": STATIC_UNCERTAINTY_BENCHMARK_VERSION,
            "uncertainty_contract": UNCERTAINTY_CONTRACT_VERSION,
            "nominal": self.nominal.public(),
            "evaluation_scenarios": self.evaluation_scenarios.public(),
        }


def _future_keys(instance_seed: int, count: int) -> tuple[int, ...]:
    if count <= 0:
        raise ValueError("scenario_count must be positive")
    # Separate deterministic namespace from the nominal generator seed.
    base = (int(instance_seed) ^ 0xA5A5A5A5) & 0xFFFFFFFF
    return tuple((base + 0x9E3779B1 * (index + 1)) & 0xFFFFFFFF for index in range(count))


def synthetic_uncertain_instance(
    seed: int,
    *,
    station_count: int = 10,
    total_trips: float = 1000.0,
    density: float = 0.65,
    distance_decay: float = 1.25,
    max_lines: int = 2,
    max_stations_per_line: int = 6,
    transfer_penalty: float = 20.0,
    scenario_count: int = 8,
    relative_noise: float = 0.35,
    global_noise: float = 0.15,
) -> UncertainStaticInstance:
    nominal = synthetic_static_od_instance(
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
    scenarios = build_demand_scenarios(
        nominal.demand,
        _future_keys(seed, scenario_count),
        relative_noise=relative_noise,
        global_noise=global_noise,
    )
    return UncertainStaticInstance(nominal=nominal, evaluation_scenarios=scenarios)


@dataclass(frozen=True)
class UncertaintyEpisodeResult:
    algorithm: str
    seed: int
    design_compute_ms: float
    nominal_coverage_rate: float
    nominal_generalized_cost: float
    out_of_sample_mean_coverage_rate: float
    out_of_sample_worst_coverage_rate: float
    out_of_sample_coverage_std: float
    out_of_sample_mean_generalized_cost: float
    out_of_sample_worst_generalized_cost: float
    out_of_sample_generalized_cost_std: float
    scenario_count: int
    lines: tuple


@dataclass(frozen=True)
class UncertaintySummary:
    algorithm: str
    episodes: int
    mean_nominal_coverage_rate: float
    mean_oos_coverage_rate: float
    mean_worst_coverage_rate: float
    mean_coverage_std: float
    mean_nominal_generalized_cost: float
    mean_oos_generalized_cost: float
    mean_worst_generalized_cost: float
    mean_generalized_cost_std: float
    mean_design_compute_ms: float


def _assignment_metrics(instance: ExplicitODStaticInstance, lines) -> tuple[float, float]:
    assigned = assign_passengers(
        instance.demand,
        instance.nodes,
        lines,
        transfer_penalty=instance.transfer_penalty,
    )
    total = assigned.total_trips
    served = assigned.served_trips
    coverage = served / total if total else 0.0
    generalized = assigned.weighted_generalized_cost / served if served else float("inf")
    return coverage, generalized


def run_uncertainty_algorithm(
    instance: UncertainStaticInstance,
    algorithm_id: str,
) -> UncertaintyEpisodeResult:
    """Design once from nominal demand, then evaluate on hidden frozen futures.

    The algorithm receives only ``instance.nominal``. Evaluation scenario OD
    matrices are never passed into ``design`` and therefore cannot be used as an
    oracle by a standard Static Design V1 plugin.
    """

    algorithm = STATIC_ALGORITHMS.create(algorithm_id)
    start = perf_counter_ns()
    plan = validate_line_plan(instance.nominal, algorithm.design(instance.nominal))
    elapsed_ms = (perf_counter_ns() - start) / 1_000_000.0

    nominal_coverage, nominal_cost = _assignment_metrics(instance.nominal, plan)
    scenario_coverages: list[float] = []
    scenario_costs: list[float] = []
    for scenario in instance.evaluation_scenarios.scenarios:
        realized = replace(instance.nominal, demand=scenario.demand)
        coverage, cost = _assignment_metrics(realized, plan)
        scenario_coverages.append(coverage)
        scenario_costs.append(cost)

    return UncertaintyEpisodeResult(
        algorithm=algorithm_id,
        seed=instance.seed,
        design_compute_ms=elapsed_ms,
        nominal_coverage_rate=nominal_coverage,
        nominal_generalized_cost=nominal_cost,
        out_of_sample_mean_coverage_rate=mean(scenario_coverages),
        out_of_sample_worst_coverage_rate=min(scenario_coverages),
        out_of_sample_coverage_std=pstdev(scenario_coverages),
        out_of_sample_mean_generalized_cost=mean(scenario_costs),
        out_of_sample_worst_generalized_cost=max(scenario_costs),
        out_of_sample_generalized_cost_std=pstdev(scenario_costs),
        scenario_count=len(scenario_coverages),
        lines=plan,
    )


def run_uncertainty_benchmark(
    algorithms: Iterable[str],
    seeds: Iterable[int],
    **instance_kwargs,
) -> tuple[tuple[UncertaintyEpisodeResult, ...], tuple[UncertainStaticInstance, ...]]:
    algorithm_ids = tuple(algorithms)
    seed_values = tuple(int(seed) for seed in seeds)
    if not algorithm_ids:
        raise ValueError("at least one uncertainty algorithm is required")
    unknown = sorted(set(algorithm_ids) - set(STATIC_ALGORITHMS.ids()))
    if unknown:
        raise ValueError(f"unknown static algorithms: {unknown}")
    if not seed_values:
        raise ValueError("at least one seed is required")
    instances = tuple(synthetic_uncertain_instance(seed, **instance_kwargs) for seed in seed_values)
    results = tuple(
        run_uncertainty_algorithm(instance, algorithm_id)
        for instance in instances
        for algorithm_id in algorithm_ids
    )
    return results, instances


def summarize_uncertainty_results(results: Iterable[UncertaintyEpisodeResult]) -> tuple[UncertaintySummary, ...]:
    groups: dict[str, list[UncertaintyEpisodeResult]] = {}
    for row in results:
        groups.setdefault(row.algorithm, []).append(row)
    return tuple(
        UncertaintySummary(
            algorithm=algorithm_id,
            episodes=len(rows),
            mean_nominal_coverage_rate=mean(row.nominal_coverage_rate for row in rows),
            mean_oos_coverage_rate=mean(row.out_of_sample_mean_coverage_rate for row in rows),
            mean_worst_coverage_rate=mean(row.out_of_sample_worst_coverage_rate for row in rows),
            mean_coverage_std=mean(row.out_of_sample_coverage_std for row in rows),
            mean_nominal_generalized_cost=mean(row.nominal_generalized_cost for row in rows),
            mean_oos_generalized_cost=mean(row.out_of_sample_mean_generalized_cost for row in rows),
            mean_worst_generalized_cost=mean(row.out_of_sample_worst_generalized_cost for row in rows),
            mean_generalized_cost_std=mean(row.out_of_sample_generalized_cost_std for row in rows),
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
class UncertaintyArtifacts:
    run_id: str
    run_dir: Path
    config: dict[str, Any]

    @classmethod
    def create(cls, output_root: Path, *, algorithms, seeds, instance_parameters):
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        base = f"{timestamp}-{STATIC_UNCERTAINTY_BENCHMARK_ID}"
        output_root = Path(output_root)
        output_root.mkdir(parents=True, exist_ok=True)
        run_dir = output_root / base
        suffix = 2
        while run_dir.exists():
            run_dir = output_root / f"{base}-{suffix:02d}"
            suffix += 1
        run_dir.mkdir()
        config = {
            "schema_version": 1,
            "benchmark_id": STATIC_UNCERTAINTY_BENCHMARK_ID,
            "benchmark_version": STATIC_UNCERTAINTY_BENCHMARK_VERSION,
            "static_design_contract": STATIC_DESIGN_CONTRACT_VERSION,
            "uncertainty_contract": UNCERTAINTY_CONTRACT_VERSION,
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
            "instances": [item.public() for item in instances],
            "results": result_rows,
            "summaries": summary_rows,
        }
        (self.run_dir / "results.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        fields = [
            "algorithm", "seed", "design_compute_ms", "nominal_coverage_rate",
            "nominal_generalized_cost", "out_of_sample_mean_coverage_rate",
            "out_of_sample_worst_coverage_rate", "out_of_sample_coverage_std",
            "out_of_sample_mean_generalized_cost", "out_of_sample_worst_generalized_cost",
            "out_of_sample_generalized_cost_std", "scenario_count",
        ]
        with (self.run_dir / "episodes.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for row in result_rows:
                writer.writerow({field: row.get(field) for field in fields})
        lines = [
            f"# Explicit OD Uncertainty V1 · {self.run_id}",
            "",
            "Algorithms design from nominal demand only. Frozen out-of-sample demand realizations are evaluation-only.",
            "No weighted composite score is defined.",
            "",
            "| Algorithm | Nominal coverage | OOS mean coverage | OOS worst coverage | OOS mean cost | OOS worst cost | Cost std | Design ms |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
        for row in summary_rows:
            lines.append(
                "| {algorithm} | {mean_nominal_coverage_rate:.1%} | {mean_oos_coverage_rate:.1%} | "
                "{mean_worst_coverage_rate:.1%} | {mean_oos_generalized_cost:.3f} | "
                "{mean_worst_generalized_cost:.3f} | {mean_generalized_cost_std:.3f} | "
                "{mean_design_compute_ms:.4f} |".format(**row)
            )
        (self.run_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Explicit OD Uncertainty V1 benchmark")
    parser.add_argument("--algorithms", nargs="+", default=["geometry-nearest-v1", "od-demand-chain-v1"], choices=STATIC_ALGORITHMS.ids())
    parser.add_argument("--seeds", nargs="+", type=int, default=[42, 314, 2026, 4096, 65537])
    parser.add_argument("--station-count", type=int, default=10)
    parser.add_argument("--total-trips", type=float, default=1000.0)
    parser.add_argument("--density", type=float, default=0.65)
    parser.add_argument("--distance-decay", type=float, default=1.25)
    parser.add_argument("--max-lines", type=int, default=2)
    parser.add_argument("--max-stations-per-line", type=int, default=6)
    parser.add_argument("--transfer-penalty", type=float, default=20.0)
    parser.add_argument("--scenario-count", type=int, default=8)
    parser.add_argument("--relative-noise", type=float, default=0.35)
    parser.add_argument("--global-noise", type=float, default=0.15)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_STATIC_UNCERTAINTY_OUTPUT_ROOT)
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
        "scenario_count": args.scenario_count,
        "relative_noise": args.relative_noise,
        "global_noise": args.global_noise,
    }
    results, instances = run_uncertainty_benchmark(args.algorithms, args.seeds, **parameters)
    summaries = summarize_uncertainty_results(results)
    run_dir = None
    if not args.no_save:
        artifacts = UncertaintyArtifacts.create(args.output_root, algorithms=args.algorithms, seeds=args.seeds, instance_parameters=parameters)
        artifacts.finalize(results, summaries, instances)
        run_dir = artifacts.run_dir
    payload = {
        "benchmark_id": STATIC_UNCERTAINTY_BENCHMARK_ID,
        "summaries": _jsonable(summaries),
        "run_dir": None if run_dir is None else str(run_dir),
    }
    if args.json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    print("\nExplicit OD Uncertainty V1")
    print("Design sees nominal demand only; evaluation futures are frozen and hidden.\n")
    for row in summaries:
        print(
            f"{row.algorithm}: nominal={row.mean_nominal_coverage_rate:.1%} "
            f"oos={row.mean_oos_coverage_rate:.1%} worst={row.mean_worst_coverage_rate:.1%} "
            f"oos_cost={row.mean_oos_generalized_cost:.3f} worst_cost={row.mean_worst_generalized_cost:.3f}"
        )
    if run_dir is not None:
        print(f"\nArtifacts: {run_dir}")
