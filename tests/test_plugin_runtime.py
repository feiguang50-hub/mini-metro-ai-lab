from __future__ import annotations

import unittest

from metro_lab.algorithms import create_planner
from metro_lab.contract_greedy import ContractGreedyV1
from metro_lab.plugin_runtime import PluginPlannerAdapter


class PluginRuntimeTests(unittest.TestCase):
    def test_default_greedy_runs_through_contract_adapter(self) -> None:
        planner = create_planner("greedy-v1")

        self.assertIsInstance(planner, PluginPlannerAdapter)
        self.assertIsInstance(planner.plugin, ContractGreedyV1)

    def test_adapter_translates_semantic_decision_back_to_runtime_action(self) -> None:
        planner = create_planner("greedy-v1")
        observation = {
            "structured": {
                "time_ms": 0,
                "is_game_over": False,
                "deliveries": 0,
                "line_credits": 0,
                "stations": [
                    {
                        "id": "station-a",
                        "position": (0.0, 0.0),
                        "shape_type": "circle",
                        "passenger_count": 0,
                    },
                    {
                        "id": "station-b",
                        "position": (10.0, 0.0),
                        "shape_type": "triangle",
                        "passenger_count": 0,
                    },
                ],
                "paths": [],
                "metros": [],
                "fleet": {
                    "locomotives_available": 1,
                    "carriages_available": 0,
                },
            }
        }

        planner.reset(observation)
        decision = planner.act(observation)

        self.assertEqual(
            decision.action,
            {"type": "create_path", "stations": [0, 1], "loop": False},
        )
        self.assertEqual(decision.title, "建立第一条线路")


if __name__ == "__main__":
    unittest.main()
