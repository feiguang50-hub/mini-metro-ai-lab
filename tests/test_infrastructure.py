import tempfile
import unittest
from pathlib import Path

from metro_lab.assignment import AssignmentLine
from metro_lab.infrastructure import (
    BarrierSegment,
    InfrastructureModel,
    evaluate_infrastructure,
    segments_intersect,
)
from metro_lab.problem_family import (
    EXPLICIT_OD_INFRASTRUCTURE_FAMILY_ID,
    ProblemDimension,
    get_problem_family_spec,
)
from metro_lab.static_infra import (
    InfrastructureArtifacts,
    run_infrastructure_algorithm,
    run_infrastructure_benchmark,
    summarize_infrastructure_results,
    synthetic_infrastructure_instance,
)


class InfrastructureContractTests(unittest.TestCase):
    def test_segment_intersection_and_barrier_cost(self):
        self.assertTrue(segments_intersect(0, 0, 10, 0, 5, -5, 5, 5))
        self.assertFalse(segments_intersect(0, 0, 4, 0, 5, -5, 5, 5))

        instance = synthetic_infrastructure_instance(42, station_count=4, max_lines=1, max_stations_per_line=4)
        nodes = {node.id: node for node in instance.nodes}
        left = min(nodes.values(), key=lambda node: node.x)
        right = max(nodes.values(), key=lambda node: node.x)
        line = AssignmentLine("cross", (left.id, right.id))
        result = evaluate_infrastructure(instance.nodes, (line,), instance.infrastructure)
        self.assertGreaterEqual(result.barrier_crossings, 1)
        self.assertGreater(result.construction_cost, result.total_length)

    def test_forbidden_barrier_marks_plan_infeasible(self):
        instance = synthetic_infrastructure_instance(
            314,
            station_count=4,
            max_lines=1,
            max_stations_per_line=4,
            forbidden_barrier=True,
        )
        left = min(instance.nodes, key=lambda node: node.x)
        right = max(instance.nodes, key=lambda node: node.x)
        evaluation = evaluate_infrastructure(
            instance.nodes,
            (AssignmentLine("cross", (left.id, right.id)),),
            instance.infrastructure,
        )
        self.assertFalse(evaluation.feasible)
        self.assertGreaterEqual(evaluation.forbidden_crossings, 1)

    def test_infrastructure_aware_algorithm_runs(self):
        instance = synthetic_infrastructure_instance(2026)
        baseline = run_infrastructure_algorithm(instance, "geometry-nearest-v1")
        aware = run_infrastructure_algorithm(instance, "infrastructure-aware-nearest-v1")
        self.assertEqual(baseline.seed, aware.seed)
        self.assertGreater(baseline.coverage_rate, 0.0)
        self.assertGreater(aware.coverage_rate, 0.0)
        self.assertGreaterEqual(baseline.construction_cost, 0.0)
        self.assertGreaterEqual(aware.construction_cost, 0.0)

    def test_benchmark_and_artifacts_freeze_barriers(self):
        results, instances = run_infrastructure_benchmark(
            ("geometry-nearest-v1", "infrastructure-aware-nearest-v1"),
            (42, 314),
        )
        self.assertEqual(len(results), 4)
        summaries = summarize_infrastructure_results(results)
        self.assertEqual(len(summaries), 2)
        self.assertTrue(instances[0].public()["infrastructure"]["barriers"])

        with tempfile.TemporaryDirectory() as temp:
            artifacts = InfrastructureArtifacts.create(
                Path(temp),
                algorithms=("geometry-nearest-v1", "infrastructure-aware-nearest-v1"),
                seeds=(42, 314),
                instance_parameters={"barrier_crossing_cost": 80.0},
            )
            artifacts.finalize(results, summaries, instances)
            self.assertTrue((artifacts.run_dir / "config.json").is_file())
            text = (artifacts.run_dir / "results.json").read_text(encoding="utf-8")
            self.assertIn("river-corridor", text)
            self.assertIn("construction_cost", text)

    def test_problem_family_claims_only_geometry_demand_infrastructure(self):
        family = get_problem_family_spec(EXPLICIT_OD_INFRASTRUCTURE_FAMILY_ID)
        self.assertEqual(
            set(family.dimensions),
            {ProblemDimension.GEOMETRY, ProblemDimension.DEMAND, ProblemDimension.INFRASTRUCTURE},
        )
        self.assertNotIn(ProblemDimension.CAPACITY, family.dimensions)
        self.assertNotIn(ProblemDimension.UNCERTAINTY, family.dimensions)

    def test_contract_validation(self):
        with self.assertRaisesRegex(ValueError, "non-zero length"):
            BarrierSegment("bad", 0, 0, 0, 0)
        with self.assertRaisesRegex(ValueError, "non-negative"):
            InfrastructureModel(unit_length_cost=-1)


if __name__ == "__main__":
    unittest.main()
