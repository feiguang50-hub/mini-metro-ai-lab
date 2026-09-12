import json
import tempfile
import unittest
from pathlib import Path

from metro_lab.assignment import AssignmentLine
from metro_lab.problem_family import EXPLICIT_OD_STATIC_FAMILY_ID, get_problem_family_spec
from metro_lab.static_od import (
    STATIC_ALGORITHMS,
    STATIC_DESIGN_CONTRACT_VERSION,
    STATIC_OD_BENCHMARK_ID,
    StaticODArtifacts,
    run_static_algorithm,
    run_static_benchmark,
    summarize_static_results,
    synthetic_static_od_instance,
    validate_line_plan,
)


class ExplicitODStaticV1Tests(unittest.TestCase):
    def test_instance_generation_is_exactly_reproducible(self):
        first = synthetic_static_od_instance(42)
        second = synthetic_static_od_instance(42)
        other = synthetic_static_od_instance(43)

        self.assertEqual(first, second)
        self.assertNotEqual(first.nodes, other.nodes)
        self.assertNotEqual(first.demand.flows, other.demand.flows)
        self.assertEqual(first.public()["benchmark_id"], STATIC_OD_BENCHMARK_ID)
        self.assertEqual(first.public()["static_design_contract"], STATIC_DESIGN_CONTRACT_VERSION)

    def test_builtin_reference_algorithms_are_deterministic_and_legal(self):
        instance = synthetic_static_od_instance(314)
        builtins = {"geometry-nearest-v1", "od-demand-chain-v1"}
        self.assertTrue(builtins.issubset(set(STATIC_ALGORITHMS.ids())))
        for algorithm_id in sorted(builtins):
            algorithm = STATIC_ALGORITHMS.create(algorithm_id)
            first = algorithm.design(instance)
            second = STATIC_ALGORITHMS.create(algorithm_id).design(instance)
            self.assertEqual(first, second)
            self.assertEqual(validate_line_plan(instance, first), first)
            covered = {station_id for line in first for station_id in line.station_ids}
            self.assertEqual(covered, {node.id for node in instance.nodes})

    def test_evaluation_reports_separate_passenger_and_operator_metrics(self):
        instance = synthetic_static_od_instance(2026)
        result = run_static_algorithm(instance, "geometry-nearest-v1")

        self.assertEqual(result.algorithm, "geometry-nearest-v1")
        self.assertGreater(result.total_line_length, 0.0)
        self.assertGreater(result.total_trips, 0.0)
        self.assertAlmostEqual(result.coverage_rate, 1.0)
        self.assertGreaterEqual(result.direct_trip_rate, 0.0)
        self.assertLessEqual(result.direct_trip_rate, 1.0)
        self.assertGreaterEqual(result.transfer_trip_rate, 0.0)
        self.assertLessEqual(result.transfer_trip_rate, 1.0)
        self.assertGreater(result.mean_generalized_cost_served, 0.0)
        self.assertGreaterEqual(result.design_compute_ms, 0.0)

    def test_design_budget_rejects_illegal_plan(self):
        instance = synthetic_static_od_instance(7)
        with self.assertRaisesRegex(ValueError, "max_lines"):
            validate_line_plan(
                instance,
                (
                    AssignmentLine("a", ("S00", "S01")),
                    AssignmentLine("b", ("S01", "S02")),
                    AssignmentLine("c", ("S02", "S03")),
                ),
            )
        with self.assertRaisesRegex(ValueError, "max_stations_per_line"):
            validate_line_plan(
                instance,
                (
                    AssignmentLine(
                        "a",
                        ("S00", "S01", "S02", "S03", "S04", "S05", "S06"),
                    ),
                ),
            )

    def test_benchmark_runs_paired_seeds_for_both_reference_algorithms(self):
        results, instances = run_static_benchmark(
            ("geometry-nearest-v1", "od-demand-chain-v1"),
            (42, 314),
        )
        self.assertEqual(len(instances), 2)
        self.assertEqual(len(results), 4)
        self.assertEqual({row.seed for row in results}, {42, 314})
        self.assertEqual(
            {row.algorithm for row in results},
            {"geometry-nearest-v1", "od-demand-chain-v1"},
        )
        summaries = summarize_static_results(results)
        self.assertEqual(len(summaries), 2)
        self.assertTrue(all(row.episodes == 2 for row in summaries))

    def test_artifacts_freeze_complete_instances_and_no_composite_score(self):
        results, instances = run_static_benchmark(
            ("geometry-nearest-v1", "od-demand-chain-v1"),
            (42,),
        )
        summaries = summarize_static_results(results)
        with tempfile.TemporaryDirectory() as temp:
            artifacts = StaticODArtifacts.create(
                Path(temp),
                algorithms=("geometry-nearest-v1", "od-demand-chain-v1"),
                seeds=(42,),
                instance_parameters={
                    "station_count": 10,
                    "total_trips": 1000.0,
                    "density": 0.65,
                    "distance_decay": 1.25,
                    "max_lines": 2,
                    "max_stations_per_line": 6,
                    "transfer_penalty": 20.0,
                },
            )
            artifacts.finalize(results, summaries, instances)

            config = json.loads((artifacts.run_dir / "config.json").read_text(encoding="utf-8"))
            payload = json.loads((artifacts.run_dir / "results.json").read_text(encoding="utf-8"))
            summary = (artifacts.run_dir / "summary.md").read_text(encoding="utf-8")

            self.assertEqual(config["benchmark_id"], STATIC_OD_BENCHMARK_ID)
            self.assertEqual(config["problem_family_id"], EXPLICIT_OD_STATIC_FAMILY_ID)
            self.assertEqual(payload["instances"][0]["seed"], 42)
            self.assertTrue(payload["instances"][0]["nodes"])
            self.assertTrue(payload["instances"][0]["demand"]["flows"])
            self.assertIn("No weighted composite score", summary)
            self.assertNotIn("composite_score", payload)
            self.assertTrue((artifacts.run_dir / "episodes.csv").is_file())

    def test_static_problem_family_does_not_claim_capacity(self):
        family = get_problem_family_spec(EXPLICIT_OD_STATIC_FAMILY_ID)
        self.assertEqual(family.id, STATIC_OD_BENCHMARK_ID)
        self.assertEqual({str(item) for item in family.dimensions}, {"geometry", "demand"})


if __name__ == "__main__":
    unittest.main()
