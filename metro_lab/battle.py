from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .algorithms import DEFAULT_ALGORITHM_ID, available_algorithm_ids, create_planner
from .config import ENGINE_COMMIT, ROOT, TICK_MS
from .engine import _jsonable, _load_engine
from .experiments import ReplayWriter
from .planner import Decision
from .simulation import SIMULATION_PROTOCOL_VERSION, advance_fixed_dt

DEFAULT_BATTLE_ROOT = ROOT / "output" / "battles"


@dataclass(frozen=True)
class BattleSideResult:
    algorithm: str
    seed: int
    deliveries: int
    line_credits: int
    simulated_ms: int
    steps: int
    game_over: bool
    invalid_actions: int


@dataclass(frozen=True)
class BattleResult:
    seed: int
    left: BattleSideResult
    right: BattleSideResult
    winner: str
    delivery_margin: int


def _side_result(algorithm: str, seed: int, observation: dict[str, Any], done: bool, invalid_actions: int) -> BattleSideResult:
    structured = observation["structured"]
    return BattleSideResult(
        algorithm=algorithm,
        seed=int(seed),
        deliveries=int(structured.get("deliveries", 0)),
        line_credits=int(structured.get("line_credits", 0)),
        simulated_ms=int(structured.get("time_ms", 0)),
        steps=int(structured.get("steps", 0)),
        game_over=bool(structured.get("is_game_over", done)),
        invalid_actions=int(invalid_actions),
    )


def _record(recorder: ReplayWriter | None, observation: dict[str, Any], decision: Decision, action_ok: bool, kind: str) -> None:
    if recorder is None:
        return
    game = _jsonable(observation["structured"])
    recorder.write_frame(
        time_ms=int(game.get("time_ms", 0)),
        game=game,
        decision=_jsonable(asdict(decision)),
        action_ok=bool(action_ok),
        kind=kind,
    )


def run_battle(
    left_algorithm: str,
    right_algorithm: str,
    seed: int,
    *,
    minutes: float = 15.0,
    dt_ms: int = TICK_MS,
    left_replay: Path | None = None,
    right_replay: Path | None = None,
    replay_sample_ms: int = 1_000,
) -> BattleResult:
    available = set(available_algorithm_ids())
    for algorithm in (left_algorithm, right_algorithm):
        if algorithm not in available:
            raise ValueError(f"unknown or unavailable algorithm: {algorithm}")
    if minutes <= 0:
        raise ValueError("minutes must be positive")
    if dt_ms <= 0:
        raise ValueError("dt_ms must be positive")
    if replay_sample_ms <= 0:
        raise ValueError("replay_sample_ms must be positive")

    MiniMetroEnv, _engine_config = _load_engine()
    left_env = MiniMetroEnv(dt_ms=dt_ms, reward_mode="deliveries")
    right_env = MiniMetroEnv(dt_ms=dt_ms, reward_mode="deliveries")
    left_obs = left_env.reset(seed=int(seed))
    right_obs = right_env.reset(seed=int(seed))
    left_planner = create_planner(left_algorithm)
    right_planner = create_planner(right_algorithm)
    left_planner.reset(left_obs)
    right_planner.reset(right_obs)

    left_done = False
    right_done = False
    left_invalid = 0
    right_invalid = 0
    max_steps = max(1, int(minutes * 60_000 / dt_ms))
    next_sample_ms = replay_sample_ms

    left_writer = ReplayWriter(left_replay, {
        "mode": "battle",
        "side": "left",
        "opponent": right_algorithm,
        "algorithm": left_algorithm,
        "seed": int(seed),
        "dt_ms": int(dt_ms),
        "minutes": float(minutes),
        "sample_every_ms": int(replay_sample_ms),
        "simulation_protocol": SIMULATION_PROTOCOL_VERSION,
    }).start() if left_replay is not None else None
    right_writer = ReplayWriter(right_replay, {
        "mode": "battle",
        "side": "right",
        "opponent": left_algorithm,
        "algorithm": right_algorithm,
        "seed": int(seed),
        "dt_ms": int(dt_ms),
        "minutes": float(minutes),
        "sample_every_ms": int(replay_sample_ms),
        "simulation_protocol": SIMULATION_PROTOCOL_VERSION,
    }).start() if right_replay is not None else None

    start_decision = Decision({"type": "noop"}, "Battle start", f"Seed {int(seed)}")
    _record(left_writer, left_obs, start_decision, True, "start")
    _record(right_writer, right_obs, start_decision, True, "start")

    try:
        for _ in range(max_steps):
            left_decision = left_planner.act(left_obs) if not left_done else Decision({"type": "noop"}, "已结束", "左侧已停止推进。")
            right_decision = right_planner.act(right_obs) if not right_done else Decision({"type": "noop"}, "已结束", "右侧已停止推进。")

            left_ok = True
            right_ok = True
            if not left_done:
                outcome = advance_fixed_dt(left_env, left_obs, left_decision.action, dt_ms=dt_ms)
                left_obs, left_done, left_ok = outcome.observation, outcome.done, outcome.action_ok
                if left_decision.action.get("type") != "noop" and not left_ok:
                    left_invalid += 1
            if not right_done:
                outcome = advance_fixed_dt(right_env, right_obs, right_decision.action, dt_ms=dt_ms)
                right_obs, right_done, right_ok = outcome.observation, outcome.done, outcome.action_ok
                if right_decision.action.get("type") != "noop" and not right_ok:
                    right_invalid += 1

            now_ms = max(
                int(left_obs["structured"].get("time_ms", 0)),
                int(right_obs["structured"].get("time_ms", 0)),
            )
            sampled = now_ms >= next_sample_ms
            left_significant = left_decision.action.get("type") != "noop"
            right_significant = right_decision.action.get("type") != "noop"
            if sampled or left_significant or left_done:
                _record(left_writer, left_obs, left_decision, left_ok, "decision" if left_significant else "end" if left_done else "sample")
            if sampled or right_significant or right_done:
                _record(right_writer, right_obs, right_decision, right_ok, "decision" if right_significant else "end" if right_done else "sample")
            while now_ms >= next_sample_ms:
                next_sample_ms += replay_sample_ms

            if left_done and right_done:
                break
    finally:
        if left_writer is not None:
            left_writer.close()
        if right_writer is not None:
            right_writer.close()

    left = _side_result(left_algorithm, seed, left_obs, left_done, left_invalid)
    right = _side_result(right_algorithm, seed, right_obs, right_done, right_invalid)
    margin = left.deliveries - right.deliveries
    winner = "left" if margin > 0 else "right" if margin < 0 else "tie"
    return BattleResult(seed=int(seed), left=left, right=right, winner=winner, delivery_margin=abs(margin))


