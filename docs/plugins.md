# External Algorithm Plugins V1

The platform should make a new metro-planning algorithm easy to test without modifying Viewer, Arena, replay or backend code.

External Plugin V1 is intentionally simple: one explicitly selected Python file exports a `PLUGIN_FACTORY` callable that returns a valid `PlanningAlgorithm`.

## Quick start

A runnable example is included at `examples/nearest_pair_plugin.py`.

Arena:

```bash
mini-metro-arena \
  --plugin examples/nearest_pair_plugin.py \
  --algorithms greedy-v1 example-nearest-pair \
  --seeds 42 314 2026 \
  --minutes 2
```

Live viewer:

```bash
mini-metro-lab \
  --plugin examples/nearest_pair_plugin.py \
  --algorithm example-nearest-pair
```

Battle CLI also accepts the same global `--plugin PATH` option.

`--plugin` may be repeated. A supplied directory is scanned only for visible top-level `*.py` files, in deterministic filename order. Nested directories are not recursively executed.

## Minimal plugin shape

```python
from metro_lab.action import NoOpAction, PlanningDecision
from metro_lab.plugin import AlgorithmMetadata
from metro_lab.problem import MetroPlanningState


class MyAlgorithm:
    metadata = AlgorithmMetadata(
        id="my-algorithm",
        name="My Algorithm",
        version="0.1",
        family="heuristic",
        description="My first metro-planning policy.",
    )

    def reset(self, state: MetroPlanningState) -> None:
        pass

    def act(self, state: MetroPlanningState) -> PlanningDecision:
        return PlanningDecision(NoOpAction(), "wait", "example")


PLUGIN_FACTORY = MyAlgorithm
```

The plugin receives only Problem Contract state and returns Action Contract decisions. It does not need Mini Metro path indexes, Viewer internals, HTTP state or simulator-private objects.

## Validation before entry

A plugin is rejected before it enters the algorithm library when:

- `PLUGIN_FACTORY` is missing or not callable;
- the factory does not produce a `PlanningAlgorithm`;
- the problem ID/version is incompatible;
- the Action Contract version is incompatible;
- its algorithm ID duplicates another loaded plugin;
- its ID collides with a built-in or reserved algorithm ID.

Loaded plugins appear in the same runtime algorithm catalog as built-in algorithms with status `external`.

## Reproducibility

The loader computes SHA-256 for the selected plugin entry file. The algorithm catalog exposes the entry filename and hash so experiment artifacts can identify the exact source entry used for a run.

V1 treats a plugin as a file entry point. If that file imports extra local modules or external packages, those dependencies are not yet content-addressed by the entry hash. A future packaged-plugin format can strengthen this provenance boundary.

## Trust boundary

Loading a Python plugin executes Python code with the permissions of the current Mini Metro AI Lab process. Contract validation controls the algorithm interface; it is **not** a security sandbox.

Only load plugin files you trust. Untrusted algorithm execution belongs in the future isolated runner together with hard compute and memory limits.

## Design target

A contributor who understands the mathematical problem should be able to copy the example, implement `reset` and `act`, then obtain a benchmark result without learning the Viewer, server, replay or Mini Metro backend internals.
