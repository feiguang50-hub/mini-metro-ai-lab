# Passenger Assignment V1

## Purpose

Explicit OD Demand V1 answers **who wants to travel from where to where**. Passenger Assignment V1 answers the next question: **given one candidate line network, how would that demand use it?**

The separation is deliberate. Demand should not change just because an assignment algorithm or simulator backend changes.

## V1 model

Passenger Assignment V1 uses a static, deterministic all-or-nothing assignment.

For each OD pair:

1. each `(station, line)` pair is a graph state;
2. adjacent stations on the same line are connected by ride edges;
3. lines sharing the same station are connected by transfer edges;
4. ride-edge cost is Euclidean station distance;
5. every transfer adds one fixed `transfer_penalty`;
6. the complete OD flow is assigned to one minimum-generalized-cost path;
7. demand with no feasible path is explicitly retained as unserved demand.

This is the smallest useful passenger-assignment model for line-planning research. It is intentionally easy to audit before adding behavioral or operational complexity.

## Outputs

`assign_passengers(...)` returns:

- assignment for every OD pair;
- served and unserved trips;
- direct and transfer trips;
- generalized path cost;
- physical ride-distance proxy;
- station sequence;
- line sequence;
- per-line passenger load;
- directional per-segment passenger load;
- demand-weighted generalized cost and ride distance.

Direction is preserved in segment loads. `A -> B` and `B -> A` are different load records.

## Determinism and tie-breaking

V1 uses deterministic graph construction and Dijkstra-style minimum-cost routing. Candidate lines and adjacency lists are sorted so the same demand, geometry, line plan, and transfer penalty reproduce the same assignment.

When two routes have equal generalized cost, the search prefers fewer transfers and then fewer graph hops before deterministic lexical ordering resolves the remaining tie.

## Units

Ride cost is Euclidean distance in the coordinate units supplied by `DemandNode`. `transfer_penalty` uses the same generalized-cost unit.

This is an abstract planning cost, not yet minutes. A later service/frequency layer may replace segment distance with travel time and add waiting time while preserving the same OD and assignment result boundaries.

## What V1 deliberately excludes

Passenger Assignment V1 is not a full behavioral transit assignment model. It does not yet include:

- line frequency or timetable;
- expected waiting time;
- vehicle capacity constraints;
- crowding-dependent route choice;
- stochastic path choice;
- k-shortest path splitting;
- fares;
- walking/access links;
- elastic demand or competing travel modes;
- dynamic within-period reassignment.

Those belong in later assignment versions rather than hidden heuristics inside V1.

## Research rationale

All-or-nothing shortest/generalized-cost passenger assignment is a common baseline in transit network design because it retains OD structure and transfer penalties while remaining computationally transparent. More advanced models can distribute an OD flow across several alternatives, include headways, or use stochastic choice, but they add assumptions and calibration requirements that are premature for the first explicit-demand benchmark.

## Next integration step

Once this contract passes qualification, the next slice should build a runnable **Explicit OD Static V1** benchmark family:

1. freeze station geometry and an `ODDemandMatrix` per seed;
2. let an algorithm propose a line plan through the existing problem/action plugin boundary or a dedicated static-design boundary;
3. run Passenger Assignment V1 against the proposed network;
4. score demand coverage, directness, passenger generalized cost, load concentration, and operator-side line length separately;
5. store the complete demand instance and assignment protocol in experiment artifacts.

This benchmark should remain separate from Classic/Stress simulator leaderboards because it asks a different mathematical question.
