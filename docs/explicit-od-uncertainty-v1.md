# Explicit OD Uncertainty V1

`explicit-od-uncertainty-v1` tests whether a fixed metro line design remains effective when realized OD demand differs from the nominal planning matrix.

## Research boundary

The Static Design V1 algorithm receives **only the nominal instance**. The platform freezes a separate set of seeded demand realizations and uses them only after the line plan has been returned. This prevents an algorithm from selecting a network with oracle knowledge of the exact evaluation futures.

V1 uses two multiplicative demand shocks:

- a common system-wide shock that changes total demand level;
- an OD-pair-specific shock that changes the directional demand distribution.

The perturbed matrices are not renormalized, so uncertainty in total demand volume is preserved. V1 keeps the nominal positive-OD support and does not invent new OD markets.

## Evaluation

For every algorithm and base seed the same frozen future set is used. Results report separately:

- nominal coverage and generalized cost;
- out-of-sample mean coverage and generalized cost;
- worst realized coverage and generalized cost;
- cross-scenario variability;
- design compute time.

There is no weighted composite score.

Every nominal matrix and every evaluation realization is written to `results.json`, including scenario keys, so the exact robustness test can be reconstructed later.

## What V1 does not claim

V1 is a robustness-evaluation track for fixed designs. It does not yet expose scenario sets to algorithms, implement stochastic programming or robust optimization, provide adaptive recourse, change infrastructure during a scenario, or model forecasting distributions calibrated from a real city.

A future stochastic-design contract may deliberately expose a training/planning scenario set. If added, its evaluation futures must remain separate and unseen, analogous to a train/test split.

## CLI

```bash
mini-metro-static-uncertainty \
  --algorithms geometry-nearest-v1 od-demand-chain-v1 \
  --seeds 42 314 2026 \
  --scenario-count 8
```

Static external plugins can be loaded through the same Static Design V1 plugin boundary:

```bash
mini-metro-static-uncertainty \
  --plugin my_static_algorithm.py \
  --algorithms my-static-algorithm
```
