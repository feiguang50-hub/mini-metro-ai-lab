import unittest

from metro_lab.simulation import SIMULATION_PROTOCOL_VERSION, advance_fixed_dt


class FakeEnv:
    def __init__(self):
        self.time_ms = 0

    def _obs(self):
        return {"structured": {"time_ms": self.time_ms}}

    def step(self, action, dt_ms=None):
        action_type = action.get("type")
        if action_type == "reject":
            return self._obs(), 0, False, {"action_ok": False}
        if action_type == "stuck":
            return self._obs(), 0, False, {"action_ok": True}
        self.time_ms += int(dt_ms or 0)
        return self._obs(), 0, False, {"action_ok": True}


class SimulationProtocolTests(unittest.TestCase):
    def test_protocol_version_is_v2(self):
        self.assertEqual(SIMULATION_PROTOCOL_VERSION, 2)

    def test_rejected_action_spends_round_as_noop(self):
        env = FakeEnv()
        before = env._obs()
        outcome = advance_fixed_dt(env, before, {"type": "reject"}, dt_ms=100)
        self.assertFalse(outcome.action_ok)
        self.assertTrue(outcome.fallback_used)
        self.assertEqual(outcome.elapsed_ms, 100)
        self.assertEqual(outcome.observation["structured"]["time_ms"], 100)

    def test_valid_action_uses_no_fallback(self):
        env = FakeEnv()
        outcome = advance_fixed_dt(env, env._obs(), {"type": "noop"}, dt_ms=100)
        self.assertTrue(outcome.action_ok)
        self.assertFalse(outcome.fallback_used)
        self.assertEqual(outcome.elapsed_ms, 100)

    def test_protocol_rejects_valid_action_that_does_not_tick(self):
        env = FakeEnv()
        with self.assertRaises(RuntimeError):
            advance_fixed_dt(env, env._obs(), {"type": "stuck"}, dt_ms=100)


if __name__ == "__main__":
    unittest.main()
