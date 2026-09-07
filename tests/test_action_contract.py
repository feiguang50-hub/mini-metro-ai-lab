from __future__ import annotations

import unittest

from metro_lab.action import (
    ActionTranslationError,
    AssignLocomotiveAction,
    AttachCarriageAction,
    CreateLineAction,
    NoOpAction,
    ReplaceLineAction,
    to_backend_action,
)
from metro_lab.problem import (
    FleetState,
    LineState,
    MetroPlanningState,
    PROBLEM_CONTRACT_VERSION,
    PROBLEM_ID,
    StationState,
)


class ActionContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.state = MetroPlanningState(
            problem_id=PROBLEM_ID,
            contract_version=PROBLEM_CONTRACT_VERSION,
            time_ms=1200,
            is_terminal=False,
            deliveries=4,
            line_credits=0,
            unlocked_line_count=None,
            stations=(
                StationState("station-a", 91, 10.0, 20.0, "circle", 0),
                StationState("station-b", 17, 30.0, 40.0, "triangle", 2),
                StationState("station-c", 3, 50.0, 60.0, "square", 1),
            ),
            lines=(
                LineState("line-red", 44, ("station-a", "station-b"), False),
            ),
            vehicles=(),
            fleet=FleetState(locomotives_available=1, carriages_available=1),
        )

    def test_semantic_ids_translate_at_backend_edge(self) -> None:
        self.assertEqual(
            to_backend_action(
                self.state,
                CreateLineAction(("station-c", "station-a")),
            ),
            {"type": "create_path", "stations": [2, 0], "loop": False},
        )
        self.assertEqual(
            to_backend_action(
                self.state,
                ReplaceLineAction(
                    "line-red",
                    ("station-a", "station-c", "station-b"),
                ),
            ),
            {
                "type": "replace_path",
                "path_index": 0,
                "stations": [0, 2, 1],
                "loop": False,
            },
        )
        self.assertEqual(
            to_backend_action(self.state, AssignLocomotiveAction("line-red")),
            {"type": "assign_locomotive", "path_index": 0},
        )
        self.assertEqual(
            to_backend_action(self.state, AttachCarriageAction("line-red")),
            {"type": "attach_carriage", "path_index": 0},
        )
        self.assertEqual(to_backend_action(self.state, NoOpAction()), {"type": "noop"})

    def test_translation_ignores_backend_index_fields_in_problem_objects(self) -> None:
        # The deliberately strange StationState.index / LineState.index values in
        # setUp must not leak into backend actions. Translation uses current
        # collection order at the adapter edge, not algorithm-visible indices.
        action = ReplaceLineAction(
            "line-red",
            ("station-b", "station-a"),
        )
        self.assertEqual(
            to_backend_action(self.state, action),
            {
                "type": "replace_path",
                "path_index": 0,
                "stations": [1, 0],
                "loop": False,
            },
        )

    def test_unknown_semantic_references_fail_before_backend_call(self) -> None:
        with self.assertRaisesRegex(ActionTranslationError, "unknown line id"):
            to_backend_action(self.state, AssignLocomotiveAction("missing-line"))

        with self.assertRaisesRegex(ActionTranslationError, "unknown station id"):
            to_backend_action(
                self.state,
                CreateLineAction(("station-a", "missing-station")),
            )


if __name__ == "__main__":
    unittest.main()
