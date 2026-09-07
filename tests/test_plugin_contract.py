from __future__ import annotations

import unittest

from metro_lab.action import ACTION_CONTRACT_VERSION, NoOpAction, PlanningDecision
from metro_lab.plugin import (
    AlgorithmMetadata,
    AlgorithmPluginRegistry,
    PluginRegistrationError,
)
from metro_lab.problem import MetroPlanningState, PROBLEM_CONTRACT_VERSION


class EchoPlugin:
    metadata = AlgorithmMetadata(
        id="echo-test",
        name="Echo Test",
        version="0.1",
        family="test",
        description="Minimal test plugin",
    )

    def reset(self, state: MetroPlanningState) -> None:
        self.last_time = state.time_ms

    def act(self, state: MetroPlanningState) -> PlanningDecision:
        return PlanningDecision(NoOpAction(), "noop", f"t={state.time_ms}")


class WrongProblemContractPlugin(EchoPlugin):
    metadata = AlgorithmMetadata(
        id="wrong-problem-contract",
        name="Wrong Problem Contract",
        version="0.1",
        family="test",
        problem_contract="999",
    )


class WrongActionContractPlugin(EchoPlugin):
    metadata = AlgorithmMetadata(
        id="wrong-action-contract",
        name="Wrong Action Contract",
        version="0.1",
        family="test",
        action_contract="999",
    )


class PluginContractTests(unittest.TestCase):
    def test_registry_registers_and_recreates_plugins(self) -> None:
        registry = AlgorithmPluginRegistry()

        metadata = registry.register(EchoPlugin)
        plugin = registry.create("echo-test")

        self.assertEqual(metadata.id, "echo-test")
        self.assertEqual(registry.ids(), ("echo-test",))
        self.assertEqual(registry.metadata(), (metadata,))
        self.assertEqual(plugin.metadata.problem_contract, PROBLEM_CONTRACT_VERSION)
        self.assertEqual(plugin.metadata.action_contract, ACTION_CONTRACT_VERSION)

    def test_registry_rejects_duplicate_ids(self) -> None:
        registry = AlgorithmPluginRegistry()
        registry.register(EchoPlugin)

        with self.assertRaisesRegex(PluginRegistrationError, "duplicate algorithm id"):
            registry.register(EchoPlugin)

    def test_registry_rejects_problem_contract_mismatch(self) -> None:
        registry = AlgorithmPluginRegistry()

        with self.assertRaisesRegex(PluginRegistrationError, "unsupported problem contract"):
            registry.register(WrongProblemContractPlugin)

    def test_registry_rejects_action_contract_mismatch(self) -> None:
        registry = AlgorithmPluginRegistry()

        with self.assertRaisesRegex(PluginRegistrationError, "unsupported action contract"):
            registry.register(WrongActionContractPlugin)


if __name__ == "__main__":
    unittest.main()
