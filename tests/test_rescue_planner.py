import unittest

from metro_lab.algorithms import create_planner, get_algorithm_spec
from metro_lab.rescue_planner import BalancedGreedyV21Planner


def observation(
    *,
    time_ms=0,
    waiting=("p1",),
    locomotives_available=1,
    carriages_available=0,
):
    passenger_ids = list(waiting)
    return {
        "structured": {
            "time_ms": time_ms,
            "stations": [
                {
                    "id": "s0",
                    "position": (0, 0),
                    "shape_type": "CIRCLE",
                    "passenger_ids": passenger_ids,
                    "passenger_count": len(passenger_ids),
                },
                {
                    "id": "s1",
                    "position": (100, 0),
                    "shape_type": "TRIANGLE",
                    "passenger_ids": [],
                    "passenger_count": 0,
                },
            ],
            "paths": [
                {
                    "id": "line-0",
                    "station_ids": ["s0", "s1"],
                    "is_looped": False,
                    "color": (1, 2, 3),
                }
            ],
            "metros": [
                {
                    "id": "m0",
                    "path_id": "line-0",
                    "passenger_ids": [],
                    "capacity": 6,
                    "carriage_ids": [],
                }
            ],
            "fleet": {
                "locomotives_total": 4,
                "locomotives_assigned": 1,
                "locomotives_available": locomotives_available,
                "locomotives_queued": 0,
                "carriages_total": 2,
                "carriages_assigned": 0,
                "carriages_available": carriages_available,
            },
            "deliveries": 0,
            "line_credits": 0,
            "steps": time_ms // 100,
            "is_game_over": False,
        }
    }


class RescuePlannerTests(unittest.TestCase):
    def test_candidate_is_registered(self):
        spec = get_algorithm_spec("balanced-greedy-v2-1")
        self.assertTrue(spec.available)
        self.assertEqual(spec.status, "candidate")
        self.assertIsInstance(create_planner(spec.id), BalancedGreedyV21Planner)

    def test_single_line_absolute_pressure_can_add_locomotive(self):
        planner = BalancedGreedyV21Planner()
        obs = observation(waiting=("p1", "p2", "p3", "p4"))
        planner.reset(obs)
        decision = planner.act(obs)
        self.assertEqual(decision.action, {"type": "assign_locomotive", "path_index": 0})

    def test_wait_age_triggers_rescue_before_engine_deadline(self):
        planner = BalancedGreedyV21Planner()
        planner.reset(observation(time_ms=0, waiting=("old",)))
        decision = planner.act(observation(time_ms=30_000, waiting=("old",)))
        self.assertEqual(decision.action["type"], "assign_locomotive")
        self.assertIn("30.0s", decision.detail)

    def test_passenger_returning_to_station_starts_new_wait_episode(self):
        planner = BalancedGreedyV21Planner()
        planner.reset(observation(time_ms=0, waiting=("p",)))
        planner.act(observation(time_ms=20_000, waiting=()))
        decision = planner.act(observation(time_ms=31_000, waiting=("p",)))
        self.assertEqual(decision.action["type"], "noop")

    def test_capacity_first_away_from_critical_deadline(self):
        planner = BalancedGreedyV21Planner()
        obs = observation(
            waiting=("p1", "p2", "p3", "p4", "p5", "p6"),
            locomotives_available=1,
            carriages_available=1,
        )
        planner.reset(obs)
        decision = planner.act(obs)
        self.assertEqual(decision.action, {"type": "attach_carriage", "path_index": 0})

    def test_reset_clears_wait_history(self):
        planner = BalancedGreedyV21Planner()
        planner.reset(observation(time_ms=0, waiting=("p",)))
        planner.act(observation(time_ms=29_000, waiting=("p",)))
        planner.reset(observation(time_ms=29_000, waiting=("p",)))
        decision = planner.act(observation(time_ms=30_000, waiting=("p",)))
        self.assertEqual(decision.action["type"], "noop")


if __name__ == "__main__":
    unittest.main()
