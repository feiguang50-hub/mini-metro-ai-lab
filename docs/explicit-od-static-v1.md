# Explicit OD Static V1

## What this benchmark asks

Classic/Stress ask a dynamic control question: as a simulated city evolves, what action should a planner take next?

Explicit OD Static V1 asks a different mathematical question:

> Given fixed station geometry, a fixed directional OD demand matrix, and a fixed network-design budget, what line network should be built?

The results therefore live on a separate benchmark track and must not be mixed into the Classic/Stress leaderboard.

## Problem family

`explicit-od-static-v1` currently exposes only:

- **Geometry**: station locations and line segment lengths;
- **Demand**: an explicit directional `q[i,j]` OD matrix.

The design budget limits the number of lines and stations per line. It is a feasibility constraint, not a claim that vehicle capacity, frequency, construction cost, tunneling, barriers, uncertainty, or land-use evolution are modeled.

## Reproducible instances

Each seed deterministically generates:

1. station coordinates;
2. station production/attraction weights;
3. a synthetic directional OD matrix;
4. the same declared line/station design budget;
5. the same passenger transfer penalty.

The synthetic demand generator is a benchmark generator, not a calibrated city model.

Artifacts store the complete station geometry and OD flow table for every seed. A historical experiment therefore remains interpretable even if a later generator version changes.

## Static Design Contract V1

A static algorithm receives one `ExplicitODStaticInstance` and returns a tuple of `AssignmentLine` objects.

It must obey:

- at least one line;
- no more than `max_lines`;
- each line between the declared minimum and maximum station count;
- only station IDs from the instance;
- unique line IDs;
- the Passenger Assignment V1 line validity rules.

This is intentionally separate from the dynamic `MetroPlanningState -> PlanningDecision` plugin contract. A static network design is not disguised as a sequence of simulator ticks.

## Reference baselines

V1 ships two deterministic reference algorithms.

### `geometry-nearest-v1`

Builds a nearest-neighbor station ordering from geometry only and splits it into legal lines with one transfer station shared between consecutive lines.

It never reads OD demand. This is the geometry-only control baseline.

### `od-demand-chain-v1`

Starts from the station with the largest inbound + outbound demand, then greedily extends the ordering using bidirectional OD affinity adjusted by distance.

It is deliberately simple. Its purpose is to prove that the benchmark can distinguish a demand-aware design from a geometry-only design, not to establish a state-of-the-art algorithm.

## Passenger evaluation

Every proposed network is evaluated by Passenger Assignment V1:

- static deterministic all-or-nothing assignment;
- Euclidean ride cost;
- fixed transfer penalty;
- unserved OD demand remains explicit.

Reported passenger-side metrics include:

- demand coverage;
- direct-trip share;
- transfer-trip share;
- mean generalized cost over served trips;
- mean ride distance over served trips;
- maximum line-load share.

Operator-side metrics include:

- line count;
- total physical line length;
- design compute time.

## No composite score

V1 intentionally defines **no weighted composite score**.

Coverage, generalized passenger cost, directness, load concentration, network length, and compute cost represent different objectives. Combining them requires policy weights. Hiding those weights inside the benchmark would make algorithm rankings arbitrary.

Experiments therefore report the Pareto-relevant metrics separately. Future research may define named objective profiles with explicit weights or constraints, but those would be new versioned benchmark protocols.

## CLI

After bootstrap/install:

```bash
mini-metro-static-od
```

The default run evaluates both built-in baselines on five paired seeds.

Example:

```bash
mini-metro-static-od \
  --algorithms geometry-nearest-v1 od-demand-chain-v1 \
  --seeds 42 314 2026 4096 65537 \
  --station-count 10 \
  --max-lines 2 \
  --max-stations-per-line 6 \
  --transfer-penalty 20
```

Use `--json` for machine-readable stdout and `--no-save` when artifacts are not wanted.

By default artifacts are written under:

```text
output/static-od/<timestamp>-explicit-od-static-v1-.../
```

Each run contains:

- `config.json`: benchmark contracts, algorithms, seeds, and generator parameters;
- `results.json`: complete frozen instances, line plans, episode metrics, and summaries;
- `episodes.csv`: scalar metrics for analysis;
- `summary.md`: human-readable comparison with no composite score.

## Next research steps

The next algorithmic work should happen on this benchmark rather than adding realism at random. Strong candidates include:

1. OD-aware insertion / local search;
2. multi-line neighborhood search and 2-opt/relocation moves;
3. Pareto search over passenger cost vs network length;
4. exact or mixed-integer formulations on small instances for an optimality reference;
5. only after the static geometry+demand problem is understood, add infrastructure barriers/costs or service-frequency/capacity layers as separate versioned dimensions.
