# Platform Contracts V1

Mini Metro AI Lab is being evolved from a game-specific algorithm viewer into an experimentation platform for the **metro line-planning problem**.

The platform is the test harness. Algorithms are interchangeable research components.

## Research objective

The goal is not to reproduce every detail of a real metro system. The goal is to preserve the smallest set of real-world structures that materially change solution quality, algorithm ranking, robustness, or computational difficulty.

We call this principle **minimum sufficient realism**:

- do not over-simplify away the structure that makes metro planning difficult;
- do not simulate details that add complexity without changing the mathematical decision problem;
- every added mechanism should answer what real constraint it represents, what algorithmic capability it tests, and whether the added complexity is worth it.

## Separation of concerns

The long-term architecture is:

```text
Real / synthetic data
        |
        v
Problem Instance / Problem State
        |
        v
Algorithm Plugin API
        |
        v
Semantic Action Contract
        |
        v
Backend Adapter / Experiment Engine / Scenario / Budget
        |
        v
Evaluator / Diagnostics / Replay
        |
        v
Viewer / Battle / Research UI
```

Mini Metro is the first simulation backend, not the permanent definition of the problem.

## Problem Contract V1

`metro_lab.problem.MetroPlanningState` is the first backend-neutral state contract. It contains only information that is part of the planning problem:

- time and terminal state;
- deliveries and currently visible line resources;
- stations with position, shape and queue size;
- active lines and their ordered station membership;
- vehicle-to-line placement;
- available fleet resources.

`state_from_observation()` is deliberately restricted to the public structured observation. It must not inspect simulator internals or hidden RNG state.

The contract is versioned. A future extension that changes the meaning or availability of algorithm inputs must explicitly advance the contract version.

`StationState.index` and `LineState.index` currently remain only for V1 migration compatibility. New algorithms must treat stable station/line IDs as semantic identity. Backend indexing is not part of Action Contract V1 and should disappear from a future Problem Contract revision after legacy migration is complete.

## Action Contract V1

`metro_lab.action` defines semantic actions using stable station and line IDs. Algorithms express intent such as:

- create a line through an ordered tuple of station IDs;
- replace a named line with a new ordered station route;
- assign a locomotive to a named line;
- attach a carriage to a named line;
- do nothing for this decision round.

Algorithms do **not** emit Mini Metro `path_index` values or station-index arrays. `to_backend_action()` is the adapter edge that resolves semantic IDs against the current problem state and emits the backend-specific action dictionary.

Unknown station or line IDs fail at that boundary before an invalid backend call is attempted.

Action Contract V1 is intentionally small. It contains only operations already needed by the proven baseline migration. New operations should be added from mathematical planning needs, not by copying every simulator command into the public contract.

## Algorithm Plugin Contract V1

A backend-neutral algorithm implements only:

```python
metadata: AlgorithmMetadata
reset(state: MetroPlanningState) -> None
act(state: MetroPlanningState) -> PlanningDecision
```

`PlanningDecision.action` is an Action Contract V1 object, not a simulator dictionary.

Algorithms do not receive the viewer, HTTP server, replay writer, experiment runner or Mini Metro mediator.

The plugin registry rejects duplicate IDs, incompatible problem IDs, incompatible problem-contract versions and incompatible action-contract versions. This is the future loading boundary for drop-in algorithms.

## Runtime adapter

`metro_lab.plugin_runtime.PluginPlannerAdapter` is the compatibility edge between the new contracts and the existing Viewer / Battle / Arena runtime:

```text
legacy runtime observation
        |
        v
state_from_observation()
        |
        v
PlanningAlgorithm
        |
        v
PlanningDecision
        |
        v
to_backend_action()
        |
        v
legacy runtime Decision
```

The public `greedy-v1` baseline now runs through this adapter and `ContractGreedyV1`. Its public algorithm ID, metadata and behavior remain unchanged. The old `GreedyPlanner` implementation stays in the repository as a behavioral oracle during migration and for archived strategies that still inherit from it.

This is the first production execution path to use Problem + Action Contracts end to end.

## Migration rule

Balanced / Rescue planners remain untouched until each algorithm is migrated deliberately. They still use the legacy structured observation.

`ContractGreedyV1` remains the migration witness. Its semantic actions are translated at the backend edge and compared step-by-step with the legacy Greedy V1 on the real pinned engine. A platform refactor is not accepted if that compiled behavior diverges.

## Next contract milestones

1. expose explicit compute budgets and decision latency in the benchmark contract;
2. add a first-class plugin loading/discovery path with validation before an algorithm can enter experiments;
3. define problem families rather than a single difficulty axis;
4. keep Viewer/Battle as diagnostic instruments over the same experiment state rather than separate game logic;
5. migrate additional algorithms only when doing so improves the platform boundary rather than creating churn;
6. remove migration-only backend index fields in a future Problem Contract revision once legacy algorithms no longer depend on them.
