import gzip
import json
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path

from metro_lab.experiments import ExperimentArtifacts, ReplayWriter


@dataclass(frozen=True)
class FakeResult:
    algorithm: str
    seed: int
    deliveries: int


@dataclass(frozen=True)
class FakeSummary:
    algorithm: str
    episodes: int
    mean_deliveries: float
    median_deliveries: float
    min_deliveries: int
    max_deliveries: int
    game_over_rate: float
    invalid_actions: int


class ExperimentArtifactTests(unittest.TestCase):
    def test_experiment_writes_machine_and_human_artifacts(self):
        with tempfile.TemporaryDirectory() as temp:
            artifacts = ExperimentArtifacts.create(
                Path(temp),
                algorithms=["greedy-v1"],
                seeds=[42],
                minutes=1.0,
                dt_ms=100,
                replay_sample_ms=1000,
            )
            replay_path = artifacts.replay_path("greedy-v1", 42)
            with ReplayWriter(replay_path, {"algorithm": "greedy-v1", "seed": 42}) as replay:
                replay.write_frame(
                    time_ms=1000,
                    game={"deliveries": 3, "time_ms": 1000},
                    decision={"action": {"type": "noop"}},
                    action_ok=True,
                    kind="sample",
                )

            artifacts.finalize(
                [FakeResult("greedy-v1", 42, 3)],
                [FakeSummary("greedy-v1", 1, 3.0, 3.0, 3, 3, 0.0, 0)],
            )

            self.assertTrue((artifacts.run_dir / "config.json").is_file())
            self.assertTrue((artifacts.run_dir / "results.json").is_file())
            self.assertTrue((artifacts.run_dir / "episodes.csv").is_file())
            self.assertTrue((artifacts.run_dir / "summary.md").is_file())
            self.assertTrue(replay_path.is_file())

            with gzip.open(replay_path, "rt", encoding="utf-8") as handle:
                rows = [json.loads(line) for line in handle]
            self.assertEqual(rows[0]["type"], "header")
            self.assertEqual(rows[1]["type"], "frame")
            self.assertEqual(rows[1]["game"]["deliveries"], 3)

            payload = json.loads((artifacts.run_dir / "results.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["results"][0]["seed"], 42)
            self.assertEqual(payload["summaries"][0]["mean_deliveries"], 3.0)


if __name__ == "__main__":
    unittest.main()
