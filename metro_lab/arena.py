from __future__ import annotations

import argparse
import json
import statistics
from dataclasses import asdict, dataclass
from pathlib import Path

from .algorithms import DEFAULT_ALGORITHM_ID, available_algorithm_ids, create_planner
from .config import ENGINE_COMMIT, TICK_MS
from .engine import _jsonable, _load_engine
from .experiments import DEFAULT_EXPERIMENT_ROOT, ExperimentArtifacts, ReplayWriter


@dataclass(frozen=True)
class EpisodeResult:
    algorithm: str
    seed: int
    deliveries: int
    line_credits: int
    simulated_ms: int
    steps: int
    game_over: bool
    invalid_actions: int


@dataclass(frozen=True)
class AlgorithmSummary:
    algorithm: str
    episodes: int
    mean_deliveries: float
    median_deliveries: float
    min_deliveries: int
    max_deliveries: int
    game_over_rate: float
    invalid_actions: int


def _record_frame(
    recorder: ReplayWriter,
    observation: dict,
    decision,
    *,
    action_ok: bool,
    kind: str,
) -> None:
    structured = _jsonable(observation["structured"])
    recorder.write_frame(
        time_ms=int(structured.get("time_ms", 0)),
        game=structured,
        decision=_jsonable(asdict(decision)),
        action_ok=action_ok,
        kind=kind,
    )


def run_episode(
    algorithm: str,
    seed: int,
    *,
    minutes: float = 15.0,
    dt_ms: int = TICK_MS,
    replay_path: Path | None = None,
    replay_sample_ms: int = 1_000,
) -> EpisodeResult:
    if algorithm not in available_algorithm_ids():
        raise ValueError(f"unknown or unavailable algorithm: {algorithm}")
    if minutes <= 0:
        raise ValueError("minutes must be positive")
    if dt_ms <= 0:
        raise ValueError("dt_ms must be positive")
    if replay_sample_ms <= 0:
        raise ValueError("replay_sample_ms must be positive")

    MiniMetroEnv, _engine_config = _load_engine()
    env = MiniMetroEnv(dt_ms=dt_ms, reward_mode="deliveries")
    observation = env.reset(seed=int(seed))
    planner = create_planner(algorithm)
    planner.reset(observation)

    max_steps = max(1, int(minutes * 60_000 / dt_ms))
    invalid_actions = 0
    done = False
    recorder = None
    next_sample_ms = replay_sample_ms

    if replay_path is not None:
        recorder = ReplayWriter(
            Path(replay_path),
            {
                "algorithm": algorithm,
                "seed": int(seed),
                "dt_ms": int(dt_ms),
                "minutes": float(minutes),
                "sample_every_ms": int(replay_sample_ms),
            },
        ).start()
        from .planner import Decision

        _record_frame(
            recorder,
            observation,
            Decision({"type": "noop"}, "Replay start", f"Seed {int(seed)}"),
            action_ok=True,
            kind="start",
        )

    try:
        for _ in range(max_steps):
            decision = planner.act(observation)
            observation, _reward, done, info = env.step(decision.action, dt_ms=dt_ms)
            action_ok = bool(info.get("action_ok", False))
            action_type = decision.action.get("type")
            if action_type != "noop" and not action_ok:
                invalid_actions += 1

            if recorder is not None:
                now_ms = int(observation["structured"].get("time_ms", 0))
                significant = action_type != "noop"
                sampled = now_ms >= next_sample_ms
                if significant or sampled or done:
                    _record_frame(
                        recorder,
                        observation,
                        decision,
                        action_ok=action_ok,
                        kind="decision" if significant else "end" if done else "sample",
                    )
                while now_ms >= next_sample_ms:
                    next_sample_ms += replay_sample_ms

            if done:
                break
    finally:
        if recorder is not None:
            recorder.close()

    structured = observation["structured"]
    return EpisodeResult(
        algorithm=algorithm,
        seed=int(seed),
        deliveries=int(structured.get("deliveries", 0)),
        line_credits=int(structured.get("line_credits", 0)),
        simulated_ms=int(structured.get("time_ms", 0)),
        steps=int(structured.get("steps", 0)),
        game_over=bool(structured.get("is_game_over", done)),
        invalid_actions=invalid_actions,
    )


def summarize(results: list[EpisodeResult]) -> list[AlgorithmSummary]:
    grouped: dict[str, list[EpisodeResult]] = {}
    for result in results:
        grouped.setdefault(result.algorithm, []).append(result)

    summaries: list[AlgorithmSummary] = []
    for algorithm, episodes in grouped.items():
        scores = [episode.deliveries for episode in episodes]
        summaries.append(
            AlgorithmSummary(
                algorithm=algorithm,
                episodes=len(episodes),
                mean_deliveries=round(statistics.fmean(scores), 2),
                median_deliveries=round(float(statistics.median(scores)), 2),
                min_deliveries=min(scores),
                max_deliveries=max(scores),
                game_over_rate=round(sum(episode.game_over for episode in episodes) / len(episodes), 3),
                invalid_actions=sum(episode.invalid_actions for episode in episodes),
            )
        )
    return sorted(summaries, key=lambda item: (-item.mean_deliveries, item.algorithm))


