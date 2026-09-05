import unittest

from metro_lab.scenarios import (
    CLASSIC_SCENARIO_ID,
    DEFAULT_SCENARIO_ID,
    STRESS_SCENARIO_ID,
    STRESS_STATION_SPAWN_INTERVAL_MS,
    get_scenario_spec,
    scenario_catalog,
    scenario_ids,
)


class ScenarioRegistryTests(unittest.TestCase):
    def test_default_preserves_classic_history(self):
        self.assertEqual(DEFAULT_SCENARIO_ID, CLASSIC_SCENARIO_ID)

    def test_registry_exposes_classic_and_stress(self):
        self.assertEqual(scenario_ids(), [CLASSIC_SCENARIO_ID, STRESS_SCENARIO_ID])
        catalog = scenario_catalog()
        self.assertEqual([item["id"] for item in catalog], scenario_ids())
        self.assertIsNone(get_scenario_spec(CLASSIC_SCENARIO_ID).station_spawn_interval_ms)
        self.assertEqual(
            get_scenario_spec(STRESS_SCENARIO_ID).station_spawn_interval_ms,
            STRESS_STATION_SPAWN_INTERVAL_MS,
        )

    def test_unknown_scenario_is_rejected(self):
        with self.assertRaises(ValueError):
            get_scenario_spec("future-chaos-v99")


if __name__ == "__main__":
    unittest.main()
