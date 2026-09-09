import unittest

from metro_lab.problem_family import (
    EXOGENOUS_GROWTH_FAMILY_ID,
    PROBLEM_FAMILY_CONTRACT_VERSION,
    SIMULATOR_BASELINE_FAMILY_ID,
    ProblemDimension,
    get_problem_family_spec,
    problem_dimension_catalog,
    problem_family_catalog,
)
from metro_lab.scenarios import CLASSIC_SCENARIO_ID, STRESS_SCENARIO_ID, get_scenario_spec


class ProblemFamilyContractTests(unittest.TestCase):
    def test_dimension_catalog_is_unique_and_complete(self):
        rows = problem_dimension_catalog()
        ids = [row["id"] for row in rows]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(set(ids), {str(item) for item in ProblemDimension})

    def test_current_families_do_not_overclaim_unimplemented_dimensions(self):
        baseline = get_problem_family_spec(SIMULATOR_BASELINE_FAMILY_ID)
        growth = get_problem_family_spec(EXOGENOUS_GROWTH_FAMILY_ID)

        self.assertEqual(
            set(baseline.dimensions),
            {
                ProblemDimension.GEOMETRY,
                ProblemDimension.DEMAND,
                ProblemDimension.CAPACITY,
            },
        )
        self.assertEqual(
            set(growth.dimensions),
            set(baseline.dimensions) | {ProblemDimension.EVOLUTION},
        )
        for family in (baseline, growth):
            self.assertNotIn(ProblemDimension.INFRASTRUCTURE, family.dimensions)
            self.assertNotIn(ProblemDimension.UNCERTAINTY, family.dimensions)

    def test_scenarios_freeze_full_problem_family_metadata(self):
        classic = get_scenario_spec(CLASSIC_SCENARIO_ID).public()
        stress = get_scenario_spec(STRESS_SCENARIO_ID).public()

        self.assertEqual(classic["problem_family_id"], SIMULATOR_BASELINE_FAMILY_ID)
        self.assertEqual(stress["problem_family_id"], EXOGENOUS_GROWTH_FAMILY_ID)
        self.assertEqual(
            classic["problem_family"]["contract_version"],
            PROBLEM_FAMILY_CONTRACT_VERSION,
        )
        self.assertIn("geometry", classic["problem_family"]["dimensions"])
        self.assertIn("evolution", stress["problem_family"]["dimensions"])

    def test_family_catalog_is_versioned_and_unique(self):
        rows = problem_family_catalog()
        ids = [row["id"] for row in rows]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(row["contract_version"] == "1.0" for row in rows))
        self.assertTrue(all(row["scope_notes"] for row in rows))


if __name__ == "__main__":
    unittest.main()
