import unittest

from metro_lab.algorithms import available_algorithm_ids, create_planner, get_algorithm_spec
from metro_lab.balanced_planner import BalancedGreedyPlanner
from metro_lab.battle import run_battle
from metro_lab.config import ENGINE_SRC


class BalancedPlannerPureTests(unittest.TestCase):
    def test_candidate_is_registered_and_available(self):
        self.assertIn("balanced-greedy-v2", available_algorithm_ids())
        self.assertEqual(get_algorithm_spec("balanced-greedy-v2").status, "candidate")
        self.assertIsInstance(create_planner("balanced-greedy-v2"), BalancedGreedyPlanner)

    def test_initial_route_prefers_shape_diversity(self):
        planner = BalancedGreedyPlanner()
        stations = [
            {"id": "a", "shape_type": "circle", "position": [0, 0]},
            {"id": "b", "shape_type": "circle", "position": [1, 0]},
            {"id": "c", "shape_type": "triangle", "position": [20, 0]},
            {"id": "d", "shape_type": "square", "position": [40, 0]},
        ]
        route = planner._initial_route(stations)
        shapes = {stations[idx]["shape_type"] for idx in route}
        self.assertEqual(len(route), 3)
        self.assertEqual(len(shapes), 3)


@unittest.skipUnless(ENGINE_SRC.exists(), "vendor engine not bootstrapped")
class BalancedPlannerEngineTests(unittest.TestCase):
    def test_candidate_runs_in_real_battle_engine(self):
        result = run_battle("greedy-v1", "balanced-greedy-v2", 42, minutes=0.05)
        self.assertEqual(result.left.algorithm, "greedy-v1")
        self.assertEqual(result.right.algorithm, "balanced-greedy-v2")
        self.assertGreater(result.left.steps, 0)
        self.assertGreater(result.right.steps, 0)
        self.assertGreaterEqual(result.left.deliveries, 0)
        self.assertGreaterEqual(result.right.deliveries, 0)


if __name__ == "__main__":
    unittest.main()
