from __future__ import annotations

import unittest

from metro_lab.engine import _load_engine
from metro_lab.lookahead_probe import generate_candidates, run_probe
from metro_lab.planner import Decision
from metro_lab.rollout import capture_rollout_snapshot, sample_future_keys
from metro_lab.scenarios import STRESS_SCENARIO_ID, configure_scenario


class LookaheadProbeTests(unittest.TestCase):
    def test_candidate_set_keeps_baseline_and_noop_without_duplicates(self):
        observation = {
            "structured": {
                "stations": [
                    {"id": "a", "position": (0, 0), "passenger_count": 3},
                    {"id": "b", "position": (100, 0), "passenger_count": 0},
                ],
                "paths": [
                    {"id": "p", "station_ids": ["a", "b"], "is_looped": False}
                ],
                "fleet": {
                    "locomotives_available": 1,
                    "carriages_available": 1,
                },
            }
        }
        baseline = Decision(
            {"type": "assign_locomotive", "path_index": 0},
            "baseline",
            "baseline",
        )
        actions = generate_candidates(observation, baseline, max_candidates=8)
        self.assertEqual(actions[0], baseline.action)
        self.assertIn({"type": "noop"}, actions)
        self.assertEqual(len(actions), len({repr(sorted(action.items())) for action in actions}))

    def test_probe_is_reproducible_on_real_pinned_engine(self):
        MiniMetroEnv, _config = _load_engine()
        env = MiniMetroEnv(dt_ms=100, reward_mode="deliveries")
        observation = env.reset(seed=42)
        configure_scenario(env, STRESS_SCENARIO_ID)
        observation = env.observe()
        snapshot = capture_rollout_snapshot(env)
        baseline = Decision({"type": "noop"}, "wait", "wait")
        keys = sample_future_keys(1234, 2)

        first = run_probe(
            snapshot,
            observation,
            baseline,
            future_keys=keys,
            scenario_id=STRESS_SCENARIO_ID,
            horizon_ms=500,
            max_candidates=4,
        )
        second = run_probe(
            snapshot,
            observation,
            baseline,
            future_keys=keys,
            scenario_id=STRESS_SCENARIO_ID,
            horizon_ms=500,
            max_candidates=4,
        )
        self.assertEqual(first, second)
        self.assertGreaterEqual(len(first.scores), 1)
        self.assertEqual(first.best.samples, 2)

    def test_probe_rejects_empty_future_set(self):
        MiniMetroEnv, _config = _load_engine()
        env = MiniMetroEnv(dt_ms=100, reward_mode="deliveries")
        observation = env.reset(seed=7)
        snapshot = capture_rollout_snapshot(env)
        with self.assertRaises(ValueError):
            run_probe(
                snapshot,
                observation,
                Decision({"type": "noop"}, "wait", "wait"),
                future_keys=(),
                scenario_id=STRESS_SCENARIO_ID,
                horizon_ms=500,
            )


if __name__ == "__main__":
    unittest.main()
