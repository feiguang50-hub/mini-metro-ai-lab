from __future__ import annotations

from .action import to_backend_action
from .planner import Decision
from .plugin import AlgorithmFactory, PlanningAlgorithm
from .problem import state_from_observation


class PluginPlannerAdapter:
    """Bridge a backend-neutral algorithm plugin into the legacy runtime surface.

    Viewer, Battle and Arena still call planners with raw observations and expect
    serializable ``Decision`` objects. The adapter keeps that compatibility at
    one edge while the plugin itself sees only Problem + Action Contracts.
    """

    def __init__(self, factory: AlgorithmFactory) -> None:
        self._factory = factory
        self._plugin: PlanningAlgorithm = factory()

    @property
    def plugin(self) -> PlanningAlgorithm:
        return self._plugin

    def reset(self, observation: dict[str, object]) -> None:
        self._plugin = self._factory()
        self._plugin.reset(state_from_observation(observation))

    def act(self, observation: dict[str, object]) -> Decision:
        state = state_from_observation(observation)
        semantic = self._plugin.act(state)
        return Decision(
            to_backend_action(state, semantic.action),
            semantic.title,
            semantic.detail,
        )


def plugin_planner_factory(factory: AlgorithmFactory):
    """Return a no-argument legacy planner factory for one contract plugin."""

    def create() -> PluginPlannerAdapter:
        return PluginPlannerAdapter(factory)

    return create
