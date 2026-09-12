# Explicit OD Demand V1

## Why this exists

The historical simulator exposes station crowding and passenger destinations through its own game mechanics. That is useful for a dynamic benchmark, but it is not the same thing as an explicit origin–destination demand matrix.

Transit network design and line-planning research commonly represents passenger demand as directional flow `q_ij` from origin `i` to destination `j` over a fixed time period. Passenger assignment is then a separate problem: given a network and those OD flows, determine which lines, transfers, and paths passengers use.

Explicit OD Demand V1 creates that separation in Mini Metro AI Lab.

## Contract

`metro_lab/demand.py` defines:

- `DemandNode`: a backend-neutral demand node with coordinates and optional production/attraction weights.
- `ODFlow`: one directional positive demand pair.
- `ODDemandMatrix`: a sparse matrix of OD flows over a declared time period.
- `explicit_od_matrix(...)`: validated construction from external or hand-authored data.
- `synthetic_gravity_od(...)`: deterministic research-instance generator.

The contract version is `1.0`.

### Semantics

For an OD flow:

```text
q[i,j] = trips from station i to station j during period_seconds
```

Important properties:

1. Direction matters. `q[i,j]` does not imply `q[j,i]`.
2. Missing pairs mean zero demand.
3. Self-demand is excluded from V1.
4. Demand must be positive and finite.
5. The period is explicit. V1 defaults to 3600 seconds, but the unit is never silently assumed.
6. Every endpoint must belong to the declared station set.

## Synthetic Gravity V1

The generator exists only to create deterministic benchmark instances before real OD datasets are imported. It is **not** presented as a calibrated urban demand model.

For each directional pair it combines:

- origin production weight;
- destination attraction weight;
- Euclidean distance impedance;
- a seeded directional multiplier;
- a seeded sparsity mask.

The resulting positive flows are normalized to a declared `total_trips`. The same nodes, parameters, and seed produce the exact same matrix.

This gives the project a controlled way to test algorithms against explicit directional demand without contaminating the interface with simulator internals.

## What V1 deliberately does not do

OD demand and passenger assignment are separate layers. V1 therefore does **not** yet decide:

- shortest or generalized-cost passenger paths;
- transfer penalties;
- waiting time caused by service frequency;
- capacity-constrained assignment;
- elastic demand or mode choice;
- time-varying OD matrices;
- land-use feedback;
- calibration from AFC/APC/AVL or survey data.

Those mechanisms can be added later without changing what `q[i,j]` means.

## Next layer: Passenger Assignment V1

The next research slice should consume `ODDemandMatrix` plus a candidate line network and report, at minimum:

- served vs unserved demand;
- direct vs transfer demand;
- passenger path distance/time proxy;
- number of transfers;
- edge/line loads;
- a deterministic assignment result suitable for algorithm comparison.

Only after this assignment boundary is stable should Explicit OD become a runnable benchmark family in Arena/Battle. Until then it is a contract foundation, not a claim that the current simulator scenarios already use OD matrices.

## Research grounding

The design follows the standard separation used in transit planning literature: OD matrices define passenger demand, while passenger assignment determines how those OD pairs use a proposed transit network. This matters because network topology can only be evaluated meaningfully against OD pairs when origin and destination are retained jointly instead of replacing demand with independent station crowd totals.
