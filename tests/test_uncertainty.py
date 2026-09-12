import tempfile
import unittest
from pathlib import Path

from metro_lab.assignment import AssignmentLine
from metro_lab.problem_family import (
    EXPLICIT_OD_UNCERTAINTY_FAMILY_ID,
    ProblemDimension,
    get_problem_family_spec,
)
from metro_lab.static_od import STATIC_ALGORITHMS, StaticAlgorithmMetadata
from metro_lab.static_uncertain import (
    UncertaintyArtifacts,
    run_uncertainty_algorithm,
    run_uncertainty_benchmark,
    summarize_uncertainty_results,
    synthetic_uncertain_instance,
)
from metro_lab.uncertainty import build_demand_scenarios, perturb_od_demand


class NominalOnlyProbe:
    metadata = StaticAlgorithmMetadata(
        id="nominal-only-probe-test",
        name="Nominal Only Probe Test",
        version="1.0",
        description="Asserts that hidden evaluation futures are not exposed to design().",
    )

    def design(self, instance):
        if hasattr(instance, "evaluation_scenarios"):
            raise AssertionError("evaluation scenarios leaked into algorithm input")
        station_ids = tuple(node.id for node in instance.nodes)
        width = instance.budget.max_stations_per_line
        lines = []
        cursor = 0
        index = 1
        while cursor < len(station_ids) - 1:
            end = min(len(station_ids), cursor + width)
            lines.append(AssignmentLine(f"probe-{index}", station_ids[cursor:end]))
            if end == len(station_ids):
                break
            cursor = end - 1
            index += 1
        return tuple(lines)


class DemandUncertaintyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if "nominal-only-probe-test" not in STATIC_ALGORITHMS.ids():
            STATIC_ALGORITHMS.register(NominalOnlyProbe)

    def test_perturbation_is_deterministic_and_not_renormalized(self):
        instance = synthetic_uncertain_instance(42, scenario_count=2)
        nominal = instance.nominal.demand
        first = perturb_od_demand(nominal, key=1234)
        second = perturb_od_demand(nominal, key=1234)
        other = perturb_od_demand(nominal, key=5678)
        self.assertEqual(first, second)
        self.assertNotEqual(first.flows, other.flows)
        self.assertNotAlmostEqual(first.total_trips, nominal.total_trips)
        self.assertEqual(first.station_ids, nominal.station_ids)

    def test_scenario_set_is_frozen_and_reproducible(self):
        nominal = synthetic_uncertain_instance(314, scenario_count=1).nominal.demand
        first = build_demand_scenarios(nominal, (11, 22, 33))
        second = build_demand_scenarios(nominal, (11, 22, 33))
        self.assertEqual(first, second)
        self.assertEqual([item.key for item in first.scenarios], [11, 22, 33])
        self.assertEqual(len({item.demand.total_trips for item in first.scenarios}), 3)

    def test_algorithm_receives_nominal_instance_only(self):
        instance = synthetic_uncertain_instance(2026, scenario_count=4)
        result = run_uncertainty_algorithm(instance, "nominal-only-probe-test")
        self.assertEqual(result.scenario_count, 4)
        self.assertGreater(result.out_of_sample_mean_coverage_rate, 0.0)

    def test_benchmark_reports_out_of_sample_mean_worst_and_variability(self):
        results, instances = run_uncertainty_benchmark(
            ("geometry-nearest-v1", "od-demand-chain-v1"),
            (42, 314),
            scenario_count=4,
        )
        self.assertEqual(len(results), 4)
        self.assertEqual(len(instances), 2)
        for row in results:
            self.assertLessEqual(row.out_of_sample_worst_coverage_rate, row.out_of_sample_mean_coverage_rate)
            self.assertGreaterEqual(row.out_of_sample_worst_generalized_cost, row.out_of_sample_mean_generalized_cost)
            self.assertGreaterEqual(row.out_of_sample_generalized_cost_std, 0.0)
        summaries = summarize_uncertainty_results(results)
        self.assertEqual(len(summaries), 2)

    def test_artifacts_freeze_nominal_and_evaluation_demand_matrices(self):
        results, instances = run_uncertainty_benchmark(
            ("geometry-nearest-v1",),
            (42,),
            scenario_count=3,
        )
        summaries = summarize_uncertainty_results(results)
        with tempfile.TemporaryDirectory() as temp:
            artifacts = UncertaintyArtifacts.create(
                Path(temp),
                algorithms=("geometry-nearest-v1",),
                seeds=(42,),
                instance_parameters={"scenario_count": 3},
            )
            artifacts.finalize(results, summaries, instances)
            text = (artifacts.run_dir / "results.json").read_text(encoding="utf-8")
            summary = (artifacts.run_dir / "summary.md").read_text(encoding="utf-8")
            self.assertIn('"evaluation_scenarios"', text)
            self.assertIn('"nominal"', text)
            self.assertIn('"demand-future-01"', text)
            self.assertIn("evaluation-only", summary)
            self.assertIn("No weighted composite score", summary)

    def test_problem_family_claims_uncertainty_without_capacity(self):
        family = get_problem_family_spec(EXPLICIT_OD_UNCERTAINTY_FAMILY_ID)
        self.assertEqual(
            set(family.dimensions),
            {ProblemDimension.GEOMETRY, ProblemDimension.DEMAND, ProblemDimension.UNCERTAINTY},
        )
        self.assertNotIn(ProblemDimension.CAPACITY, family.dimensions)
        self.assertNotIn(ProblemDimension.INFRASTRUCTURE, family.dimensions)

    def test_uncertainty_validation(self):
        instance = synthetic_uncertain_instance(7, scenario_count=2)
        nominal = instance.nominal.demand
        with self.assertRaisesRegex(ValueError, "unique"):
            build_demand_scenarios(nominal, (5, 5))
        with self.assertRaisesRegex(ValueError, "relative_noise"):
            perturb_od_demand(nominal, key=1, relative_noise=1.0)


if __name__ == "__main__":
    unittest.main()
