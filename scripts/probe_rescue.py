from __future__ import annotations

import argparse
from dataclasses import dataclass

from metro_lab.algorithms import create_planner
from metro_lab.engine import _load_engine
from metro_lab.scenarios import advance_scenario, configure_scenario
from metro_lab.simulation import advance_fixed_dt


@dataclass
class ProbeResult:
    seed: int
    algorithm: str
    deliveries: int
    simulated_ms: int
    rescue_events: list[str]


def run_probe(seed: int, algorithm: str, *, minutes: float, dt_ms: int, scenario: str) -> ProbeResult:
    MiniMetroEnv, _ = _load_engine()
    env = MiniMetroEnv(dt_ms=dt_ms, reward_mode="deliveries")
    observation = env.reset(seed=int(seed))
    if configure_scenario(env, scenario):
        observation = env.observe()

    planner = create_planner(algorithm)
    planner.reset(observation)
    rescue_events: list[str] = []
    max_steps = max(1, int(minutes * 60_000 / dt_ms))

    for _ in range(max_steps):
        decision = planner.act(observation)
        now_ms = int(observation["structured"].get("time_ms", 0))
        if "救火" in decision.title:
            fleet = observation["structured"].get("fleet", {})
            rescue_events.append(
                f"t={now_ms / 1000:.1f}s {decision.action.get('type')} "
                f"locos={fleet.get('locomotives_available', 0)} "
                f"cars={fleet.get('carriages_available', 0)} | {decision.detail}"
            )

        outcome = advance_fixed_dt(env, observation, decision.action, dt_ms=dt_ms)
        observation = outcome.observation
        done = outcome.done
        if advance_scenario(env, scenario):
            observation = env.observe()
            done = bool(done or observation["structured"].get("is_game_over"))
        if done:
            break

    state = observation["structured"]
    return ProbeResult(
        seed=int(seed),
        algorithm=algorithm,
        deliveries=int(state.get("deliveries", 0)),
        simulated_ms=int(state.get("time_ms", 0)),
        rescue_events=rescue_events,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe pressure-rescue decisions on known development seeds.")
    parser.add_argument("--seeds", nargs="+", type=int, required=True)
    parser.add_argument("--scenario", default="stress-v1")
    parser.add_argument("--minutes", type=float, default=15.0)
    parser.add_argument("--dt-ms", type=int, default=100)
    args = parser.parse_args()

    for seed in args.seeds:
        baseline = run_probe(seed, "greedy-v1", minutes=args.minutes, dt_ms=args.dt_ms, scenario=args.scenario)
        candidate = run_probe(seed, "greedy-v1-1-pressure", minutes=args.minutes, dt_ms=args.dt_ms, scenario=args.scenario)
        print(
            f"seed={seed} v1={baseline.deliveries}@{baseline.simulated_ms / 60000:.2f}m "
            f"v1.1={candidate.deliveries}@{candidate.simulated_ms / 60000:.2f}m "
            f"delta={candidate.deliveries - baseline.deliveries:+d} rescues={len(candidate.rescue_events)}"
        )
        for event in candidate.rescue_events:
            print("  " + event)


if __name__ == "__main__":
    main()
