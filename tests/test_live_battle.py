import json
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from metro_lab.config import ENGINE_SRC, WEB_ROOT
from metro_lab.live_battle import BattleRuntime
from metro_lab.planner import Decision
from metro_lab.scenarios import STRESS_SCENARIO_ID
from metro_lab.server import Handler, LabHTTPServer


class FakeEnv:
    def __init__(self, **kwargs):
        del kwargs
        # Two station passengers at 32 s and 16 s toward a 40 s timeout.
        # With threshold=2 the real pressure score is (0.8 + 0.4) / 2 = 60%.
        self.mediator = SimpleNamespace(
            overdue_passenger_threshold=2,
            passenger_max_wait_time_ms=40_000,
            stations=[
                SimpleNamespace(passengers=[SimpleNamespace(wait_ms=32_000)]),
                SimpleNamespace(passengers=[SimpleNamespace(wait_ms=16_000)]),
            ],
        )
        self.time = 0
        self.end_at = None

    def reset(self, seed):
        del seed
        return self.observation()

    def observation(self):
        return {"structured": {"time_ms": self.time, "deliveries": self.time // 100,
                "stations": [{"passenger_count": 1}, {"passenger_count": 1}], "is_game_over": False}}

    def observe(self):
        return self.observation()

    def step(self, action, dt_ms):
        ok = action["type"] == "noop"
        if ok:
            self.time += dt_ms
        return self.observation(), 0, self.time == self.end_at, {"action_ok": ok}


class FakePlanner:
    def reset(self, obs):
        del obs

    def act(self, obs):
        del obs
        return Decision({"type": "create_path"}, "test", "test")


CONFIG = dict(left="greedy-v1", right="balanced-greedy-v2", seed=314, dt_ms=100, budget_ms=300)


