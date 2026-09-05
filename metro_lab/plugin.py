from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol, runtime_checkable

from .planner import Decision
from .problem import MetroPlanningState, PROBLEM_CONTRACT_VERSION, PROBLEM_ID


@dataclass(frozen=True)
class AlgorithmMetadata:
    """Stable metadata for one interchangeable planning algorithm."""

    id: str
    name: str
    version: str
    family: str
    description: str = ""
    problem_id: str = PROBLEM_ID
    problem_contract: str = PROBLEM_CONTRACT_VERSION


@runtime_checkable
class PlanningAlgorithm(Protocol):
    """Minimal plugin surface for future backend-neutral algorithms.

    Implementations receive only ``MetroPlanningState`` and return the existing
    serializable ``Decision`` action envelope. They do not receive the simulator,
    viewer, HTTP runtime, replay writer, or scenario internals.
    """

    metadata: AlgorithmMetadata

    def reset(self, state: MetroPlanningState) -> None: ...

    def act(self, state: MetroPlanningState) -> Decision: ...


AlgorithmFactory = Callable[[], PlanningAlgorithm]


class PluginRegistrationError(ValueError):
    pass


class AlgorithmPluginRegistry:
    """Small explicit registry used as the future algorithm loading boundary."""

    def __init__(self) -> None:
        self._factories: dict[str, AlgorithmFactory] = {}
        self._metadata: dict[str, AlgorithmMetadata] = {}

    def register(self, factory: AlgorithmFactory) -> AlgorithmMetadata:
        plugin = factory()
        if not isinstance(plugin, PlanningAlgorithm):
            raise PluginRegistrationError("factory must return a PlanningAlgorithm")
        metadata = plugin.metadata
        if not metadata.id or metadata.id.strip() != metadata.id:
            raise PluginRegistrationError("algorithm id must be a non-empty trimmed string")
        if metadata.problem_id != PROBLEM_ID:
            raise PluginRegistrationError(
                f"unsupported problem id {metadata.problem_id!r}; expected {PROBLEM_ID!r}"
            )
        if metadata.problem_contract != PROBLEM_CONTRACT_VERSION:
            raise PluginRegistrationError(
                "unsupported problem contract "
                f"{metadata.problem_contract!r}; expected {PROBLEM_CONTRACT_VERSION!r}"
            )
        if metadata.id in self._factories:
            raise PluginRegistrationError(f"duplicate algorithm id: {metadata.id}")
        self._factories[metadata.id] = factory
        self._metadata[metadata.id] = metadata
        return metadata

    def create(self, algorithm_id: str) -> PlanningAlgorithm:
        try:
            return self._factories[algorithm_id]()
        except KeyError as exc:
            raise KeyError(f"unknown plugin algorithm: {algorithm_id}") from exc

    def metadata(self) -> tuple[AlgorithmMetadata, ...]:
        return tuple(self._metadata[key] for key in sorted(self._metadata))

    def ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._factories))
