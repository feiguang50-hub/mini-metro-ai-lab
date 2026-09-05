import unittest

from metro_lab.algorithms import create_planner, get_algorithm_spec
from metro_lab.relayout_planner import BalancedGreedyV22Planner


def observation(*, positions=None):
    if positions is None:
        # Deliberately tangled enough that the full 2-opt target saves >20%.
        positions = [(0, 0), (100, 100), (0, 100), (100, 0), (100, 10)]
    shapes = ["CIRCLE", "TRIANGLE", "SQUARE", "CIRCLE", "TRIANGLE"]
    stations = [
        {
            "id": f"s{idx}",
            "position": position,
            "shape_type": shapes[idx],
            "passenger_ids": [],
            "passenger_count": 0,
        }
        for idx, position in enumerate(positions)
    ]
    return {
        "structured": {
            "time_ms": 10_000,
            "stations": stations,
            "paths": [
                {
                    "id": "line-0",
                    "station_ids": ["s0", "s1", "s2", "s3", "s4"],
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
                "locomotives_total": 1,
                "locomotives_assigned": 1,
                "locomotives_available": 0,
                "locomotives_queued": 0,
                "carriages_total": 0,
                "carriages_assigned": 0,
                "carriages_available": 0,
            },
            "deliveries": 0,
            "line_credits": 0,
            "steps": 100,
            "is_game_over": False,
        }
    }


class RelayoutPlannerTests(unittest.TestCase):
    def test_candidate_is_registered(self):
        spec = get_algorithm_spec("balanced-greedy-v2-2")
        self.assertTrue(spec.available)
        self.assertEqual(spec.status, "candidate")
        self.assertIsInstance(create_planner(spec.id), BalancedGreedyV22Planner)

    def test_full_two_opt_reaches_local_target_and_anchors_first_station(self):
        obs = observation()
        state = obs["structured"]
        station_by_id = {station["id"]: station for station in state["stations"]}
        candidate = BalancedGreedyV22Planner._two_opt_target(
            state["paths"][0], station_by_id
        )
        self.assertIsNotNone(candidate)
        saving_ratio, improvement, route = candidate
        self.assertGreater(saving_ratio, 0.20)
        self.assertGreater(improvement, 90.0)
        self.assertEqual(route[0], "s0")
        self.assertEqual(set(route), {"s0", "s1", "s2", "s3", "s4"})
        self.assertEqual(route, ["s0", "s2", "s1", "s4", "s3"])

    def test_looped_path_is_not_relaid_out_by_open_line_operator(self):
        obs = observation()
        state = obs["structured"]
        state["paths"][0]["is_looped"] = True
        station_by_id = {station["id"]: station for station in state["stations"]}
        self.assertIsNone(
            BalancedGreedyV22Planner._two_opt_target(
                state["paths"][0], station_by_id
            )
        )

    def test_subthreshold_improvement_is_not_submitted(self):
        obs = observation(
            positions=[(0, 0), (10, 10), (0, 10), (10, 0), (20, 0)]
        )
        planner = BalancedGreedyV22Planner()
        planner.reset(obs)
        target = planner._two_opt_target(
            obs["structured"]["paths"][0],
            {station["id"]: station for station in obs["structured"]["stations"]},
        )
        self.assertIsNotNone(target)
        self.assertLess(target[0], planner.MIN_SAVING_RATIO)
        self.assertEqual(planner.act(obs).action["type"], "noop")

    def test_act_emits_one_atomic_replace_for_over_threshold_target(self):
        obs = observation()
        planner = BalancedGreedyV22Planner()
        planner.reset(obs)
        decision = planner.act(obs)
        self.assertEqual(decision.action["type"], "replace_path")
        self.assertEqual(decision.action["path_index"], 0)
        self.assertEqual(decision.action["stations"], [0, 2, 1, 4, 3])
        self.assertGreater(decision.action["_lab_saving_ratio"], 0.20)
        self.assertIn("2-opt", decision.title)

    def test_same_rejected_candidate_is_not_hammered_every_tick(self):
        obs = observation()
        planner = BalancedGreedyV22Planner()
        planner.reset(obs)
        first = planner.act(obs)
        second = planner.act(obs)
        self.assertEqual(first.action["type"], "replace_path")
        self.assertEqual(second.action["type"], "noop")


if __name__ == "__main__":
    unittest.main()