class LiveBattleTests(unittest.TestCase):
    def setUp(self):
        self.loader = patch("metro_lab.live_battle._load_engine", return_value=(FakeEnv, SimpleNamespace()))
        self.planner = patch("metro_lab.live_battle.create_planner", side_effect=lambda _: FakePlanner())
        self.configure_progression = patch("metro_lab.live_battle.configure_timed_station_progression")
        self.advance_progression = patch("metro_lab.live_battle.advance_timed_station_progression", return_value=False)
        self.progression_status = patch("metro_lab.live_battle.timed_station_status", return_value={
            "scenario_id": STRESS_SCENARIO_ID,
            "scenario_name": "Stress V1",
            "station_count": 2,
            "station_limit": 2,
            "station_spawn_interval_ms": 45_000,
            "next_station_at_ms": None,
            "next_station_in_ms": None,
        })
        self.loader.start()
        self.planner.start()
        self.configure_progression.start()
        self.advance_progression.start()
        self.progression_status.start()
        self.addCleanup(self.loader.stop)
        self.addCleanup(self.planner.stop)
        self.addCleanup(self.configure_progression.stop)
        self.addCleanup(self.advance_progression.stop)
        self.addCleanup(self.progression_status.stop)
        self.runtime = BattleRuntime()
        self.addCleanup(self.runtime.stop)

    def test_idle_and_restart_requires_session(self):
        self.assertEqual(self.runtime.snapshot()["status"], "idle")
        with self.assertRaises(ValueError):
            self.runtime.control("restart")

    def test_fixed_budget_risk_margin_and_restart(self):
        self.runtime.control("start", CONFIG)
        for _ in range(5):
            self.runtime.advance()
        state = self.runtime.snapshot()
        self.assertEqual((state["round"], state["elapsed_ms"], state["status"]), (3, 300, "finished"))
        self.assertEqual(state["left"]["runtime"]["risk"], 60)
        self.assertEqual(state["left"]["runtime"]["at_risk_passengers"], 1)
        self.assertEqual(state["left"]["runtime"]["overdue_passengers"], 0)
        self.assertEqual(state["left"]["runtime"]["max_wait_ms"], 32_000)
        self.assertEqual(state["left"]["progression"]["scenario_id"], STRESS_SCENARIO_ID)
        self.assertEqual(state["left"]["runtime"]["invalid_actions"], 3)
        self.assertEqual(state["leader"], "tie")
        self.runtime.control("restart")
        restarted = self.runtime.snapshot()
        self.assertEqual(restarted["config"], CONFIG)
        self.assertEqual(restarted["session_id"], state["session_id"] + 1)
        self.assertEqual(restarted["elapsed_ms"], 0)
        self.assertEqual(restarted["left"]["runtime"]["invalid_actions"], 0)

    def test_one_side_game_over_freezes_other_continues(self):
        self.runtime.control("start", CONFIG)
        self.runtime._sides[0]["env"].end_at = 100
        for _ in range(3):
            self.runtime.advance()
        state = self.runtime.snapshot()
        self.assertEqual(state["left"]["runtime"]["status"], "game_over")
        self.assertEqual(state["left"]["game"]["time_ms"], 100)
        self.assertEqual(state["right"]["game"]["time_ms"], 300)
        self.assertEqual((state["leader"], state["delivery_margin"]), ("right", 2))

    def test_both_game_over_ends_early(self):
        self.runtime.control("start", CONFIG)
        for side in self.runtime._sides:
            side["env"].end_at = 100
        self.runtime.advance()
        self.assertEqual(self.runtime.snapshot()["status"], "finished")

    def test_errors_stop_runtime(self):
        self.runtime.control("start", CONFIG)
        with patch.object(self.runtime._sides[1]["env"], "step", side_effect=RuntimeError("broken")):
            self.runtime.advance()
        self.assertEqual(self.runtime.snapshot()["status"], "error")
        self.assertIn("broken", self.runtime.snapshot()["error"])
        self.runtime.control("restart")
        self.assertIsNone(self.runtime.snapshot()["error"])

    def test_invalid_config_does_not_replace_session(self):
        self.runtime.control("start", CONFIG)
        before = self.runtime.snapshot()
        for value in [None, [], {**CONFIG, "left": "beam-search"}, {**CONFIG, "right": "missing"},
                      {**CONFIG, "seed": True}, {**CONFIG, "dt_ms": 0}, {**CONFIG, "dt_ms": 1.5},
                      {**CONFIG, "budget_ms": 301}, {**CONFIG, "budget_ms": float("inf")}]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.runtime.control("start", value)
            self.assertEqual(self.runtime.snapshot(), before)

    def test_snapshot_cannot_observe_half_round(self):
        self.runtime.control("start", CONFIG)
        entered, release, captured = threading.Event(), threading.Event(), threading.Event()
        original = self.runtime._sides[1]["env"].step

        def slow_step(*args, **kwargs):
            entered.set()
            release.wait(2)
            return original(*args, **kwargs)

        result = []

        def read():
            result.append(self.runtime.snapshot())
            captured.set()

        with patch.object(self.runtime._sides[1]["env"], "step", side_effect=slow_step):
            advance = threading.Thread(target=self.runtime.advance)
            advance.start()
            self.assertTrue(entered.wait(2))
            reader = threading.Thread(target=read)
            reader.start()
            try:
                self.assertFalse(captured.wait(.05))
            finally:
                release.set()
                advance.join(2)
                reader.join(2)
        self.assertEqual(result[0]["left"]["game"], result[0]["right"]["game"])


