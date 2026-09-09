from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any

PROBLEM_FAMILY_CONTRACT_VERSION = "1.0"


class ProblemDimension(StrEnum):
    """Independent mathematical structure that a benchmark family may expose."""

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
    ProblemDimensionSpec(
        id=ProblemDimension.GEOMETRY,
        name="Geometry",
        research_question="How should lines connect spatially distributed stations?",
    ),
    ProblemDimensionSpec(
        id=ProblemDimension.DEMAND,
        name="Demand",
        research_question="How should network structure respond to passenger demand?",
    ),
    ProblemDimensionSpec(
        id=ProblemDimension.CAPACITY,
        name="Capacity",
        research_question="How should limited vehicles and carrying capacity be allocated?",
    ),
    ProblemDimensionSpec(
        id=ProblemDimension.INFRASTRUCTURE,
        name="Infrastructure",
        research_question="How do construction costs and spatial barriers change feasible networks?",
    ),
    ProblemDimensionSpec(
        id=ProblemDimension.UNCERTAINTY,
        name="Uncertainty",
        research_question="How robust is a plan when future demand or events are not known exactly?",
    ),
    ProblemDimensionSpec(
        id=ProblemDimension.EVOLUTION,
        name="Evolution",
        research_question="How should planning react when the candidate network changes over time?",
    ),
)

DIMENSIONS = {spec.id: spec for spec in DIMENSION_SPECS}


@dataclass(frozen=True)
class ProblemFamilySpec:
    """Versioned benchmark family defined by mathematical dimensions, not UI rules."""

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


PROBLEM_FAMILY_SPECS: tuple[ProblemFamilySpec, ...] = (
    ProblemFamilySpec(
        id=SIMULATOR_BASELINE_FAMILY_ID,
        name="Dynamic Capacitated Baseline",
        version="1.0",
        summary=(
            "Spatial line planning with simulated passenger demand and finite fleet capacity; "
            "kept as the historical baseline family."
        ),
        dimensions=(
            ProblemDimension.GEOMETRY,
            ProblemDimension.DEMAND,
            ProblemDimension.CAPACITY,
        ),
        scope_notes=(
            "Demand follows the pinned simulator model; this is not yet an explicit OD-matrix benchmark.",
            "No explicit construction-cost, barrier, uncertainty, or land-use feedback model is claimed.",
        ),
    ),
    ProblemFamilySpec(
        id=EXOGENOUS_GROWTH_FAMILY_ID,
        name="Exogenous Network Growth",
        version="1.0",
        summary=(
            "The baseline family plus an externally scheduled expansion of the visible station set, "
            "testing adaptation to a changing planning domain."
        ),
        dimensions=(
            ProblemDimension.GEOMETRY,
            ProblemDimension.DEMAND,
            ProblemDimension.CAPACITY,
            ProblemDimension.EVOLUTION,
        ),
        scope_notes=(
            "Evolution currently means exogenous station availability over time only.",
            "It does not yet model endogenous population, land-use, or demand feedback from new lines.",
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
