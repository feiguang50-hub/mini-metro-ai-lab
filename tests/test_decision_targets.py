import copy
import unittest
from collections import deque

from metro_lab.engine import LabRuntime, decision_targets
from metro_lab.planner import Decision


class DecisionTargetsTests(unittest.TestCase):
    def setUp(self):
        self.game = {
            "stations": [{"id": "station-a"}, {"id": "station-b"}, {"id": "station-c"}],
            "paths": [{"id": "path-original", "station_ids": ["station-a", "station-b"]}],
        }

    def test_route_indices_resolve_to_stable_ids_without_mutating_observation(self):
        before = copy.deepcopy(self.game)
        targets = decision_targets({"type": "create_path", "stations": [2, 0, 2]}, self.game)
        self.assertEqual(targets, {"station_ids": ["station-c", "station-a"], "path_ids": []})
        self.assertEqual(self.game, before)

    def test_path_resources_and_replacement_include_the_original_path(self):
        for kind in ("assign_locomotive", "attach_carriage", "replace_path"):
            with self.subTest(kind=kind):
                targets = decision_targets({"type": kind, "path_index": 0, "stations": [2, 0]}, self.game)
                self.assertEqual(targets, {"station_ids": ["station-c", "station-a", "station-b"], "path_ids": ["path-original"]})

    def test_invalid_indices_do_not_locate_a_different_station_or_crash_runtime(self):
        targets = decision_targets({"stations": [-1, True, 2.5, "0", 99], "path_index": -1}, self.game)
        self.assertEqual(targets, {"station_ids": [], "path_ids": []})
        self.assertEqual(decision_targets({"stations": "invalid", "path_index": True}, {}), targets)

    def test_history_retains_targets_when_current_path_order_changes(self):
        runtime = object.__new__(LabRuntime)
        runtime._history = deque(maxlen=12)
        action = {"type": "attach_carriage", "path_index": 0}
        targets = decision_targets(action, self.game)
        runtime._record(Decision(action, "增加车厢", "扩容"), True, 1200, targets)
        self.game["paths"].insert(0, {"id": "new-path", "station_ids": ["station-c"]})
        self.assertEqual(runtime._history[0]["targets"]["path_ids"], ["path-original"])
        self.assertEqual(runtime._history[0]["action"], "attach_carriage")

    def test_failed_actions_remain_labelled_and_noops_do_not_fill_history(self):
        runtime = object.__new__(LabRuntime)
        runtime._history = deque(maxlen=12)
        targets = decision_targets({"path_index": 0}, self.game)
        runtime._record(Decision({"type": "attach_carriage"}, "增加车厢", "扩容"), False, 100, targets)
        runtime._record(Decision({"type": "noop"}, "观察", "继续"), True, 200, targets)
        self.assertEqual(len(runtime._history), 1)
        self.assertFalse(runtime._history[0]["ok"])


if __name__ == "__main__":
    unittest.main()