@unittest.skipUnless(ENGINE_SRC.exists(), "vendor engine not bootstrapped")
class LiveBattleEngineTests(unittest.TestCase):
    def test_real_engine_dynamic_stations_and_exact_self_play(self):
        for right in ("greedy-v1", "balanced-greedy-v2"):
            runtime = BattleRuntime()
            runtime.control("start", {**CONFIG, "right": right, "budget_ms": 60000})
            for _ in range(600):
                runtime.advance()
            state = runtime.snapshot()
            self.assertEqual(state["status"], "finished")
            self.assertEqual(state["left"]["game"]["time_ms"], 60000)
            self.assertEqual(state["right"]["game"]["time_ms"], 60000)
            self.assertEqual(state["left"]["progression"]["scenario_id"], STRESS_SCENARIO_ID)
            self.assertEqual(state["right"]["progression"]["scenario_id"], STRESS_SCENARIO_ID)
            self.assertEqual(state["left"]["progression"]["station_count"], 4)
            self.assertEqual(state["right"]["progression"]["station_count"], 4)
            for side in ("left", "right"):
                self.assertGreaterEqual(state[side]["runtime"]["risk"], 0)
                self.assertLessEqual(state[side]["runtime"]["risk"], 100)
                self.assertGreater(state[side]["runtime"]["passenger_max_wait_time_ms"], 0)
            left_stations = [(item["position"], item["shape_type"]) for item in state["left"]["game"]["stations"]]
            right_stations = [(item["position"], item["shape_type"]) for item in state["right"]["game"]["stations"]]
            self.assertEqual(left_stations, right_stations)
            if right == "greedy-v1":
                def canonical(game):
                    ids = {item["id"]: f"{kind}-{index}"
                           for kind in ("stations", "paths", "metros", "carriages", "passengers")
                           for index, item in enumerate(game.get(kind, []))}
                    def normalize(value):
                        if isinstance(value, dict):
                            return {ids.get(k, k): normalize(v) for k, v in value.items()}
                        if isinstance(value, list):
                            return [normalize(v) for v in value]
                        return ids.get(value, value) if isinstance(value, str) else value
                    return normalize(game)
                self.assertEqual(canonical(state["left"]["game"]), canonical(state["right"]["game"]))
                self.assertEqual(state["leader"], "tie")
                self.assertEqual(state["delivery_margin"], 0)
            json.dumps(state)

    def test_real_rejected_actions_still_spend_same_dt_and_budget(self):
        runtime = BattleRuntime()
        runtime.control("start", {**CONFIG, "budget_ms": 900000})
        for _ in range(9000):
            runtime.advance()
            state = runtime.snapshot()
            for side in ("left", "right"):
                if state[side]["runtime"]["status"] != "game_over":
                    self.assertEqual(state[side]["game"]["time_ms"], state["elapsed_ms"])
        self.assertEqual(state["status"], "finished")
        self.assertGreaterEqual(state["elapsed_ms"], 45_000)
        self.assertGreater(state["left"]["progression"]["station_count"], 3)
        self.assertGreater(state["right"]["progression"]["station_count"], 3)
        self.assertGreater(state["left"]["runtime"]["invalid_actions"], 0)
        self.assertGreater(state["right"]["runtime"]["invalid_actions"], 0)

    def test_http_live_battle_and_single_viewer(self):
        from metro_lab.engine import LabRuntime
        server = LabHTTPServer(("127.0.0.1", 0), Handler)
        server.runtime = LabRuntime(seed=42)
        server.battle = BattleRuntime()
        server.web_root = WEB_ROOT
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        base = f"http://127.0.0.1:{server.server_port}"

        def request(path, payload=None):
            data = json.dumps(payload).encode() if payload is not None else None
            return urlopen(Request(base + path, data=data, headers={"Content-Type": "application/json"}), timeout=5)

        try:
            before = json.load(request("/api/state"))
            self.assertEqual(json.load(request("/api/battle/state"))["status"], "idle")
            self.assertTrue(json.load(request("/api/battle/control", {"command": "start", "value": CONFIG}))["ok"])
            server.battle.advance()
            state = json.load(request("/api/battle/state"))
            self.assertEqual(state["round"], 1)
            self.assertEqual(state["left"]["game"]["time_ms"], state["right"]["game"]["time_ms"])
            self.assertEqual(state["left"]["progression"]["scenario_id"], STRESS_SCENARIO_ID)
            self.assertEqual(json.load(request("/api/state")), before)
            for body in ([], {"command": "start", "value": {}}, {"command": "bad"}):
                with self.assertRaises(HTTPError) as error:
                    request("/api/battle/control", body)
                self.assertEqual(error.exception.code, 400)
                self.assertFalse(json.load(error.exception)["ok"])
            self.assertTrue(json.load(request("/api/battle/control", {"command": "restart"}))["ok"])
            self.assertEqual(json.load(request("/api/battle/state"))["round"], 0)
            self.assertTrue(json.load(request("/api/control", {"command": "pause"}))["ok"])
            self.assertIn(b"leftCanvas", request("/battle.html").read())
            self.assertIn(b"metroCanvas", request("/").read())
        finally:
            server.shutdown()
            server.server_close()
            worker.join(2)
            server.battle.stop()
            server.runtime.stop()
