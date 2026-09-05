from __future__ import annotations

import pytest

from metro_lab.planner import Decision
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

    def act(self, state: MetroPlanningState) -> Decision:
        return Decision({"type": "noop"}, "noop", f"t={state.time_ms}")


class WrongContractPlugin(EchoPlugin):
    metadata = AlgorithmMetadata(
        id="wrong-contract",
        name="Wrong Contract",
        version="0.1",
        family="test",
        problem_contract="999",
    )


def test_plugin_registry_registers_and_recreates_plugins() -> None:
    registry = AlgorithmPluginRegistry()

    metadata = registry.register(EchoPlugin)
    plugin = registry.create("echo-test")

    assert metadata.id == "echo-test"
    assert registry.ids() == ("echo-test",)
    assert registry.metadata() == (metadata,)
    assert plugin.metadata.problem_contract == PROBLEM_CONTRACT_VERSION


def test_plugin_registry_rejects_duplicate_ids() -> None:
    registry = AlgorithmPluginRegistry()
    registry.register(EchoPlugin)

    with pytest.raises(PluginRegistrationError, match="duplicate algorithm id"):
        registry.register(EchoPlugin)


def test_plugin_registry_rejects_contract_mismatch() -> None:
    registry = AlgorithmPluginRegistry()

    with pytest.raises(PluginRegistrationError, match="unsupported problem contract"):
        registry.register(WrongContractPlugin)
