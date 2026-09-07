from __future__ import annotations

from dataclasses import dataclass
from math import ceil, isfinite
from time import perf_counter_ns
from typing import Callable, TypeVar

BENCHMARK_CONTRACT_VERSION = 1

T = TypeVar("T")


@dataclass(frozen=True)
class ComputeBudget:
    """Optional wall-clock compute limits for one benchmark episode.

    V1 records compliance but does not forcibly interrupt algorithms. Hard
    isolation/timeouts require a process boundary and belong to a later runner
    milestone rather than being approximated with unsafe in-process signals.
    """

    decision_ms: float | None = None
    episode_ms: float | None = None

    def __post_init__(self) -> None:
        for name, value in (
            ("decision_ms", self.decision_ms),
            ("episode_ms", self.episode_ms),
        ):
            if value is not None and (not isfinite(value) or value <= 0):
                raise ValueError(f"{name} must be a positive finite number or None")

    def public(self) -> dict[str, float | None]:
        return {
            "decision_ms": self.decision_ms,
            "episode_ms": self.episode_ms,
        }


@dataclass(frozen=True)
class ComputeStats:
    benchmark_contract_version: int
    setup_compute_ms: float
    decision_calls: int
    decision_compute_ms: float
    planner_compute_ms: float
    mean_decision_ms: float
    p95_decision_ms: float
    max_decision_ms: float
    decision_budget_ms: float | None
    episode_compute_budget_ms: float | None
    decision_budget_violations: int
    episode_compute_budget_exceeded: bool
    compute_budget_compliant: bool

    @property
    def decision_budget_violation_rate(self) -> float:
        if self.decision_calls <= 0:
            return 0.0
        return self.decision_budget_violations / self.decision_calls


class PlannerComputeProfiler:
    """Measure end-to-end planner wall-clock cost without changing behavior.

    Setup includes planner construction and reset so an algorithm cannot hide
    expensive precomputation outside ``act``. Decision timing covers the whole
    planner call exposed to the experiment harness, including standard adapter
    work required to turn the public problem state into a backend action.
    """

    def __init__(
        self,
        budget: ComputeBudget | None = None,
        *,
        clock_ns: Callable[[], int] = perf_counter_ns,
    ) -> None:
        self.budget = budget or ComputeBudget()
        self._clock_ns = clock_ns
        self._setup_ns = 0
        self._decision_ns: list[int] = []

    def measure_setup(self, call: Callable[[], T]) -> T:
        start = self._clock_ns()
        try:
            return call()
        finally:
            self._setup_ns += max(0, self._clock_ns() - start)

    def measure_decision(self, call: Callable[[], T]) -> T:
        start = self._clock_ns()
        try:
            return call()
        finally:
            self._decision_ns.append(max(0, self._clock_ns() - start))

    def snapshot(self) -> ComputeStats:
        decision_ms = [value / 1_000_000.0 for value in self._decision_ns]
        setup_ms = self._setup_ns / 1_000_000.0
        decision_total_ms = sum(decision_ms)
        planner_total_ms = setup_ms + decision_total_ms

        if decision_ms:
            ordered = sorted(decision_ms)
            rank = max(1, ceil(0.95 * len(ordered)))
            p95_ms = ordered[rank - 1]
            mean_ms = decision_total_ms / len(decision_ms)
            max_ms = ordered[-1]
        else:
            p95_ms = 0.0
            mean_ms = 0.0
            max_ms = 0.0

        decision_limit = self.budget.decision_ms
        decision_violations = (
            sum(value > decision_limit for value in decision_ms)
            if decision_limit is not None
            else 0
        )
        episode_limit = self.budget.episode_ms
        episode_exceeded = bool(
            episode_limit is not None and planner_total_ms > episode_limit
        )

        return ComputeStats(
            benchmark_contract_version=BENCHMARK_CONTRACT_VERSION,
            setup_compute_ms=round(setup_ms, 6),
            decision_calls=len(decision_ms),
            decision_compute_ms=round(decision_total_ms, 6),
            planner_compute_ms=round(planner_total_ms, 6),
            mean_decision_ms=round(mean_ms, 6),
            p95_decision_ms=round(p95_ms, 6),
            max_decision_ms=round(max_ms, 6),
            decision_budget_ms=decision_limit,
            episode_compute_budget_ms=episode_limit,
            decision_budget_violations=decision_violations,
            episode_compute_budget_exceeded=episode_exceeded,
            compute_budget_compliant=(decision_violations == 0 and not episode_exceeded),
        )
