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
from .metrics import EpisodeTelemetry
from .pressure import passenger_pressure
from .scenarios import (
    DEFAULT_SCENARIO_ID,
    advance_scenario,
    configure_scenario,
    get_scenario_spec,
    scenario_ids,
)
from .simulation import SIMULATION_PROTOCOL_VERSION, advance_fixed_dt


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
    protocol_version: int = SIMULATION_PROTOCOL_VERSION
    scenario: str = DEFAULT_SCENARIO_ID
    deliveries_per_minute: float = 0.0
    average_waiting_passengers: float = 0.0
    waiting_passenger_seconds: float = 0.0
    peak_network_waiting: int = 0
    peak_station_queue: int = 0
    average_fleet_load_pct: float = 0.0
    at_risk_passenger_seconds: float = 0.0
    overdue_passenger_seconds: float = 0.0
    high_risk_seconds: float = 0.0
    peak_at_risk_passengers: int = 0
    peak_overdue_passengers: int = 0
    peak_wait_seconds: float = 0.0
    peak_risk_pct: int = 0
    passenger_max_wait_seconds: float = 0.0
    overdue_passenger_threshold: int = 0
    max_paths: int = 0
    max_stations: int = 0
    max_locomotives_assigned: int = 0
    max_carriages_assigned: int = 0
    non_noop_actions: int = 0
    topology_actions: int = 0


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
    scenario: str = DEFAULT_SCENARIO_ID
    mean_survival_minutes: float = 0.0
    mean_deliveries_per_minute: float = 0.0
    mean_waiting_passengers: float = 0.0
    mean_peak_network_waiting: float = 0.0
    mean_peak_station_queue: float = 0.0
    mean_fleet_load_pct: float = 0.0
    mean_peak_wait_seconds: float = 0.0
    mean_peak_risk_pct: float = 0.0
    mean_high_risk_seconds: float = 0.0
    mean_at_risk_passenger_seconds: float = 0.0
    mean_peak_overdue_passengers: float = 0.0
    non_noop_actions: int = 0
    invalid_action_rate: float = 0.0


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
    scenario: str = DEFAULT_SCENARIO_ID,
    replay_path: Path | None = None,
    replay_sample_ms: int = 1_000,
) -> EpisodeResult:
    if algorithm not in available_algorithm_ids():
        raise ValueError(f"unknown or unavailable algorithm: {algorithm}")
    get_scenario_spec(scenario)
    if minutes <= 0:
        raise ValueError("minutes must be positive")
    if dt_ms <= 0:
        raise ValueError("dt_ms must be positive")
    if replay_sample_ms <= 0:
        raise ValueError("replay_sample_ms must be positive")

    MiniMetroEnv, _engine_config = _load_engine()
    env = MiniMetroEnv(dt_ms=dt_ms, reward_mode="deliveries")
    observation = env.reset(seed=int(seed))
    if configure_scenario(env, scenario):
        observation = env.observe()
    planner = create_planner(algorithm)
    planner.reset(observation)

    telemetry = EpisodeTelemetry()
    telemetry.observe_initial(observation, passenger_pressure(env))
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
                "scenario": scenario,
                "dt_ms": int(dt_ms),
                "minutes": float(minutes),
                "sample_every_ms": int(replay_sample_ms),
                "simulation_protocol": SIMULATION_PROTOCOL_VERSION,
            },
        ).start()
        from .planner import Decision

        _record_frame(
            recorder,
            observation,
            Decision({"type": "noop"}, "Replay start", f"Seed {int(seed)} · {scenario}"),
            action_ok=True,
            kind="start",
        )

    try:
        for _ in range(max_steps):
            decision = planner.act(observation)
            action_type = decision.action.get("type")
            telemetry.record_action(action_type)

            outcome = advance_fixed_dt(
                env,
                observation,
                decision.action,
                dt_ms=dt_ms,
            )
            observation = outcome.observation
            done = outcome.done
            action_ok = outcome.action_ok
            if advance_scenario(env, scenario):
                observation = env.observe()
                done = bool(done or observation["structured"].get("is_game_over"))
            telemetry.record_transition(
                observation,
                elapsed_ms=outcome.elapsed_ms,
                pressure=passenger_pressure(env),
            )

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
    simulated_ms = int(structured.get("time_ms", 0))
    deliveries = int(structured.get("deliveries", 0))
    deliveries_per_minute = (
        deliveries / (simulated_ms / 60_000) if simulated_ms > 0 else 0.0
    )
    return EpisodeResult(
        algorithm=algorithm,
        seed=int(seed),
        deliveries=deliveries,
        line_credits=int(structured.get("line_credits", 0)),
        simulated_ms=simulated_ms,
        steps=int(structured.get("steps", 0)),
        game_over=bool(structured.get("is_game_over", done)),
        invalid_actions=invalid_actions,
        scenario=scenario,
        deliveries_per_minute=round(deliveries_per_minute, 3),
        average_waiting_passengers=round(telemetry.average_waiting_passengers, 3),
        waiting_passenger_seconds=round(telemetry.waiting_passenger_seconds, 2),
        peak_network_waiting=telemetry.peak_network_waiting,
        peak_station_queue=telemetry.peak_station_queue,
        average_fleet_load_pct=round(telemetry.average_fleet_load_pct, 2),
        at_risk_passenger_seconds=round(telemetry.at_risk_passenger_seconds, 2),
        overdue_passenger_seconds=round(telemetry.overdue_passenger_seconds, 2),
        high_risk_seconds=round(telemetry.high_risk_seconds, 2),
        peak_at_risk_passengers=telemetry.peak_at_risk_passengers,
        peak_overdue_passengers=telemetry.peak_overdue_passengers,
        peak_wait_seconds=round(telemetry.peak_wait_ms / 1000.0, 2),
        peak_risk_pct=telemetry.peak_risk_pct,
        passenger_max_wait_seconds=round(telemetry.passenger_max_wait_time_ms / 1000.0, 2),
        overdue_passenger_threshold=telemetry.overdue_passenger_threshold,
        max_paths=telemetry.max_paths,
        max_stations=telemetry.max_stations,
        max_locomotives_assigned=telemetry.max_locomotives_assigned,
        max_carriages_assigned=telemetry.max_carriages_assigned,
        non_noop_actions=telemetry.non_noop_actions,
        topology_actions=telemetry.topology_actions,
    )


