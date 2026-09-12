from __future__ import annotations

from dataclasses import asdict, is_dataclass, replace
from typing import Any

from .assignment import assign_passengers
from .static_infra import (
    STATIC_INFRA_BENCHMARK_ID,
    run_infrastructure_algorithm,
    synthetic_infrastructure_instance,
)
from .static_od import (
    STATIC_ALGORITHMS,
    STATIC_OD_BENCHMARK_ID,
    run_static_algorithm,
    synthetic_static_od_instance,
)
from .static_uncertain import (
    STATIC_UNCERTAINTY_BENCHMARK_ID,
    run_uncertainty_algorithm,
    synthetic_uncertain_instance,
)

RESEARCH_VIEW_CONTRACT_VERSION = "1.0"

FAMILIES: dict[str, dict[str, Any]] = {
    "static": {
        "id": STATIC_OD_BENCHMARK_ID,
        "name": "Explicit OD Static V1",
        "summary": "显式 OD 下的静态线路设计，比较客流服务质量与线路几何。",
        "algorithms": ("geometry-nearest-v1", "od-demand-chain-v1"),
    },
    "infrastructure": {
        "id": STATIC_INFRA_BENCHMARK_ID,
        "name": "Infrastructure / Barrier V1",
        "summary": "加入建设长度成本与空间障碍，观察现实约束如何改变线路结构。",
        "algorithms": ("geometry-nearest-v1", "infrastructure-aware-nearest-v1"),
    },
    "uncertainty": {
        "id": STATIC_UNCERTAINTY_BENCHMARK_ID,
        "name": "Demand Uncertainty V1",
        "summary": "算法只看名义 OD，再用冻结且隐藏的需求场景检验鲁棒性。",
        "algorithms": ("geometry-nearest-v1", "od-demand-chain-v1"),
    },
}


def _jsonable(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return _jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    return value


def _algorithm_meta(algorithm_id: str) -> dict[str, Any]:
    metadata = STATIC_ALGORITHMS.create(algorithm_id).metadata
    return metadata.public()


def _uncertainty_scenarios(instance, lines) -> list[dict[str, float | int]]:
    rows: list[dict[str, float | int]] = []
    for index, scenario in enumerate(instance.evaluation_scenarios.scenarios):
        realized = replace(instance.nominal, demand=scenario.demand)
        assignment = assign_passengers(
            realized.demand,
            realized.nodes,
            lines,
            transfer_penalty=realized.transfer_penalty,
        )
        served = assignment.served_trips
        total = assignment.total_trips
        rows.append(
            {
                "index": index + 1,
                "total_trips": total,
                "coverage_rate": served / total if total else 0.0,
                "generalized_cost": (
                    assignment.weighted_generalized_cost / served if served else 0.0
                ),
            }
        )
    return rows


def research_catalog() -> dict[str, Any]:
    return {
        "contract_version": RESEARCH_VIEW_CONTRACT_VERSION,
        "families": [
            {
                "key": key,
                "id": spec["id"],
                "name": spec["name"],
                "summary": spec["summary"],
                "algorithms": [
                    _algorithm_meta(algorithm_id) for algorithm_id in spec["algorithms"]
                ],
            }
            for key, spec in FAMILIES.items()
        ],
    }


def build_research_snapshot(family: str, seed: int = 42) -> dict[str, Any]:
    if family not in FAMILIES:
        raise ValueError(f"unknown research family: {family}")
    if seed < 0 or seed > 2_147_483_647:
        raise ValueError("seed must be in 0..2147483647")

    spec = FAMILIES[family]
    algorithm_ids = tuple(spec["algorithms"])
    barriers: list[dict[str, Any]] = []
    scenario_meta: dict[str, Any] | None = None

    if family == "static":
        instance = synthetic_static_od_instance(seed)
        public_instance = instance.public()
        results = [run_static_algorithm(instance, algorithm_id) for algorithm_id in algorithm_ids]
        algorithms = [
            {
                "metadata": _algorithm_meta(result.algorithm),
                "lines": _jsonable(result.lines),
                "metrics": {
                    "coverage_rate": result.coverage_rate,
                    "direct_trip_rate": result.direct_trip_rate,
                    "transfer_trip_rate": result.transfer_trip_rate,
                    "generalized_cost": result.mean_generalized_cost_served,
                    "ride_distance": result.mean_ride_distance_served,
                    "line_length": result.total_line_length,
                    "design_compute_ms": result.design_compute_ms,
                },
            }
            for result in results
        ]
    elif family == "infrastructure":
        instance = synthetic_infrastructure_instance(seed)
        public_instance = instance.public()
        barriers = _jsonable(instance.infrastructure.barriers)
        results = [
            run_infrastructure_algorithm(instance, algorithm_id)
            for algorithm_id in algorithm_ids
        ]
        algorithms = [
            {
                "metadata": _algorithm_meta(result.algorithm),
                "lines": _jsonable(result.lines),
                "metrics": {
                    "coverage_rate": result.coverage_rate,
                    "direct_trip_rate": result.direct_trip_rate,
                    "transfer_trip_rate": result.transfer_trip_rate,
                    "generalized_cost": result.mean_generalized_cost_served,
                    "ride_distance": result.mean_ride_distance_served,
                    "line_length": result.total_line_length,
                    "construction_cost": result.construction_cost,
                    "crossing_cost": result.crossing_cost,
                    "barrier_crossings": result.barrier_crossings,
                    "forbidden_crossings": result.forbidden_crossings,
                    "feasible": result.feasible,
                    "design_compute_ms": result.design_compute_ms,
                },
            }
            for result in results
        ]
    else:
        instance = synthetic_uncertain_instance(seed)
        public_instance = instance.nominal.public()
        scenario_meta = {
            "contract": instance.evaluation_scenarios.public().get("contract_version"),
            "count": len(instance.evaluation_scenarios.scenarios),
            "discipline": "nominal-only design; frozen out-of-sample evaluation futures",
        }
        results = [run_uncertainty_algorithm(instance, algorithm_id) for algorithm_id in algorithm_ids]
        algorithms = [
            {
                "metadata": _algorithm_meta(result.algorithm),
                "lines": _jsonable(result.lines),
                "metrics": {
                    "nominal_coverage_rate": result.nominal_coverage_rate,
                    "nominal_generalized_cost": result.nominal_generalized_cost,
                    "oos_mean_coverage_rate": result.out_of_sample_mean_coverage_rate,
                    "oos_worst_coverage_rate": result.out_of_sample_worst_coverage_rate,
                    "oos_coverage_std": result.out_of_sample_coverage_std,
                    "oos_mean_generalized_cost": result.out_of_sample_mean_generalized_cost,
                    "oos_worst_generalized_cost": result.out_of_sample_worst_generalized_cost,
                    "oos_generalized_cost_std": result.out_of_sample_generalized_cost_std,
                    "design_compute_ms": result.design_compute_ms,
                },
                "scenarios": _uncertainty_scenarios(instance, result.lines),
            }
            for result in results
        ]

    return {
        "contract_version": RESEARCH_VIEW_CONTRACT_VERSION,
        "family": {
            "key": family,
            "id": spec["id"],
            "name": spec["name"],
            "summary": spec["summary"],
        },
        "seed": seed,
        "instance": public_instance,
        "barriers": barriers,
        "scenario_meta": scenario_meta,
        "algorithms": algorithms,
        "research_discipline": {
            "paired_seed": True,
            "composite_score": False,
            "metric_policy": "passenger, infrastructure, robustness and compute metrics stay separate",
        },
    }
