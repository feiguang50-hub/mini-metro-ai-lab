import json
import time
import unittest

from metro_lab.algorithms import DEFAULT_ALGORITHM_ID
from metro_lab.config import ENGINE_SRC
from metro_lab.scenarios import STRESS_SCENARIO_ID


@unittest.skipUnless(ENGINE_SRC.exists(), "vendor engine not bootstrapped")
class EngineSmokeTests(unittest.TestCase):
    def test_runtime_advances_and_serializes(self):
        from metro_lab.engine import LabRuntime

        runtime = LabRuntime(seed=42)
        runtime.start()
        try:
            time.sleep(0.7)
            snapshot = runtime.snapshot()
        finally:
            runtime.stop()

        self.assertEqual(snapshot["runtime"]["seed"], 42)
        self.assertEqual(snapshot["runtime"]["algorithm_id"], DEFAULT_ALGORITHM_ID)
        self.assertGreaterEqual(len(snapshot["game"]["stations"]), 2)
        self.assertGreater(snapshot["game"]["time_ms"], 0)
        self.assertEqual(snapshot["runtime"]["scenario_id"], STRESS_SCENARIO_ID)
        self.assertEqual(snapshot["runtime"]["station_count"], len(snapshot["game"]["stations"]))
        self.assertEqual(snapshot["runtime"]["station_spawn_interval_ms"], 45_000)
        self.assertGreater(snapshot["runtime"]["passenger_max_wait_time_ms"], 0)
        self.assertGreater(snapshot["runtime"]["overdue_threshold"], 0)
        self.assertGreaterEqual(snapshot["runtime"]["risk"], 0)
        self.assertLessEqual(snapshot["runtime"]["risk"], 100)
        self.assertGreaterEqual(snapshot["runtime"]["max_wait_ms"], 0)
        self.assertTrue(any(item["id"] == DEFAULT_ALGORITHM_ID for item in snapshot["algorithms"]))
        self.assertIn(snapshot["decision"]["action"]["type"], {
            "noop",
            "create_path",
            "replace_path",
            "assign_locomotive",
            "attach_carriage",
        })
        json.dumps(snapshot, ensure_ascii=False)

    def test_algorithm_control_rejects_unavailable_algorithm(self):
        from metro_lab.engine import LabRuntime

        runtime = LabRuntime(seed=42)
        try:
            with self.assertRaises(ValueError):
                runtime.control("algorithm", "beam-search")
            snapshot = runtime.snapshot()
            self.assertEqual(snapshot["runtime"]["algorithm_id"], DEFAULT_ALGORITHM_ID)
        finally:
            runtime.stop()


if __name__ == "__main__":
    unittest.main()
