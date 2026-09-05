#!/usr/bin/env python3
from __future__ import annotations

import argparse

from metro_lab.algorithms import create_planner
from metro_lab.config import TICK_MS
from metro_lab.engine import _load_engine
from metro_lab.scenarios import advance_scenario, configure_scenario, get_scenario_spec
from metro_lab.simulation import advance_fixed_dt


def run(seed: int, *, minutes: float, dt_ms: int, scenario: str) -> None:
    MiniMetroEnv, _ = _load_engine()
    env = MiniMetroEnv(dt_ms=dt_ms, reward_mode="deliveries")
    observation = env.reset(seed=int(seed))
    if configure_scenario(env, scenario):
        observation = env.observe()

    planner = create_planner("balanced-greedy-v2-2")
    planner.reset(observation)
    attempts: list[dict] = []
    max_steps = max(1, int(minutes * 60_000 / dt_ms))

    for _ in range(max_steps):
        decision = planner.act(observation)
        action = decision.action
        is_relayout = action.get("_lab_kind") == "relayout-2opt"
        before_ms = int(observation["structured"].get("time_ms", 0))

        outcome = advance_fixed_dt(env, observation, action, dt_ms=dt_ms)
        observation = outcome.observation
        done = outcome.done
        if advance_scenario(env, scenario):
            observation = env.observe()
            done = bool(done or observation["structured"].get("is_game_over"))

        if is_relayout:
            attempts.append(
                {
                    "time_ms": before_ms,
                    "ok": bool(outcome.action_ok),
                    "improvement_px": float(action.get("_lab_improvement_px", 0.0)),
                    "before": list(action.get("_lab_before_route", ())),
                    "after": list(action.get("_lab_after_route", ())),
                }
            )
        if done:
            break

    state = observation["structured"]
    accepted = [item for item in attempts if item["ok"]]
    rejected = [item for item in attempts if not item["ok"]]
    print(
        f"seed={seed} deliveries={int(state.get('deliveries', 0))} "
        f"time={int(state.get('time_ms', 0)) / 60000:.2f}m "
        f"relayout={len(attempts)} ok={len(accepted)} reject={len(rejected)} "
        f"accepted_px={sum(item['improvement_px'] for item in accepted):.1f}"
    )
    for index, item in enumerate(attempts, 1):
        print(
            f"  #{index} t={item['time_ms'] / 1000:.1f}s "
            f"{'OK' if item['ok'] else 'REJECT'} "
            f"gain={item['improvement_px']:.1f}px "
            f"{item['before']} -> {item['after']}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Probe V2.2 2-opt proposals and engine acceptance without changing policy."
    )
    parser.add_argument("--seeds", nargs="+", type=int, required=True)
    parser.add_argument("--scenario", default="stress-v1")
    parser.add_argument("--minutes", type=float, default=15.0)
    parser.add_argument("--dt-ms", type=int, default=TICK_MS)
    args = parser.parse_args()
    get_scenario_spec(args.scenario)
    for seed in args.seeds:
        run(seed, minutes=args.minutes, dt_ms=args.dt_ms, scenario=args.scenario)


if __name__ == "__main__":
    main()
