import gzip
import json
import tempfile
import unittest
from pathlib import Path

from metro_lab.arena import EpisodeResult, run_episode, summarize
from metro_lab.config import ENGINE_SRC
from metro_lab.scenarios import CLASSIC_SCENARIO_ID, STRESS_SCENARIO_ID
from metro_lab.simulation import SIMULATION_PROTOCOL_VERSION


class ArenaPureTests(unittest.TestCase):
    def test_summary_ranks_by_mean_deliveries(self):
        results = [
            EpisodeResult(
                "a", 1, 10, 0, 1000, 10, False, 0,
                deliveries_per_minute=600.0,
                average_waiting_passengers=3.0,
                peak_network_waiting=5,
                peak_station_queue=4,
                average_fleet_load_pct=50.0,
                non_noop_actions=2,
            ),
            EpisodeResult(
                "a", 2, 20, 0, 1000, 10, False, 1,
                deliveries_per_minute=1200.0,
                average_waiting_passengers=5.0,
                peak_network_waiting=7,
                peak_station_queue=6,
                average_fleet_load_pct=70.0,
                non_noop_actions=3,
            ),
            EpisodeResult("b", 1, 8, 0, 1000, 10, True, 0),
            EpisodeResult("b", 2, 9, 0, 1000, 10, True, 0),
        ]
        summaries = summarize(results)
        self.assertEqual([item.algorithm for item in summaries], ["a", "b"])
        self.assertTrue(all(item.scenario == CLASSIC_SCENARIO_ID for item in summaries))
        self.assertEqual(summaries[0].mean_deliveries, 15.0)
        self.assertEqual(summaries[0].invalid_actions, 1)
        self.assertEqual(summaries[0].mean_waiting_passengers, 4.0)
        self.assertEqual(summaries[0].mean_peak_station_queue, 5.0)
        self.assertEqual(summaries[0].mean_fleet_load_pct, 60.0)
        self.assertEqual(summaries[0].invalid_action_rate, 0.2)
        self.assertEqual(summaries[1].game_over_rate, 1.0)

    def test_summary_does_not_mix_scenarios(self):
        results = [
            EpisodeResult("a", 1, 10, 0, 1000, 10, False, 0, scenario=CLASSIC_SCENARIO_ID),
            EpisodeResult("a", 1, 20, 0, 1000, 10, False, 0, scenario=STRESS_SCENARIO_ID),
        ]
        summaries = summarize(results)
        self.assertEqual(len(summaries), 2)
        self.assertEqual({item.scenario for item in summaries}, {CLASSIC_SCENARIO_ID, STRESS_SCENARIO_ID})


@unittest.skipUnless(ENGINE_SRC.exists(), "vendor engine not bootstrapped")
class ArenaEngineTests(unittest.TestCase):
    def test_short_episode_uses_real_engine(self):
        result = run_episode("greedy-v1", 42, minutes=0.02)
        self.assertEqual(result.algorithm, "greedy-v1")
        self.assertEqual(result.seed, 42)
        self.assertEqual(result.scenario, CLASSIC_SCENARIO_ID)
        self.assertEqual(result.protocol_version, SIMULATION_PROTOCOL_VERSION)
        self.assertEqual(result.simulated_ms, 1200)
        self.assertEqual(result.steps, 12)
        self.assertGreaterEqual(result.deliveries, 0)
        self.assertGreaterEqual(result.average_waiting_passengers, 0)
        self.assertGreaterEqual(result.peak_station_queue, 0)
        self.assertGreaterEqual(result.average_fleet_load_pct, 0)
        self.assertGreaterEqual(result.max_stations, 2)

    def test_stress_scenario_reveals_new_station_on_clock(self):
        result = run_episode(
            "greedy-v1",
            42,
            minutes=0.8,
            scenario=STRESS_SCENARIO_ID,
        )
        self.assertEqual(result.scenario, STRESS_SCENARIO_ID)
        self.assertGreaterEqual(result.max_stations, 4)
        self.assertGreater(result.simulated_ms, 45_000)

    def test_short_episode_records_replay(self):
        with tempfile.TemporaryDirectory() as temp:
            replay_path = Path(temp) / "greedy-v1--seed-42.jsonl.gz"
            run_episode(
                "greedy-v1",
                42,
                minutes=0.02,
                scenario=STRESS_SCENARIO_ID,
                replay_path=replay_path,
                replay_sample_ms=250,
            )
            self.assertTrue(replay_path.is_file())
            with gzip.open(replay_path, "rt", encoding="utf-8") as handle:
                rows = [json.loads(line) for line in handle]
            self.assertEqual(rows[0]["type"], "header")
            self.assertEqual(rows[0]["algorithm"], "greedy-v1")
            self.assertEqual(rows[0]["scenario"], STRESS_SCENARIO_ID)
            self.assertEqual(rows[0]["simulation_protocol"], SIMULATION_PROTOCOL_VERSION)
            self.assertTrue(any(row.get("type") == "frame" for row in rows[1:]))


if __name__ == "__main__":
    unittest.main()
