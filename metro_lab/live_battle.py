"""Atomic paired snapshots for browser battles; viewers never advance simulation."""
from __future__ import annotations

import threading
import time
from dataclasses import asdict
from typing import Any

from .algorithms import available_algorithm_ids, create_planner, get_algorithm_spec
from .config import ENGINE_COMMIT, TICK_MS
from .engine import _jsonable, _load_engine
from .planner import Decision


class BattleRuntime:
    def __init__(self):
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread = None
        self._session = 0
        self._config = None
        self._sides = []
        self._round = 0
        self._status = "idle"
        self._error = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._loop, daemon=True, name="mini-metro-battle")
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    @staticmethod
    def _validate(value):
        if not isinstance(value, dict):
            raise ValueError("battle configuration is required")
        available = available_algorithm_ids()
        for key in ("left", "right"):
            if value.get(key) not in available:
                raise ValueError(f"{key}: unknown or unavailable algorithm")
        config = {key: value[key] for key in ("left", "right")}
        for key, default, low, high in (
            ("seed", 42, 0, 2_147_483_647),
            ("dt_ms", TICK_MS, 10, 1000),
            ("budget_ms", 900_000, 100, 3_600_000),
        ):
            number = value.get(key, default)
            if type(number) is not int or not low <= number <= high:
                raise ValueError(f"{key} must be an integer in {low}..{high}")
            config[key] = number
        if config["budget_ms"] % config["dt_ms"]:
            raise ValueError("budget_ms must be a multiple of dt_ms")
        return config

    def control(self, command, value=None):
        with self._lock:
            if command == "start":
                config = self._validate(value)
            elif command == "restart":
                if self._config is None:
                    raise ValueError("no battle to restart")
                config = dict(self._config)
            else:
                raise ValueError(f"unknown battle command: {command}")
            Env, engine_config = _load_engine()
            # Build both environments before replacing a running session.
            sides = []
            for key in ("left", "right"):
                env = Env(dt_ms=config["dt_ms"], reward_mode="deliveries")
                obs = env.reset(seed=config["seed"])
                planner = create_planner(config[key])
                planner.reset(obs)
                sides.append(dict(env=env, obs=obs, planner=planner, done=False,
                                  invalid=0, action_ok=True,
                                  decision=Decision({"type": "noop"}, "新局开始", "同 Seed 同步对战")))
            self._engine_config = engine_config
            self._config, self._sides = config, sides
            self._round = 0
            self._session += 1
            self._status, self._error = "running", None
            return {"ok": True, "session_id": self._session}

    def advance(self):
        """One fixed-dt round under the same lock used to publish paired states."""
        with self._lock:
            if self._status != "running":
                return
            try:
                decisions = [side["planner"].act(side["obs"]) if not side["done"] else None
                             for side in self._sides]
                for side, decision in zip(self._sides, decisions):
                    if decision is None:
                        continue
                    obs, _, done, info = side["env"].step(decision.action, dt_ms=self._config["dt_ms"])
                    action_ok = bool(info.get("action_ok", False))
                    if not action_ok and not done:
                        # The pinned engine does not tick time on a rejected action.
                        # Spend this round as a noop so neither side gains extra time.
                        obs, _, done, _ = side["env"].step({"type": "noop"}, dt_ms=self._config["dt_ms"])
                    side.update(obs=obs, done=bool(done or obs["structured"].get("is_game_over")),
                                decision=decision, action_ok=action_ok)
                    if decision.action.get("type") != "noop" and not side["action_ok"]:
                        side["invalid"] += 1
                self._round += 1
                if (self._round * self._config["dt_ms"] >= self._config["budget_ms"]
                        or all(side["done"] for side in self._sides)):
                    self._status = "finished"
            except Exception as exc:
                # A partial round must never be presented as synchronized progress.
                self._status = "error"
                self._error = f"对战停止：{exc}"

    def _loop(self):
        while not self._stop.is_set():
            started = time.monotonic()
            self.advance()
            with self._lock:
                dt = self._config["dt_ms"] if self._config else TICK_MS
            self._stop.wait(max(.01, dt / 1000 - (time.monotonic() - started)))

    def snapshot(self):
        with self._lock:
            result = dict(session_id=self._session, status=self._status, error=self._error,
                          config=dict(self._config) if self._config else None, round=self._round,
                          elapsed_ms=self._round * self._config["dt_ms"] if self._config else 0)
            if not self._sides:
                return result
            for key, side in zip(("left", "right"), self._sides):
                game = _jsonable(side["obs"]["structured"])
                threshold = int(getattr(side["env"].mediator, "overdue_passenger_threshold", 10))
                waiting = max((int(s.get("passenger_count", 0)) for s in game.get("stations", [])), default=0)
                spec = get_algorithm_spec(self._config[key])
                result[key] = dict(
                    engine=dict(commit=ENGINE_COMMIT,
                                screen_width=int(getattr(self._engine_config, "screen_width", 1920)),
                                screen_height=int(getattr(self._engine_config, "screen_height", 1080))),
                    runtime=dict(algorithm_id=spec.id, algorithm=spec.name, algorithm_status=spec.status,
                                 seed=self._config["seed"], risk=min(100, round(waiting / max(1, threshold) * 100)),
                                 overdue_threshold=threshold, invalid_actions=side["invalid"],
                                 status="game_over" if side["done"] else self._status),
                    game=game, decision=_jsonable(asdict(side["decision"])))
            margin = result["left"]["game"].get("deliveries", 0) - result["right"]["game"].get("deliveries", 0)
            result.update(delivery_margin=abs(margin), leader="left" if margin > 0 else "right" if margin < 0 else "tie")
            return result
