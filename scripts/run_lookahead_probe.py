from __future__ import annotations

import argparse
import json

from metro_lab.engine import _load_engine
from metro_lab.lookahead_probe import run_probe, score_candidates
from metro_lab.planner import GreedyPlanner
from metro_lab.rollout import capture_rollout_snapshot, sample_future_keys
from metro_lab.scenarios import STRESS_SCENARIO_ID, advance_scenario, configure_scenario
from metro_lab.simulation import advance_fixed_dt


def _advance_baseline_to(env, planner, target_ms: int):
    observation = env.observe()
    while (
        not observation["structured"]["is_game_over"]
        and int(observation["structured"]["time_ms"]) < target_ms
    ):
        decision = planner.act(observation)
        outcome = advance_fixed_dt(env, observation, decision.action, dt_ms=100)
        observation = outcome.observation
        if advance_scenario(env, STRESS_SCENARIO_ID):
            observation = env.observe()
    return observation


def probe_seed(
    seed: int,
    *,
    points_ms: tuple[int, ...],
    planning_futures: int,
    evaluation_futures: int,
    horizon_ms: int,
    max_candidates: int,
) -> list[dict]:
    MiniMetroEnv, _config = _load_engine()
    env = MiniMetroEnv(dt_ms=100, reward_mode="deliveries")
    observation = env.reset(seed=seed)
    configure_scenario(env, STRESS_SCENARIO_ID)
    observation = env.observe()
    planner = GreedyPlanner()
    planner.reset(observation)
    rows: list[dict] = []

    for point_index, point_ms in enumerate(points_ms):
        observation = _advance_baseline_to(env, planner, point_ms)
        if observation["structured"]["is_game_over"]:
            rows.append({"seed": seed, "point_ms": point_ms, "status": "game_over_before_probe"})
            break

        baseline = planner.act(observation)
        snapshot = capture_rollout_snapshot(env)
        plan_keys = sample_future_keys(seed * 10_000 + point_index * 101 + 11, planning_futures)
        eval_keys = sample_future_keys(seed * 10_000 + point_index * 101 + 79, evaluation_futures)
        result = run_probe(
            snapshot,
            observation,
            baseline,
            future_keys=plan_keys,
            scenario_id=STRESS_SCENARIO_ID,
            horizon_ms=horizon_ms,
            max_candidates=max_candidates,
        )

        # Evaluate only the selected action and the original Greedy action on a
        # disjoint future set. The evaluation futures never participated in
        # candidate selection, so this is an out-of-sample paired check.
        eval_actions = (result.baseline_action, result.best.action)
        if result.best.action == result.baseline_action:
            eval_actions = (result.baseline_action,)
        evaluated = score_candidates(
            snapshot,
            eval_actions,
            future_keys=eval_keys,
            scenario_id=STRESS_SCENARIO_ID,
            horizon_ms=horizon_ms,
        )
        baseline_eval = evaluated[0]
        chosen_eval = evaluated[-1]
        rows.append(
            {
                "seed": seed,
                "point_ms": point_ms,
                "status": "ok",
                "baseline_action": result.baseline_action,
                "chosen_action": result.best.action,
                "overrode": result.best.action != result.baseline_action,
                "planning_candidate_count": len(result.scores),
                "planning_best_deliveries": result.best.expected_deliveries,
                "evaluation_baseline_deliveries": baseline_eval.expected_deliveries,
                "evaluation_chosen_deliveries": chosen_eval.expected_deliveries,
                "evaluation_delivery_margin": (
                    chosen_eval.expected_deliveries - baseline_eval.expected_deliveries
                ),
                "evaluation_survival_margin_ms": (
                    chosen_eval.expected_survival_ms - baseline_eval.expected_survival_ms
                ),
                "evaluation_risk_delta": (
                    chosen_eval.expected_peak_risk - baseline_eval.expected_peak_risk
                ),
                "planning_keys": list(plan_keys),
                "evaluation_keys": list(eval_keys),
            }
        )

        # Continue the observed baseline episode. Probe choices never alter the
        # state used to create later probe points.
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Out-of-sample stochastic one-decision lookahead probe"
    )
    parser.add_argument("--seeds", nargs="+", type=int, default=[42, 314, 2026, 4096, 65537])
    parser.add_argument("--points-seconds", nargs="+", type=int, default=[180, 360, 540])
    parser.add_argument("--planning-futures", type=int, default=4)
    parser.add_argument("--evaluation-futures", type=int, default=8)
    parser.add_argument("--horizon-seconds", type=int, default=120)
    parser.add_argument("--max-candidates", type=int, default=8)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if set(args.points_seconds) != set(sorted(args.points_seconds)):
        raise SystemExit("--points-seconds must be unique and increasing")

    rows: list[dict] = []
    for seed in args.seeds:
        rows.extend(
            probe_seed(
                seed,
                points_ms=tuple(value * 1000 for value in args.points_seconds),
                planning_futures=args.planning_futures,
                evaluation_futures=args.evaluation_futures,
                horizon_ms=args.horizon_seconds * 1000,
                max_candidates=args.max_candidates,
            )
        )

    ok = [row for row in rows if row["status"] == "ok"]
    overrides = [row for row in ok if row["overrode"]]
    wins = [row for row in overrides if row["evaluation_delivery_margin"] > 0]
    losses = [row for row in overrides if row["evaluation_delivery_margin"] < 0]
    ties = [row for row in overrides if row["evaluation_delivery_margin"] == 0]
    mean_margin = (
        sum(row["evaluation_delivery_margin"] for row in overrides) / len(overrides)
        if overrides
        else 0.0
    )

    summary = {
        "probes": len(ok),
        "overrides": len(overrides),
        "override_wins": len(wins),
        "override_losses": len(losses),
        "override_ties": len(ties),
        "mean_out_of_sample_delivery_margin_on_overrides": mean_margin,
        "rows": rows,
    }
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print("\n🔭 Stochastic Lookahead Probe · out-of-sample futures")
        print("=" * 92)
        for row in ok:
            marker = "→" if row["overrode"] else "="
            print(
                f"seed {row['seed']:>10} @ {row['point_ms']/1000:>4.0f}s {marker} "
                f"margin {row['evaluation_delivery_margin']:+5.2f}  "
                f"risk Δ {row['evaluation_risk_delta']:+5.1f}%  "
                f"{row['baseline_action']['type']} -> {row['chosen_action']['type']}"
            )
        print("-" * 92)
        print(
            f"probes {len(ok)}, overrides {len(overrides)}, "
            f"W/L/T {len(wins)}/{len(losses)}/{len(ties)}, "
            f"mean override margin {mean_margin:+.2f} deliveries"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
