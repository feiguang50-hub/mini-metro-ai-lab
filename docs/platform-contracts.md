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
Experiment Engine / Scenario / Budget
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

## Algorithm Plugin Contract V1

A new backend-neutral algorithm implements only:

```python
metadata: AlgorithmMetadata
reset(state: MetroPlanningState) -> None
act(state: MetroPlanningState) -> Decision
```

Algorithms do not receive the viewer, HTTP server, replay writer, experiment runner or Mini Metro mediator.

The plugin registry rejects duplicate IDs, incompatible problem IDs and incompatible problem-contract versions. This is the future loading boundary for drop-in algorithms.

## Migration rule

Existing Greedy / Balanced / Rescue planners remain untouched while this contract is introduced. They still use the legacy structured observation until each algorithm is migrated deliberately.

This prevents a platform refactor from silently changing benchmark results.

## Next contract milestones

1. migrate one existing baseline through the new problem contract and prove paired behavioral equivalence;
2. add a stable action contract that removes backend-specific path/station indexing;
3. expose explicit compute budgets and decision latency in the benchmark contract;
4. define problem families rather than a single difficulty axis;
5. add plugin discovery/loading only after the in-process contract is proven stable;
6. keep Viewer/Battle as diagnostic instruments over the same experiment state rather than separate game logic.