def summarize(results: list[EpisodeResult]) -> list[AlgorithmSummary]:
    grouped: dict[tuple[str, str], list[EpisodeResult]] = {}
    for result in results:
        grouped.setdefault((result.algorithm, result.scenario), []).append(result)

    summaries: list[AlgorithmSummary] = []
    for (algorithm, scenario), episodes in grouped.items():
        scores = [episode.deliveries for episode in episodes]
        non_noop_actions = sum(episode.non_noop_actions for episode in episodes)
        invalid_actions = sum(episode.invalid_actions for episode in episodes)
        summaries.append(
            AlgorithmSummary(
                algorithm=algorithm,
                episodes=len(episodes),
                mean_deliveries=round(statistics.fmean(scores), 2),
                median_deliveries=round(float(statistics.median(scores)), 2),
                min_deliveries=min(scores),
                max_deliveries=max(scores),
                game_over_rate=round(sum(episode.game_over for episode in episodes) / len(episodes), 3),
                invalid_actions=invalid_actions,
                scenario=scenario,
                mean_survival_minutes=round(
                    statistics.fmean(episode.simulated_ms / 60_000 for episode in episodes), 3
                ),
                mean_deliveries_per_minute=round(
                    statistics.fmean(episode.deliveries_per_minute for episode in episodes), 3
                ),
                mean_waiting_passengers=round(
                    statistics.fmean(episode.average_waiting_passengers for episode in episodes), 3
                ),
                mean_peak_network_waiting=round(
                    statistics.fmean(episode.peak_network_waiting for episode in episodes), 2
                ),
                mean_peak_station_queue=round(
                    statistics.fmean(episode.peak_station_queue for episode in episodes), 2
                ),
                mean_fleet_load_pct=round(
                    statistics.fmean(episode.average_fleet_load_pct for episode in episodes), 2
                ),
                mean_peak_wait_seconds=round(
                    statistics.fmean(episode.peak_wait_seconds for episode in episodes), 2
                ),
                mean_peak_risk_pct=round(
                    statistics.fmean(episode.peak_risk_pct for episode in episodes), 1
                ),
                mean_high_risk_seconds=round(
                    statistics.fmean(episode.high_risk_seconds for episode in episodes), 2
                ),
                mean_at_risk_passenger_seconds=round(
                    statistics.fmean(episode.at_risk_passenger_seconds for episode in episodes), 2
                ),
                mean_peak_overdue_passengers=round(
                    statistics.fmean(episode.peak_overdue_passengers for episode in episodes), 2
                ),
                non_noop_actions=non_noop_actions,
                invalid_action_rate=round(
                    invalid_actions / non_noop_actions if non_noop_actions else 0.0,
                    4,
                ),
            )
        )
    return sorted(
        summaries,
        key=lambda item: (
            item.scenario,
            -item.mean_deliveries,
            item.game_over_rate,
            item.mean_peak_risk_pct,
            item.algorithm,
        ),
    )


def run_suite(
    algorithms: list[str],
    seeds: list[int],
    *,
    minutes: float,
    dt_ms: int = TICK_MS,
    scenario: str = DEFAULT_SCENARIO_ID,
) -> tuple[list[EpisodeResult], list[AlgorithmSummary]]:
    if not algorithms:
        raise ValueError("at least one algorithm is required")
    if not seeds:
        raise ValueError("at least one seed is required")
    get_scenario_spec(scenario)

    results = [
        run_episode(algorithm, seed, minutes=minutes, dt_ms=dt_ms, scenario=scenario)
        for algorithm in algorithms
        for seed in seeds
    ]
    return results, summarize(results)


