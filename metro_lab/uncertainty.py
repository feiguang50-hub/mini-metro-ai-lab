from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from random import Random
from typing import Iterable

from .demand import ODFlow, ODDemandMatrix

UNCERTAINTY_CONTRACT_VERSION = "1.0"


@dataclass(frozen=True)
class DemandScenario:
    """One frozen out-of-sample realization of an uncertain OD matrix."""

    id: str
    key: int
    demand: ODDemandMatrix

    def __post_init__(self) -> None:
        if not self.id or self.id.strip() != self.id:
            raise ValueError("scenario id must be a non-empty trimmed string")

    def public(self) -> dict[str, object]:
        return {
            "contract_version": UNCERTAINTY_CONTRACT_VERSION,
            "id": self.id,
            "key": self.key,
            "demand": self.demand.public(),
        }


@dataclass(frozen=True)
class DemandScenarioSet:
    """Evaluation-only demand futures kept outside the algorithm input."""

    nominal: ODDemandMatrix
    scenarios: tuple[DemandScenario, ...]
    relative_noise: float
    global_noise: float

    def __post_init__(self) -> None:
        if not self.scenarios:
            raise ValueError("uncertainty scenario set must contain at least one scenario")
        for name, value in (("relative_noise", self.relative_noise), ("global_noise", self.global_noise)):
            if not isfinite(float(value)) or not (0 <= value < 1):
                raise ValueError(f"{name} must be finite and in [0, 1)")
        ids = [item.id for item in self.scenarios]
        keys = [item.key for item in self.scenarios]
        if len(ids) != len(set(ids)):
            raise ValueError("scenario ids must be unique")
        if len(keys) != len(set(keys)):
            raise ValueError("scenario keys must be unique")
        for item in self.scenarios:
            if item.demand.station_ids != self.nominal.station_ids:
                raise ValueError("scenario station ids must match nominal demand")
            if item.demand.period_seconds != self.nominal.period_seconds:
                raise ValueError("scenario demand period must match nominal demand")

    def public(self) -> dict[str, object]:
        return {
            "contract_version": UNCERTAINTY_CONTRACT_VERSION,
            "relative_noise": self.relative_noise,
            "global_noise": self.global_noise,
            "nominal": self.nominal.public(),
            "scenarios": [item.public() for item in self.scenarios],
        }


def perturb_od_demand(
    nominal: ODDemandMatrix,
    *,
    key: int,
    relative_noise: float = 0.35,
    global_noise: float = 0.15,
) -> ODDemandMatrix:
    """Create one deterministic demand realization without renormalizing total trips.

    Each existing OD flow receives an idiosyncratic multiplicative shock plus a
    common system-wide shock. Not renormalizing preserves uncertainty in total
    demand volume instead of reducing the exercise to redistribution only.
    V1 preserves the nominal support: it perturbs positive OD pairs but does not
    invent previously absent travel markets.
    """

    for name, value in (("relative_noise", relative_noise), ("global_noise", global_noise)):
        if not isfinite(float(value)) or not (0 <= value < 1):
            raise ValueError(f"{name} must be finite and in [0, 1)")

    rng = Random(int(key))
    common = 1.0 + rng.uniform(-global_noise, global_noise)
    flows = tuple(
        ODFlow(
            origin_id=item.origin_id,
            destination_id=item.destination_id,
            trips=item.trips * common * (1.0 + rng.uniform(-relative_noise, relative_noise)),
        )
        for item in nominal.flows
    )
    return ODDemandMatrix(
        station_ids=nominal.station_ids,
        flows=flows,
        period_seconds=nominal.period_seconds,
        source="uncertainty-perturbation-v1",
        seed=int(key),
    )


def build_demand_scenarios(
    nominal: ODDemandMatrix,
    keys: Iterable[int],
    *,
    relative_noise: float = 0.35,
    global_noise: float = 0.15,
) -> DemandScenarioSet:
    key_values = tuple(int(key) for key in keys)
    if not key_values:
        raise ValueError("at least one evaluation scenario key is required")
    if len(set(key_values)) != len(key_values):
        raise ValueError("evaluation scenario keys must be unique")
    scenarios = tuple(
        DemandScenario(
            id=f"demand-future-{index:02d}",
            key=key,
            demand=perturb_od_demand(
                nominal,
                key=key,
                relative_noise=relative_noise,
                global_noise=global_noise,
            ),
        )
        for index, key in enumerate(key_values, start=1)
    )
    return DemandScenarioSet(
        nominal=nominal,
        scenarios=scenarios,
        relative_noise=float(relative_noise),
        global_noise=float(global_noise),
    )
