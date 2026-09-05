from __future__ import annotations

import unittest

from metro_lab.config import ENGINE_SRC, TICK_MS
from metro_lab.contract_greedy import ContractGreedyV1
from metro_lab.planner import GreedyPlanner
from metro_lab.plugin import AlgorithmPluginRegistry
from metro_lab.problem import state_from_observation
from metro_lab.scenarios import (
    CLASSIC_SCENARIO_ID,
    STRESS_SCENARIO_ID,
    advance_scenario,
    configure_scenario,
)
from metro_lab.simulation import advance_fixed_dt


class ContractGreedyPureTests(unittest.TestCase):
    def test_contract_greedy_registers_as_problem_plugin(self) -> None:
        registry = AlgorithmPluginRegistry()
        metadata = registry.register(ContractGreedyV1)
        self.assertEqual(metadata.id, "greedy-v1-contract")
        self.assertEqual(registry.ids(), ("greedy-v1-contract",))


@unittest.skipUnless(ENGINE_SRC.exists(), "vendor engine not bootstrapped")
class ContractGreedyEngineTests(unittest.TestCase):
    def _assert_equivalent(self, *, seed: int, scenario_id: str, steps: int) -> None:
        from metro_lab.engine import _load_engine

        MiniMetroEnv, _engine_config = _load_engine()
        env = MiniMetroEnv(dt_ms=TICK_MS, reward_mode="deliveries")
        observation = env.reset(seed=seed)
        if configure_scenario(env, scenario_id):
            observation = env.observe()

        legacy = GreedyPlanner()
        contract = ContractGreedyV1()
        legacy.reset(observation)
        contract.reset(state_from_observation(observation))

        compared = 0
        for step in range(steps):
            legacy_decision = legacy.act(observation)
            contract_decision = contract.act(state_from_observation(observation))
            self.assertEqual(
                contract_decision,
                legacy_decision,
                msg=f"decision diverged at seed={seed} scenario={scenario_id} step={step}",
            )
            compared += 1

            outcome = advance_fixed_dt(
                env,
                observation,
                legacy_decision.action,
                dt_ms=TICK_MS,
            )
            observation = outcome.observation
            if advance_scenario(env, scenario_id):
                observation = env.observe()
            if outcome.done:
                break

        self.assertGreater(compared, 0)

    def test_classic_real_engine_decisions_are_strictly_equivalent(self) -> None:
        for seed in (42, 314, 2026):
            with self.subTest(seed=seed):
                self._assert_equivalent(
                    seed=seed,
                    scenario_id=CLASSIC_SCENARIO_ID,
                    steps=700,
                )

    def test_stress_real_engine_decisions_are_strictly_equivalent(self) -> None:
        for seed in (42, 314, 2026):
            with self.subTest(seed=seed):
                self._assert_equivalent(
                    seed=seed,
                    scenario_id=STRESS_SCENARIO_ID,
                    steps=700,
                )


if __name__ == "__main__":
    unittest.main()