def _parser() -> argparse.ArgumentParser:
    available = available_algorithm_ids()
    parser = argparse.ArgumentParser(description="Mini Metro AI Lab 固定 Seed 算法竞技场")
    parser.add_argument("--algorithms", nargs="+", default=[DEFAULT_ALGORITHM_ID], choices=available, help="要比较的算法")
    parser.add_argument("--seeds", nargs="+", type=int, default=[42, 314, 2026, 4096, 65537], help="公平复现用的随机种子")
    parser.add_argument("--scenario", default=DEFAULT_SCENARIO_ID, choices=scenario_ids(), help="版本化 benchmark 场景")
    parser.add_argument("--minutes", type=float, default=15.0, help="每局最多模拟多少分钟")
    parser.add_argument("--dt-ms", type=int, default=TICK_MS, help="模拟步长，默认与实时观战一致")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_EXPERIMENT_ROOT, help="实验结果目录，默认 output/experiments")
    parser.add_argument("--no-save", action="store_true", help="只输出终端结果，不保存实验目录")
    parser.add_argument("--no-replays", action="store_true", help="保存结果，但不记录回放")
    parser.add_argument("--replay-sample-ms", type=int, default=1_000, help="回放状态采样间隔；非 noop 决策无论如何都会记录")
    parser.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    return parser


def _print_human(
    results: list[EpisodeResult],
    summaries: list[AlgorithmSummary],
    scenario: str,
    artifacts: ExperimentArtifacts | None = None,
) -> None:
    spec = get_scenario_spec(scenario)
    print(f"\n🚇 Mini Metro AI Arena · Protocol V2 · {spec.name}")
    print("=" * 108)
    print(
        f"{'算法':18} {'Seed':>8} {'运送':>6} {'D/min':>7} {'均候车':>7} "
        f"{'风险峰':>7} {'最长等':>7} {'站点':>5} {'时间':>8} {'无效':>5}"
    )
    for item in results:
        print(
            f"{item.algorithm:18} {item.seed:>8} {item.deliveries:>6} "
            f"{item.deliveries_per_minute:>7.2f} {item.average_waiting_passengers:>7.2f} "
            f"{item.peak_risk_pct:>6}% {item.peak_wait_seconds:>6.1f}s {item.max_stations:>5} "
            f"{item.simulated_ms / 60_000:>6.2f}m {item.invalid_actions:>5}"
        )

    print("\n排行榜（主排序仍以运送量为准，压力指标解释生存质量）")
    print("-" * 108)
    print(
        f"{'算法':18} {'均值':>7} {'D/min':>7} {'均候车':>7} {'风险峰':>7} "
        f"{'最长等':>7} {'高危秒':>7} {'结束率':>7} {'无效率':>7}"
    )
    for item in summaries:
        print(
            f"{item.algorithm:18} {item.mean_deliveries:>7.2f} "
            f"{item.mean_deliveries_per_minute:>7.2f} {item.mean_waiting_passengers:>7.2f} "
            f"{item.mean_peak_risk_pct:>6.1f}% {item.mean_peak_wait_seconds:>6.1f}s "
            f"{item.mean_high_risk_seconds:>7.1f} {item.game_over_rate:>6.0%} "
            f"{item.invalid_action_rate:>6.1%}"
        )
    if artifacts is not None:
        print(f"\n📼 实验已保存：{artifacts.run_dir}")


def main() -> None:
    args = _parser().parse_args()
    if args.replay_sample_ms <= 0:
        raise SystemExit("--replay-sample-ms 必须大于 0")

    algorithms = list(args.algorithms)
    seeds = list(args.seeds)
    scenario = str(args.scenario)
    artifacts = None
    if not args.no_save:
        artifacts = ExperimentArtifacts.create(
            args.output_dir,
            algorithms=algorithms,
            seeds=seeds,
            minutes=args.minutes,
            dt_ms=args.dt_ms,
            replay_sample_ms=args.replay_sample_ms,
            scenario=scenario,
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
                    scenario=scenario,
                    replay_path=replay_path,
                    replay_sample_ms=args.replay_sample_ms,
                )
            )

    summaries = summarize(results)
    if artifacts is not None:
        artifacts.finalize(results, summaries)

    if args.json:
        print(json.dumps({
            "engine_commit": ENGINE_COMMIT,
            "simulation_protocol": SIMULATION_PROTOCOL_VERSION,
            "scenario": scenario,
            "artifacts_dir": str(artifacts.run_dir) if artifacts is not None else None,
            "results": [asdict(item) for item in results],
            "summaries": [asdict(item) for item in summaries],
        }, ensure_ascii=False, indent=2))
    else:
        _print_human(results, summaries, scenario, artifacts)


if __name__ == "__main__":
    main()