def run_suite(
    algorithms: list[str],
    seeds: list[int],
    *,
    minutes: float,
    dt_ms: int = TICK_MS,
) -> tuple[list[EpisodeResult], list[AlgorithmSummary]]:
    if not algorithms:
        raise ValueError("at least one algorithm is required")
    if not seeds:
        raise ValueError("at least one seed is required")

    results = [
        run_episode(algorithm, seed, minutes=minutes, dt_ms=dt_ms)
        for algorithm in algorithms
        for seed in seeds
    ]
    return results, summarize(results)


def _parser() -> argparse.ArgumentParser:
    available = available_algorithm_ids()
    parser = argparse.ArgumentParser(description="Mini Metro AI Lab 固定 Seed 算法竞技场")
    parser.add_argument(
        "--algorithms",
        nargs="+",
        default=[DEFAULT_ALGORITHM_ID],
        choices=available,
        help="要比较的算法",
    )
    parser.add_argument(
        "--seeds",
        nargs="+",
        type=int,
        default=[42, 314, 2026, 4096, 65537],
        help="公平复现用的随机种子",
    )
    parser.add_argument("--minutes", type=float, default=15.0, help="每局最多模拟多少分钟")
    parser.add_argument("--dt-ms", type=int, default=TICK_MS, help="模拟步长，默认与实时观战一致")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_EXPERIMENT_ROOT,
        help="实验结果目录，默认 output/experiments",
    )
    parser.add_argument("--no-save", action="store_true", help="只输出终端结果，不保存实验目录")
    parser.add_argument("--no-replays", action="store_true", help="保存结果，但不记录回放")
    parser.add_argument(
        "--replay-sample-ms",
        type=int,
        default=1_000,
        help="回放状态采样间隔；非 noop 决策无论如何都会记录",
    )
    parser.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    return parser


def _print_human(
    results: list[EpisodeResult],
    summaries: list[AlgorithmSummary],
    artifacts: ExperimentArtifacts | None = None,
) -> None:
    print("\n🚇 Mini Metro AI Arena")
    print("=" * 72)
    print(f"{'算法':16} {'Seed':>8} {'运送':>8} {'时间':>10} {'结束':>6} {'无效动作':>8}")
    for item in results:
        print(
            f"{item.algorithm:16} {item.seed:>8} {item.deliveries:>8} "
            f"{item.simulated_ms / 60_000:>8.2f}m "
            f"{'是' if item.game_over else '否':>6} {item.invalid_actions:>8}"
        )

    print("\n排行榜")
    print("-" * 72)
    print(f"{'算法':16} {'均值':>8} {'中位数':>8} {'最低':>8} {'最高':>8} {'结束率':>8}")
    for item in summaries:
        print(
            f"{item.algorithm:16} {item.mean_deliveries:>8.2f} {item.median_deliveries:>8.2f} "
            f"{item.min_deliveries:>8} {item.max_deliveries:>8} {item.game_over_rate:>7.0%}"
        )
    if artifacts is not None:
        print(f"\n📼 实验已保存：{artifacts.run_dir}")


def main() -> None:
    args = _parser().parse_args()
    if args.replay_sample_ms <= 0:
        raise SystemExit("--replay-sample-ms 必须大于 0")

    algorithms = list(args.algorithms)
    seeds = list(args.seeds)
    artifacts = None
    if not args.no_save:
        artifacts = ExperimentArtifacts.create(
            args.output_dir,
            algorithms=algorithms,
            seeds=seeds,
            minutes=args.minutes,
            dt_ms=args.dt_ms,
            replay_sample_ms=args.replay_sample_ms,
        )

    results: list[EpisodeResult] = []
    for algorithm in algorithms:
        for seed in seeds:
            replay_path = None
            if artifacts is not None and not args.no_replays:
                replay_path = artifacts.replay_path(algorithm, seed)
            results.append(
                run_episode(
                    algorithm,
                    seed,
                    minutes=args.minutes,
                    dt_ms=args.dt_ms,
                    replay_path=replay_path,
                    replay_sample_ms=args.replay_sample_ms,
                )
            )

    summaries = summarize(results)
    if artifacts is not None:
        artifacts.finalize(results, summaries)

    if args.json:
        print(
            json.dumps(
                {
                    "engine_commit": ENGINE_COMMIT,
                    "artifacts_dir": str(artifacts.run_dir) if artifacts is not None else None,
                    "results": [asdict(item) for item in results],
                    "summaries": [asdict(item) for item in summaries],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        _print_human(results, summaries, artifacts)


if __name__ == "__main__":
    main()
