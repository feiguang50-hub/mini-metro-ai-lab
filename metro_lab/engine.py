from __future__ import annotations

import json
import random
import sys
import threading
import time
from collections import deque
from dataclasses import asdict
from enum import Enum
from typing import Any

from .algorithms import (
    DEFAULT_ALGORITHM_ID,
    algorithm_catalog,
    create_planner,
    get_algorithm_spec,
)
from .config import ENGINE_COMMIT, ENGINE_ROOT, ENGINE_SRC, TICK_MS
from .planner import Decision
from .viewer_scenario import (
    advance_timed_station_progression,
    configure_timed_station_progression,
    timed_station_status,
)


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Enum):
        return _jsonable(value.value)
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v) for v in value]
    if hasattr(value, "to_tuple"):
        return _jsonable(value.to_tuple())
    if hasattr(value, "value"):
        return _jsonable(value.value)
    return str(value)


def _load_engine():
    if not ENGINE_SRC.exists():
        raise RuntimeError(
            "Mini Metro 引擎尚未安装。请先运行 ./scripts/bootstrap.sh 或直接 ./run.sh。"
        )
    src = str(ENGINE_SRC)
    if src not in sys.path:
        sys.path.insert(0, src)
    from env import MiniMetroEnv  # type: ignore
    import config as engine_config  # type: ignore

    return MiniMetroEnv, engine_config


class LabRuntime:
    def __init__(self, seed: int = 42, algorithm_id: str = DEFAULT_ALGORITHM_ID) -> None:
        MiniMetroEnv, engine_config = _load_engine()
        self._MiniMetroEnv = MiniMetroEnv
        self._engine_config = engine_config
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._algorithm_id = get_algorithm_spec(algorithm_id).id
        self._planner = create_planner(self._algorithm_id)
        self._env = MiniMetroEnv(dt_ms=TICK_MS, reward_mode="deliveries")
        self._seed = int(seed)
        self._speed = 1
        self._paused = False
        self._observation: dict[str, Any] = {}
        self._last_decision = Decision({"type": "noop"}, "初始化", "正在建立模拟环境。")
        self._history: deque[dict[str, Any]] = deque(maxlen=12)
        self._action_ok = True
        self._reset_locked(self._seed)

    def _reset_locked(self, seed: int) -> None:
        self._seed = int(seed)
        self._planner = create_planner(self._algorithm_id)
        self._env = self._MiniMetroEnv(dt_ms=TICK_MS, reward_mode="deliveries")
        self._observation = self._env.reset(seed=self._seed)
        configure_timed_station_progression(self._env)
        self._observation = self._env.observe()
        self._planner.reset(self._observation)
        self._history.clear()
        spec = get_algorithm_spec(self._algorithm_id)
        self._last_decision = Decision(
            {"type": "noop"},
            "新局开始",
            f"{spec.name} · Seed {self._seed}",
        )
        self._action_ok = True
        self._paused = False

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._loop, name="mini-metro-lab", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def _record(self, decision: Decision, ok: bool, now_ms: int) -> None:
        if decision.action.get("type") == "noop":
            return
        self._history.appendleft(
            {
                "time_ms": now_ms,
                "title": decision.title,
                "detail": decision.detail,
                "action": decision.action.get("type"),
                "ok": bool(ok),
            }
        )

    def _loop(self) -> None:
        while not self._stop.is_set():
            started = time.monotonic()
            with self._lock:
                if not self._paused and not self._observation["structured"]["is_game_over"]:
                    decision = self._planner.act(self._observation)
                    self._last_decision = decision
                    dt = TICK_MS * self._speed
                    obs, _reward, _done, info = self._env.step(decision.action, dt_ms=dt)
                    if advance_timed_station_progression(self._env):
                        obs = self._env.observe()
                    self._observation = obs
                    self._action_ok = bool(info.get("action_ok", False))
                    self._record(decision, self._action_ok, int(obs["structured"]["time_ms"]))
            elapsed = time.monotonic() - started
            self._stop.wait(max(0.01, TICK_MS / 1000 - elapsed))

    def algorithm_library(self) -> list[dict[str, Any]]:
        return algorithm_catalog()

    def control(self, command: str, value: Any = None) -> dict[str, Any]:
        with self._lock:
            if command == "pause":
                self._paused = True
            elif command == "resume":
                self._paused = False
            elif command == "toggle_pause":
                self._paused = not self._paused
            elif command == "speed":
                speed = int(value)
                if speed not in {1, 2, 4}:
                    raise ValueError("speed must be 1, 2 or 4")
                self._speed = speed
            elif command == "restart":
                self._reset_locked(self._seed)
            elif command == "random_restart":
                self._reset_locked(random.randint(1, 2_147_483_647))
            elif command == "algorithm":
                if not isinstance(value, str):
                    raise ValueError("algorithm id is required")
                spec = get_algorithm_spec(value)
                if not spec.available:
                    raise ValueError(f"algorithm is not available yet: {value}")
                if spec.id != self._algorithm_id:
                    self._algorithm_id = spec.id
                    self._reset_locked(self._seed)
            else:
                raise ValueError(f"unknown command: {command}")
            return {"ok": True, "command": command, "algorithm_id": self._algorithm_id}

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            s = _jsonable(self._observation["structured"])
            stations = s.get("stations", [])
            threshold = int(getattr(self._env.mediator, "overdue_passenger_threshold", 10))
            max_waiting = max((int(st.get("passenger_count", 0)) for st in stations), default=0)
            risk = min(100, round(max_waiting / max(1, threshold) * 100))
            spec = get_algorithm_spec(self._algorithm_id)
            payload = {
                "engine": {
                    "commit": ENGINE_COMMIT,
                    "screen_width": int(getattr(self._engine_config, "screen_width", 1920)),
                    "screen_height": int(getattr(self._engine_config, "screen_height", 1080)),
                },
                "runtime": {
                    "seed": self._seed,
                    "speed": self._speed,
                    "paused": self._paused,
                    "algorithm_id": spec.id,
                    "algorithm": spec.name,
                    "algorithm_family": spec.family,
                    "algorithm_status": spec.status,
                    "algorithm_version": spec.version,
                    "action_ok": self._action_ok,
                    "risk": risk,
                    "overdue_threshold": threshold,
                    **timed_station_status(self._env),
                },
                "algorithms": self.algorithm_library(),
                "decision": _jsonable(asdict(self._last_decision)),
                "history": _jsonable(list(self._history)),
                "game": s,
            }
            json.dumps(payload, ensure_ascii=False)
            return payload
