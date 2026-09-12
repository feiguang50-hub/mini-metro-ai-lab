from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any

PROBLEM_FAMILY_CONTRACT_VERSION = "1.0"


class ProblemDimension(StrEnum):
    GEOMETRY = "geometry"
    DEMAND = "demand"
    CAPACITY = "capacity"
    INFRASTRUCTURE = "infrastructure"
    UNCERTAINTY = "uncertainty"
    EVOLUTION = "evolution"


@dataclass(frozen=True)
class ProblemDimensionSpec:
    id: ProblemDimension
    name: str
    research_question: str

    def public(self) -> dict[str, str]:
        return {
            "id": str(self.id),
            "name": self.name,
            "research_question": self.research_question,
        }


DIMENSION_SPECS: tuple[ProblemDimensionSpec, ...] = (
    ProblemDimensionSpec(ProblemDimension.GEOMETRY, "Geometry", "How should lines connect spatially distributed stations?"),
    ProblemDimensionSpec(ProblemDimension.DEMAND, "Demand", "How should network structure respond to passenger demand?"),
    ProblemDimensionSpec(ProblemDimension.CAPACITY, "Capacity", "How should limited vehicles and carrying capacity be allocated?"),
    ProblemDimensionSpec(ProblemDimension.INFRASTRUCTURE, "Infrastructure", "How do construction costs and spatial barriers change feasible networks?"),
    ProblemDimensionSpec(ProblemDimension.UNCERTAINTY, "Uncertainty", "How robust is a plan when future demand or events are not known exactly?"),
    ProblemDimensionSpec(ProblemDimension.EVOLUTION, "Evolution", "How should planning react when the candidate network changes over time?"),
)

DIMENSIONS = {spec.id: spec for spec in DIMENSION_SPECS}


@dataclass(frozen=True)
class ProblemFamilySpec:
    id: str
    name: str
    version: str
    summary: str
    dimensions: tuple[ProblemDimension, ...]
    scope_notes: tuple[str, ...] = ()

    def public(self) -> dict[str, Any]:
        data = asdict(self)
        data["contract_version"] = PROBLEM_FAMILY_CONTRACT_VERSION
        data["dimensions"] = [str(item) for item in self.dimensions]
        data["scope_notes"] = list(self.scope_notes)
        return data


SIMULATOR_BASELINE_FAMILY_ID = "simulator-baseline-v1"
EXOGENOUS_GROWTH_FAMILY_ID = "exogenous-growth-v1"
EXPLICIT_OD_STATIC_FAMILY_ID = "explicit-od-static-v1"
EXPLICIT_OD_INFRASTRUCTURE_FAMILY_ID = "explicit-od-infrastructure-v1"


PROBLEM_FAMILY_SPECS: tuple[ProblemFamilySpec, ...] = (
    ProblemFamilySpec(
        id=SIMULATOR_BASELINE_FAMILY_ID,
        name="Dynamic Capacitated Baseline",
        version="1.0",
        summary="Spatial line planning with simulated passenger demand and finite fleet capacity; kept as the historical baseline family.",
        dimensions=(ProblemDimension.GEOMETRY, ProblemDimension.DEMAND, ProblemDimension.CAPACITY),
        scope_notes=(
            "Demand follows the pinned simulator model; this is not yet an explicit OD-matrix benchmark.",
            "No explicit construction-cost, barrier, uncertainty, or land-use feedback model is claimed.",
        ),
    ),
    ProblemFamilySpec(
        id=EXOGENOUS_GROWTH_FAMILY_ID,
        name="Exogenous Network Growth",
        version="1.0",
        summary="The baseline family plus an externally scheduled expansion of the visible station set, testing adaptation to a changing planning domain.",
        dimensions=(ProblemDimension.GEOMETRY, ProblemDimension.DEMAND, ProblemDimension.CAPACITY, ProblemDimension.EVOLUTION),
        scope_notes=(
            "Evolution currently means exogenous station availability over time only.",
            "It does not yet model endogenous population, land-use, or demand feedback from new lines.",
        ),
    ),
    ProblemFamilySpec(
        id=EXPLICIT_OD_STATIC_FAMILY_ID,
        name="Explicit OD Static Network Design",
        version="1.0",
        summary="Static line-network design against an explicit directional origin-destination demand matrix under a declared line/station design budget.",
        dimensions=(ProblemDimension.GEOMETRY, ProblemDimension.DEMAND),
        scope_notes=(
            "Passenger demand is an explicit OD matrix and is evaluated with Passenger Assignment V1.",
            "The line/station design budget constrains feasible designs but is not a vehicle-capacity model.",
            "V1 has no service frequency, vehicle capacity, infrastructure cost/barrier, uncertainty, or evolution model.",
        ),
    ),
    ProblemFamilySpec(
        id=EXPLICIT_OD_INFRASTRUCTURE_FAMILY_ID,
        name="Explicit OD Infrastructure Network Design",
        version="1.0",
        summary="Static explicit-OD line design with length-dependent construction cost and finite spatial barriers that can penalize or forbid crossings.",
        dimensions=(ProblemDimension.GEOMETRY, ProblemDimension.DEMAND, ProblemDimension.INFRASTRUCTURE),
        scope_notes=(
            "Infrastructure V1 models unit line-length cost plus finite straight barrier segments with fixed crossing cost or hard crossing prohibition.",
            "Barriers are mathematical abstractions for structures such as rivers, protected corridors, or unusually expensive crossings; they do not simulate construction workflow.",
            "Passenger service quality and infrastructure cost remain separate reported metrics; V1 defines no weighted composite score.",
            "Vehicle capacity, service frequency, uncertain future demand, and land-use feedback remain outside this family.",
        ),
    ),
)

PROBLEM_FAMILIES = {spec.id: spec for spec in PROBLEM_FAMILY_SPECS}


def get_problem_family_spec(family_id: str) -> ProblemFamilySpec:
    try:
        return PROBLEM_FAMILIES[family_id]
    except KeyError as exc:
        raise ValueError(f"unknown problem family: {family_id}") from exc


def problem_family_catalog() -> list[dict[str, Any]]:
    return [spec.public() for spec in PROBLEM_FAMILY_SPECS]


def problem_dimension_catalog() -> list[dict[str, str]]:
    return [spec.public() for spec in DIMENSION_SPECS]