def save_battle(result: BattleResult, *, output_root: Path, minutes: float, dt_ms: int) -> Path:
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = output_root / f"{timestamp}-{result.left.algorithm}-vs-{result.right.algorithm}-seed-{result.seed}"
    suffix = 2
    base = run_dir
    while run_dir.exists():
        run_dir = Path(f"{base}-{suffix:02d}")
        suffix += 1
    run_dir.mkdir(parents=True)
    payload = {
        "schema_version": 1,
        "simulation_protocol": SIMULATION_PROTOCOL_VERSION,
        "engine_commit": ENGINE_COMMIT,
        "minutes": float(minutes),
        "dt_ms": int(dt_ms),
        "result": asdict(result),
    }
    (run_dir / "battle.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return run_dir


def _parser() -> argparse.ArgumentParser:
    available = available_algorithm_ids()
    parser = argparse.ArgumentParser(description="Mini Metro AI Lab 同 Seed 同步对战")
    parser.add_argument("left", nargs="?", default=DEFAULT_ALGORITHM_ID, choices=available)
    parser.add_argument("right", nargs="?", default=DEFAULT_ALGORITHM_ID, choices=available)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--minutes", type=float, default=15.0)
    parser.add_argument("--dt-ms", type=int, default=TICK_MS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_BATTLE_ROOT)
    parser.add_argument("--no-save", action="store_true")
    parser.add_argument("--replays", action="store_true", help="保存双方完整采样回放")
    parser.add_argument("--replay-sample-ms", type=int, default=1_000)
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> None:
    args = _parser().parse_args()
    replay_dir = None
    left_replay = right_replay = None
    if args.replays and not args.no_save:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        replay_dir = Path(args.output_dir) / f"{timestamp}-replays"
        left_replay = replay_dir / f"left-{args.left}-seed-{args.seed}.jsonl.gz"
        right_replay = replay_dir / f"right-{args.right}-seed-{args.seed}.jsonl.gz"

    result = run_battle(
        args.left,
        args.right,
        args.seed,
        minutes=args.minutes,
        dt_ms=args.dt_ms,
        left_replay=left_replay,
        right_replay=right_replay,
        replay_sample_ms=args.replay_sample_ms,
    )
    run_dir = None if args.no_save else save_battle(result, output_root=args.output_dir, minutes=args.minutes, dt_ms=args.dt_ms)

    if args.json:
        print(json.dumps({
            "engine_commit": ENGINE_COMMIT,
            "simulation_protocol": SIMULATION_PROTOCOL_VERSION,
            "run_dir": str(run_dir) if run_dir else None,
            "result": asdict(result),
        }, ensure_ascii=False, indent=2))
        return

    print("\n🏁 Mini Metro AI Battle · Protocol V2")
    print("=" * 64)
    print(f"Seed {result.seed} · {result.left.algorithm} vs {result.right.algorithm}")
    print(f"左侧：{result.left.deliveries} deliveries · {'Game Over' if result.left.game_over else 'alive'}")
    print(f"右侧：{result.right.deliveries} deliveries · {'Game Over' if result.right.game_over else 'alive'}")
    if result.winner == "tie":
        print("结果：平局")
    else:
        winner = result.left.algorithm if result.winner == "left" else result.right.algorithm
        print(f"胜者：{winner} · 领先 {result.delivery_margin}")
    if run_dir is not None:
        print(f"记录：{run_dir}")


if __name__ == "__main__":
    main()
