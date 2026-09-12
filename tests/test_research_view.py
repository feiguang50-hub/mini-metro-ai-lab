import unittest

from metro_lab.research_view import (
    RESEARCH_VIEW_CONTRACT_VERSION,
    build_research_snapshot,
    research_catalog,
)


class ResearchViewTests(unittest.TestCase):
    def test_catalog_exposes_three_research_families(self):
        catalog = research_catalog()
        self.assertEqual(catalog["contract_version"], RESEARCH_VIEW_CONTRACT_VERSION)
        self.assertEqual(
            {item["key"] for item in catalog["families"]},
            {"static", "infrastructure", "uncertainty"},
        )
        self.assertTrue(all(len(item["algorithms"]) == 2 for item in catalog["families"]))

    def test_static_snapshot_is_paired_and_complete(self):
        snapshot = build_research_snapshot("static", 42)
        self.assertEqual(snapshot["seed"], 42)
        self.assertEqual(len(snapshot["algorithms"]), 2)
        self.assertTrue(snapshot["instance"]["nodes"])
        self.assertTrue(snapshot["instance"]["demand"]["flows"])
        self.assertTrue(snapshot["research_discipline"]["paired_seed"])
        self.assertFalse(snapshot["research_discipline"]["composite_score"])
        for algorithm in snapshot["algorithms"]:
            self.assertTrue(algorithm["lines"])
            self.assertIn("coverage_rate", algorithm["metrics"])

    def test_infrastructure_snapshot_exposes_barrier_and_costs(self):
        snapshot = build_research_snapshot("infrastructure", 314)
        self.assertTrue(snapshot["barriers"])
        self.assertEqual(snapshot["barriers"][0]["id"], "river-corridor")
        for algorithm in snapshot["algorithms"]:
            self.assertIn("construction_cost", algorithm["metrics"])
            self.assertIn("barrier_crossings", algorithm["metrics"])
            self.assertIn("feasible", algorithm["metrics"])

    def test_uncertainty_snapshot_keeps_nominal_input_and_reports_oos_scenarios(self):
        snapshot = build_research_snapshot("uncertainty", 2026)
        self.assertEqual(snapshot["scenario_meta"]["count"], 8)
        self.assertIn("nominal-only", snapshot["scenario_meta"]["discipline"])
        for algorithm in snapshot["algorithms"]:
            self.assertEqual(len(algorithm["scenarios"]), 8)
            self.assertIn("oos_mean_coverage_rate", algorithm["metrics"])
            self.assertIn("oos_worst_generalized_cost", algorithm["metrics"])

    def test_invalid_family_and_seed_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "unknown research family"):
            build_research_snapshot("future-magic", 42)
        with self.assertRaisesRegex(ValueError, "seed"):
            build_research_snapshot("static", -1)


if __name__ == "__main__":
    unittest.main()
