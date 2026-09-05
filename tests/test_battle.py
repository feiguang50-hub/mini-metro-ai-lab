import json
import tempfile
import unittest
from pathlib import Path

from metro_lab.battle import BattleResult, BattleSideResult, run_battle, save_battle
from metro_lab.config import ENGINE_SRC
from metro_lab.scenarios import CLASSIC_SCENARIO_ID, STRESS_SCENARIO_ID


class BattlePureTests(unittest.TestCase):
    def test_save_battle_writes_machine_readable_result(self):
        left = BattleSideResult("a", 42, 10, 0, 1000, 10, False, 0)
        right = BattleSideResult("b", 42, 8, 0, 1000, 10, True, 1)
        result = BattleResult(42, left, right, "left", 2)
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = save_battle(result, output_root=Path(tmp), minutes=1.0, dt_ms=100)
            payload = json.loads((run_dir / "battle.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["result"]["winner"], "left")
        self.assertEqual(payload["result"]["delivery_margin"], 2)
        self.assertEqual(payload["result"]["scenario"], CLASSIC_SCENARIO_ID)
        self.assertEqual(payload["scenario"]["id"], CLASSIC_SCENARIO_ID)
        self.assertEqual(payload["result"]["left"]["seed"], 42)
        self.assertEqual(payload["result"]["right"]["seed"], 42)


@unittest.skipUnless(ENGINE_SRC.exists(), "vendor engine not bootstrapped")
class BattleEngineTests(unittest.TestCase):
    def test_same_algorithm_same_seed_is_exact_tie(self):
        result = run_battle("greedy-v1", "greedy-v1", 42, minutes=0.03)
        self.assertEqual(result.winner, "tie")
        self.assertEqual(result.delivery_margin, 0)
        self.assertEqual(result.scenario, CLASSIC_SCENARIO_ID)
        self.assertEqual(result.left, result.right)
        self.assertGreater(result.left.steps, 0)

    def test_stress_self_play_remains_exact_tie(self):
        result = run_battle(
            "greedy-v1",
            "greedy-v1",
            314,
            minutes=0.8,
            scenario=STRESS_SCENARIO_ID,
        )
        self.assertEqual(result.scenario, STRESS_SCENARIO_ID)
        self.assertEqual(result.winner, "tie")
        self.assertEqual(result.left, result.right)
        self.assertGreater(result.left.simulated_ms, 45_000)

    def test_battle_can_write_two_replays(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = run_battle(
                "greedy-v1",
                "greedy-v1",
                314,
                minutes=0.02,
                scenario=STRESS_SCENARIO_ID,
                left_replay=root / "left.jsonl.gz",
                right_replay=root / "right.jsonl.gz",
                replay_sample_ms=200,
            )
            self.assertEqual(result.winner, "tie")
            self.assertTrue((root / "left.jsonl.gz").is_file())
            self.assertTrue((root / "right.jsonl.gz").is_file())
            self.assertGreater((root / "left.jsonl.gz").stat().st_size, 0)
            self.assertGreater((root / "right.jsonl.gz").stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
