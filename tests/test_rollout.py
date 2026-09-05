import copy
import unittest

from metro_lab.engine import _load_engine
from metro_lab.rollout import (
    _restore_exact_for_test,
    capture_rollout_snapshot,
    restore_sampled_future,
    sample_future_keys,
)


class SafeRolloutTests(unittest.TestCase):
    def _env(self, seed=123):
        MiniMetroEnv, _engine_config = _load_engine()
        env = MiniMetroEnv(dt_ms=100, reward_mode="deliveries")
        env.reset(seed=seed)
        for _ in range(25):
            env.step({"type": "noop"}, dt_ms=100)
        return env

    def test_exact_restore_is_a_snapshot_fidelity_test_only(self):
        env = self._env()
        snapshot = capture_rollout_snapshot(env)
        restored = _restore_exact_for_test(snapshot)
        self.assertEqual(restored.observe()["structured"], env.observe()["structured"])
        self.assertEqual(restored.mediator.time_ms, snapshot.source_time_ms)

    def test_sampled_future_keeps_visible_board_but_replaces_hidden_rng(self):
        env = self._env()
        snapshot = capture_rollout_snapshot(env)
        original_rng = copy.deepcopy(snapshot.document["rng"])

        sampled = restore_sampled_future(snapshot, 987654)

        self.assertEqual(sampled.observe()["structured"], env.observe()["structured"])
        self.assertEqual(snapshot.document["rng"], original_rng)

    def test_same_future_key_replays_same_sampled_future(self):
        snapshot = capture_rollout_snapshot(self._env())
        left = restore_sampled_future(snapshot, 424242)
        right = restore_sampled_future(snapshot, 424242)

        left_trace = []
        right_trace = []
        for _ in range(250):
            l_obs, l_reward, l_done, _ = left.step({"type": "noop"}, dt_ms=100)
            r_obs, r_reward, r_done, _ = right.step({"type": "noop"}, dt_ms=100)
            left_trace.append((l_reward, l_done, l_obs["structured"]))
            right_trace.append((r_reward, r_done, r_obs["structured"]))
            if l_done or r_done:
                break

        self.assertEqual(left_trace, right_trace)

    def test_future_keys_are_deterministic_and_positive_count_is_required(self):
        first = sample_future_keys(20260905, 4)
        second = sample_future_keys(20260905, 4)
        self.assertEqual(first, second)
        self.assertEqual(len(first), 4)
        with self.assertRaises(ValueError):
            sample_future_keys(20260905, 0)


if __name__ == "__main__":
    unittest.main()
