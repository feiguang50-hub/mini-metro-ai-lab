import unittest

from metro_lab.config import ENGINE_SRC
from metro_lab.viewer_scenario import (
    STATION_SPAWN_INTERVAL_MS,
    advance_timed_station_progression,
    configure_timed_station_progression,
    timed_station_status,
)


@unittest.skipUnless(ENGINE_SRC.exists(), "vendor engine not bootstrapped")
class ViewerScenarioEngineTests(unittest.TestCase):
    def setUp(self):
        from metro_lab.engine import _load_engine

        Env, _ = _load_engine()
        self.env = Env(dt_ms=100, reward_mode="deliveries")
        self.env.reset(seed=42)
        configure_timed_station_progression(self.env)

    def test_station_pool_reveals_on_simulated_clock(self):
        self.assertEqual(len(self.env.mediator.stations), 3)
        self.env.mediator.time_ms = STATION_SPAWN_INTERVAL_MS - 1
        self.assertFalse(advance_timed_station_progression(self.env))
        self.assertEqual(len(self.env.mediator.stations), 3)

        self.env.mediator.time_ms += 1
        self.assertTrue(advance_timed_station_progression(self.env))
        self.assertEqual(len(self.env.mediator.stations), 4)
        self.assertEqual(timed_station_status(self.env)["next_station_in_ms"], STATION_SPAWN_INTERVAL_MS)

    def test_large_time_jump_reveals_every_due_station_and_stops_at_pool_limit(self):
        self.env.mediator.time_ms = STATION_SPAWN_INTERVAL_MS * 100
        self.assertTrue(advance_timed_station_progression(self.env))
        status = timed_station_status(self.env)
        self.assertEqual(status["station_count"], status["station_limit"])
        self.assertIsNone(status["next_station_at_ms"])
        self.assertIsNone(status["next_station_in_ms"])

    def test_delivery_milestones_no_longer_control_viewer_station_count(self):
        self.env.mediator._progression.deliveries = 10_000
        self.env.mediator.update_unlocked_num_stations()
        self.assertEqual(len(self.env.mediator.stations), 3)


if __name__ == "__main__":
    unittest.main()
