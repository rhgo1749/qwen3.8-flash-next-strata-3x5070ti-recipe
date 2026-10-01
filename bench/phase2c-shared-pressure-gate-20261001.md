# Phase 2C shared-pressure gate — 2026-10-01

## Decision

**Do not add a CPU/PCIe/shared-pressure coupling coefficient to the placement scheduler.**

The retained Phase-1 evidence still shows material cross-lane interference, but the Phase-2C held-out test does not show incremental predictive value from continuous CPU/PCIe telemetry beyond a much simpler observable concurrency signal. The next serving-control step should therefore be Phase 2D admission/tail control, where active concurrency can affect `route now | bounded wait | defer`, rather than adding a lane-placement term that the current evidence does not justify.

This is a no-go on **additional placement complexity**, not a claim that shared-resource interference is absent.

## Question

Phase 2C asks whether the promoted local/session placement model needs an explicit shared-resource interaction term.

The evidence threshold is intentionally stronger than in-sample correlation:

1. shared interference must be material;
2. a simple observable shared-pressure proxy should predict held-out slowdown;
3. CPU/PCIe telemetry must add held-out predictive value beyond that simpler proxy before it is used in routing;
4. lane-pair-specific placement coupling must not be inferred without lane-pair-identifying evidence.

## Data

Source: retained Phase-1 matched direct-lane interference runs under `bench/raw/phase1-20261001/`.

Five clean matched campaigns contribute 36 concurrent observations:

- cold short target / cold short peers, two independent 3-repetition campaigns;
- cold long target / cold long peers, 3 repetitions;
- warm short target / cold long peers, 3 repetitions;
- warm short target / warm short peers, 6 repetitions.

For each repetition, concurrent target decode time is normalized against the same repetition's solo target. This reduces run-order and baseline-speed drift.

The aligned warm-short/warm-short campaign additionally supplies 18 solo/+1/+2 observations with run-level CPU and PCIe telemetry. Only this aligned-duration campaign is used to test the **incremental** value of continuous telemetry. Cold-long peer runs continue sampling after the short target has already completed, so their run-average telemetry would not be a clean target-overlap feature.

## Held-out workload result

Leave one entire campaign out, fit target slowdown on the remaining campaigns using only active peer count, then predict the held-out campaign.

| Held-out campaign | No-pressure RMSE | Peer-count RMSE | RMSE improvement |
|---|---:|---:|---:|
| cold-long / cold-long | 12.82 pp | 7.07 pp | 44.9% |
| cold-short / cold-short v1 | 13.88 pp | 8.77 pp | 36.8% |
| cold-short / cold-short v2 | 22.44 pp | 14.46 pp | 35.6% |
| warm-short / cold-long | 13.89 pp | 10.24 pp | 26.3% |
| warm-short / warm-short | 17.81 pp | 8.91 pp | 50.0% |

Pooled across all 36 held-out observations:

- no-pressure RMSE: **16.77 percentage points**;
- peer-count RMSE: **9.99 percentage points**;
- RMSE improvement: **40.4%**.

A simple active-concurrency signal therefore generalizes materially better than pretending there is no shared interference.

## Does CPU/PCIe telemetry improve prediction?

Grouped leave-one-repetition-out cross-validation on the aligned warm-short campaign:

| Model | Decode RMSE | MAE |
|---|---:|---:|
| constant | 393.8 ms | 338.8 ms |
| peer count | **245.0 ms** | 222.2 ms |
| peer count + aggregate PCIe RX | 252.8 ms | **216.0 ms** |
| peer count + CPU | 268.6 ms | 244.3 ms |
| peer count + peer PCIe RX | 292.5 ms | 251.9 ms |
| peer count + CPU + aggregate PCIe RX | 268.1 ms | 230.2 ms |

The best telemetry-augmented model by RMSE is `peer count + aggregate PCIe RX`, but its RMSE is **3.2% worse** than peer count alone. The earlier positive CPU/PCIe correlations are therefore useful physical evidence of contention, but they do not clear the held-out predictive-value gate for a routing coefficient.

## Why this is not a lane-specific coupling result

The retained Phase-1 `plus1` arm uses one specific peer lane; the dataset does not contain the symmetric peer-lane-1-only arm needed to identify a pairwise coupling matrix. A fitted lane-pair coefficient would therefore exceed the evidence.

Also, active peer count is largely a **global concurrency condition** for the remaining idle candidates. When the signal does not distinguish candidate lanes, it is more naturally an admission/wait input than a placement score.

## Phase-2C outcome

- material shared interference: **yes**;
- simple active-peer-count proxy generalizes across held-out campaigns: **yes**;
- continuous CPU/PCIe telemetry adds held-out value beyond peer count: **no**;
- add lane-specific CPU/PCIe coupling term now: **no**;
- next step: **Phase 2D admission/tail control**.

The promoted `balanced-additive-new-prefill-retained-state-proxy-v1` placement policy remains unchanged.

## Reproduction

```bash
python3 bench/phase2c_shared_pressure_gate.py \
  --output bench/raw/phase2-20261001/phase2c-shared-pressure-gate.json
```

The script uses only Python's standard library. The machine-readable output records fold metrics, telemetry-model CV, source coverage, limitations, and the go/no-go decision.
