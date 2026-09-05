import json
import time
import unittest

from metro_lab.config import ENGINE_SRC


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
        self.assertGreaterEqual(len(snapshot["game"]["stations"]), 2)
        self.assertGreater(snapshot["game"]["time_ms"], 0)
        self.assertIn(snapshot["decision"]["action"]["type"], {
            "noop",
            "create_path",
            "replace_path",
            "assign_locomotive",
            "attach_carriage",
        })
        json.dumps(snapshot, ensure_ascii=False)


if __name__ == "__main__":
    unittest.main()
