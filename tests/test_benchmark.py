from __future__ import annotations

import unittest

from metro_lab.benchmark import (
    BENCHMARK_CONTRACT_VERSION,
    ComputeBudget,
    PlannerComputeProfiler,
)


class FakeClock:
    def __init__(self, values: list[int]) -> None:
        self._values = iter(values)

    def __call__(self) -> int:
        return next(self._values)


class BenchmarkContractTests(unittest.TestCase):
    def test_profiler_counts_setup_and_tail_latency_against_budgets(self) -> None:
        # setup=4ms, decisions=2ms and 4ms -> total planner compute=10ms.
        clock = FakeClock([
            0,
            4_000_000,
            4_000_000,
            6_000_000,
            6_000_000,
            10_000_000,
        ])
        profiler = PlannerComputeProfiler(
            ComputeBudget(decision_ms=3.0, episode_ms=9.0),
            clock_ns=clock,
        )

        self.assertEqual(profiler.measure_setup(lambda: "planner"), "planner")
        self.assertEqual(profiler.measure_decision(lambda: "a"), "a")
        self.assertEqual(profiler.measure_decision(lambda: "b"), "b")

        stats = profiler.snapshot()
        self.assertEqual(stats.benchmark_contract_version, BENCHMARK_CONTRACT_VERSION)
        self.assertEqual(stats.setup_compute_ms, 4.0)
        self.assertEqual(stats.decision_calls, 2)
        self.assertEqual(stats.decision_compute_ms, 6.0)
        self.assertEqual(stats.planner_compute_ms, 10.0)
        self.assertEqual(stats.mean_decision_ms, 3.0)
        self.assertEqual(stats.p95_decision_ms, 4.0)
        self.assertEqual(stats.max_decision_ms, 4.0)
        self.assertEqual(stats.decision_budget_violations, 1)
        self.assertTrue(stats.episode_compute_budget_exceeded)
        self.assertFalse(stats.compute_budget_compliant)
        self.assertEqual(stats.decision_budget_violation_rate, 0.5)

    def test_unbounded_budget_still_records_compute_without_false_violations(self) -> None:
        clock = FakeClock([0, 1_000_000, 1_000_000, 1_500_000])
        profiler = PlannerComputeProfiler(clock_ns=clock)
        profiler.measure_setup(lambda: None)
        profiler.measure_decision(lambda: None)

        stats = profiler.snapshot()
        self.assertEqual(stats.setup_compute_ms, 1.0)
        self.assertEqual(stats.mean_decision_ms, 0.5)
        self.assertEqual(stats.decision_budget_violations, 0)
        self.assertFalse(stats.episode_compute_budget_exceeded)
        self.assertTrue(stats.compute_budget_compliant)

    def test_budget_values_must_be_positive_and_finite(self) -> None:
        for kwargs in (
            {"decision_ms": 0},
            {"decision_ms": -1},
            {"decision_ms": float("inf")},
            {"episode_ms": 0},
            {"episode_ms": float("nan")},
        ):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    ComputeBudget(**kwargs)


if __name__ == "__main__":
    unittest.main()
