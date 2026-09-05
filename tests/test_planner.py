import unittest

from metro_lab.planner import GreedyPlanner


def observation(stations, paths=None, metros=None, available=2, carriages=0, time_ms=0):
    return {
        "structured": {
            "stations": stations,
            "paths": paths or [],
            "metros": metros or [],
            "fleet": {
                "locomotives_available": available,
                "carriages_available": carriages,
            },
            "time_ms": time_ms,
        }
    }


def st(sid, x, y, count=0):
    return {"id": sid, "position": (x, y), "shape_type": "circle", "passenger_count": count}


class PlannerTests(unittest.TestCase):
    def test_creates_initial_path(self):
        planner = GreedyPlanner()
        obs = observation([st("a", 0, 0), st("b", 10, 0), st("c", 30, 0)])
        planner.reset(obs)
        decision = planner.act(obs)
        self.assertEqual(decision.action["type"], "create_path")
        self.assertEqual(len(decision.action["stations"]), 3)

    def test_assigns_locomotive_to_empty_path(self):
        planner = GreedyPlanner()
        stations = [st("a", 0, 0), st("b", 10, 0)]
        paths = [{"id": "p", "station_ids": ["a", "b"], "is_looped": False}]
        obs = observation(stations, paths=paths, metros=[], available=1)
        decision = planner.act(obs)
        self.assertEqual(decision.action, {"type": "assign_locomotive", "path_index": 0})

    def test_inserts_unserved_station(self):
        planner = GreedyPlanner()
        stations = [st("a", 0, 0), st("b", 100, 0), st("c", 50, 10)]
        paths = [{"id": "p", "station_ids": ["a", "b"], "is_looped": False}]
        metros = [{"id": "m", "path_id": "p"}]
        obs = observation(stations, paths=paths, metros=metros, available=0, time_ms=2_000)
        decision = planner.act(obs)
        self.assertEqual(decision.action["type"], "replace_path")
        self.assertEqual(decision.action["stations"], [0, 2, 1])


if __name__ == "__main__":
    unittest.main()
