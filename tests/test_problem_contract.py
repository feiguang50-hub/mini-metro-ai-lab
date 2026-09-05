from __future__ import annotations

import copy
import unittest

from metro_lab.problem import PROBLEM_CONTRACT_VERSION, PROBLEM_ID, state_from_observation


def _observation() -> dict:
    return {
        "structured": {
            "time_ms": 12_500,
            "is_game_over": False,
            "deliveries": 7,
            "line_credits": 2,
            "unlocked_num_paths": 3,
            "stations": [
                {
                    "id": "s0",
                    "position": (100, 200),
                    "shape_type": "circle",
                    "passenger_count": 4,
                },
                {
                    "id": "s1",
                    "position": [300.5, 400.25],
                    "shape_type": "triangle",
                    "passenger_count": 1,
                },
            ],
            "paths": [
                {"id": "p0", "station_ids": ["s0", "s1"], "loop": False}
            ],
            "metros": [{"id": "m0", "path_id": "p0"}],
            "fleet": {"locomotives_available": 2, "carriages_available": 1},
        }
    }


class ProblemContractTests(unittest.TestCase):
    def test_projects_public_observation_without_mutation(self) -> None:
        observation = _observation()
        before = copy.deepcopy(observation)

        state = state_from_observation(observation)

        self.assertEqual(observation, before)
        self.assertEqual(state.problem_id, PROBLEM_ID)
        self.assertEqual(state.contract_version, PROBLEM_CONTRACT_VERSION)
        self.assertEqual(state.time_ms, 12_500)
        self.assertEqual(state.deliveries, 7)
        self.assertEqual(state.line_credits, 2)
        self.assertEqual(state.unlocked_line_count, 3)
        self.assertEqual(state.stations[0].x, 100.0)
        self.assertEqual(state.stations[1].y, 400.25)
        self.assertEqual(state.lines[0].station_ids, ("s0", "s1"))
        self.assertEqual(state.vehicles[0].path_id, "p0")
        self.assertEqual(state.fleet.locomotives_available, 2)
        self.assertEqual(state.served_station_ids, frozenset({"s0", "s1"}))
        self.assertEqual(state.station_by_id["s1"].shape, "triangle")

    def test_marks_missing_line_visibility_as_unknown(self) -> None:
        observation = _observation()
        observation["structured"].pop("unlocked_num_paths")

        state = state_from_observation(observation)

        self.assertIsNone(state.unlocked_line_count)

    def test_rejects_malformed_station_position(self) -> None:
        observation = _observation()
        observation["structured"]["stations"][0]["position"] = [1]

        with self.assertRaisesRegex(ValueError, "invalid position"):
            state_from_observation(observation)


if __name__ == "__main__":
    unittest.main()
