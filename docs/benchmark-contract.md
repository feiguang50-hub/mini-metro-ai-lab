# Benchmark Contract V1

Mini Metro AI Lab compares metro line-planning algorithms under a shared problem, scenario and simulation protocol. Benchmark Contract V1 adds an explicit **compute-cost dimension** so future search, optimization and learned planners cannot appear superior merely because they silently receive much more computation.

## Principle

Solution quality and compute cost are separate research dimensions.

The platform reports both. It does **not** combine deliveries, risk and runtime into a weighted magic score.

A claim such as “algorithm A is better than algorithm B” should therefore state the comparison regime, for example:

- higher solution quality under the same compute budget;
- similar solution quality at lower compute cost;
- higher unconstrained quality, with the additional compute cost reported explicitly.

## Version

`metro_lab.benchmark.BENCHMARK_CONTRACT_VERSION = 1`.

Experiment config, JSON output and replay metadata expose this version independently from the Simulation Protocol version and artifact schema version.

## Compute accounting

V1 measures planner **wall-clock elapsed time** with a monotonic high-resolution clock.

The compute ledger includes:

1. planner construction;
2. planner `reset`;
3. every `act` decision call.

Construction and reset are included so an algorithm cannot legitimately move expensive precomputation out of `act` and make its decision latency look artificially cheap.

For each episode the platform records:

- setup compute milliseconds;
- number of decision calls;
- total decision compute milliseconds;
- total planner compute milliseconds;
- compute milliseconds per simulated minute;
- mean decision latency;
- nearest-rank p95 decision latency;
- maximum decision latency.

The p95 and maximum are reported because an average can hide rare but operationally important slow decisions.

## Optional budgets

A run may declare:

- `decision_ms`: maximum desired wall-clock time for one decision;
- `episode_ms`: maximum desired total planner compute for one episode, including setup.

V1 records:

- number and rate of decision-budget violations;
- whether total episode compute exceeded the episode budget;
- episode and summary compliance rates.

An unbounded run still records compute cost; it simply has no budget violations.

## Why V1 does not kill an algorithm at the deadline

A safe hard timeout is not the same thing as checking elapsed time after a Python call returns. Forcibly interrupting arbitrary in-process Python code can leave shared simulator state or locks inconsistent.

Therefore Benchmark Contract V1 is an **auditing contract**, not an adversarial sandbox. Hard compute enforcement belongs in a later isolated runner with a process boundary, where the platform can terminate an algorithm process without corrupting the experiment engine.

The later runner should also address memory limits, spawned workers and other resources that simple wall-clock measurement cannot fully police.

## Hardware comparability

Wall-clock timings are hardware- and load-dependent.

Compute metrics are directly comparable only when algorithms are measured under the same runner/hardware configuration and broadly comparable system load. Published benchmark artifacts should record the runner profile once standardized hardware profiles are introduced.

Until then:

- use paired runs on the same machine for compute comparisons;
- do not treat a latency measured on one computer as a universal property of the algorithm;
- keep solution-quality claims reproducible independently through seeds, scenarios and protocol versions.

## Ranking discipline

The Arena's solution-quality ranking remains quality-first. Compute results are shown in a separate table.

A future compute-constrained leaderboard may exclude non-compliant runs, but it should still retain raw quality and raw compute measurements rather than collapsing them into one opaque score.

## Research path

Benchmark Contract V1 establishes measurement and auditability. Planned extensions include:

1. isolated algorithm processes with hard per-decision and per-episode deadlines;
2. standardized runner/hardware profiles;
3. memory and parallel-worker accounting;
4. explicit search budgets such as rollouts/nodes where algorithm families expose meaningful operation counts;
5. Pareto-frontier views across solution quality, robustness and compute cost.
