# Research Workbench V1

Research Workbench V1 turns the static research tracks into a visual, paired-seed experiment surface at `/research.html`.

## What it visualizes

The page supports three frozen benchmark families:

- `explicit-od-static-v1`
- `explicit-od-infrastructure-v1`
- `explicit-od-uncertainty-v1`

Each view uses one shared seed and renders the competing algorithms against the exact same station geometry, OD demand, and family-specific conditions.

The network panels show:

- stations and station IDs;
- strongest OD flows as neutral demand links;
- the actual line plan produced by each algorithm;
- infrastructure barriers when the family exposes them;
- a compact set of family-relevant metrics.

A comparison table keeps passenger service, infrastructure cost, robustness, and compute cost separate. V1 intentionally does not define a weighted composite score.

For uncertainty experiments, the page additionally plots the frozen out-of-sample evaluation scenarios. The algorithm still designs from nominal OD only. Evaluation futures are not passed into the design contract.

## API

`GET /api/research/catalog`

Returns the research-view contract and available families/algorithms.

`GET /api/research/snapshot?family=<static|infrastructure|uncertainty>&seed=<int>`

Builds one deterministic visual research snapshot. The endpoint is local-only under the existing Mini Metro AI Lab server and does not persist or upload state.

## Scope boundary

Research Workbench V1 is a visualization and comparison surface, not a new benchmark family. It does not change benchmark mathematics, algorithm rankings, passenger assignment, infrastructure rules, or uncertainty protocol. The UI consumes the already-versioned research contracts and exposes their differences in a form that can be inspected directly.
