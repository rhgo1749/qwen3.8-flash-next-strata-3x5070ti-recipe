# Phase 2D overload baseline — 2026-10-01

## Purpose

Establish the overload/tail baseline for the promoted production scheduler before adding any admission behavior.

Runtime:
- Strata-Lanes production main after Phase 2B promotion;
- `balanced-additive-new-prefill-retained-state-proxy-v1`;
- three independent RTX 5070 Ti lanes;
- exact server-side queue/service timing from trace-schema-2 leases;
- fresh independent sessions in synchronized bursts;
- one equalizing warmup session per lane before the measured campaign.

Measured burst sizes and repetitions:
- M=3: 7 runs
- M=4: 5 runs
- M=6: 4 runs
- M=9: 3 runs

Total retained measured requests: **92**.

## Result

| Simultaneous requests | Runs | Requests | Queue p95 | Token TTFT p95 | E2E p95 | Aggregate TG mean |
|---:|---:|---:|---:|---:|---:|---:|
| 3 | 7 | 21 | 3.6 ms | 2.08 s | 7.03 s | 164.7 tok/s |
| 4 | 5 | 20 | 4.17 s | 7.48 s | 11.19 s | 97.9 tok/s |
| 6 | 4 | 24 | 7.74 s | 11.26 s | 15.06 s | 111.9 tok/s |
| 9 | 3 | 27 | 15.37 s | 18.87 s | 22.45 s | 102.5 tok/s |

All 92 requests completed with `finish_reason=length`.

Lane assignments across the campaign were 29 / 32 / 31, so the promoted session-start balancing policy remained globally balanced under overload.

## Tail shape

The decisive transition is M=3 -> M=4.

With three lanes, M=3 fits in one service wave and queue p95 remains a few milliseconds. Adding only one extra simultaneous request forces a second service wave and raises queue p95 to about 4.17 seconds. M=6 produces roughly two full waves and M=9 roughly three; queue p95 grows to 7.74 and 15.37 seconds respectively.

This is evidence for Phase 2D admission/tail control. The problem is no longer lane placement imbalance: it is whether a request should enter a queue whose predicted wait already spans one or more service waves.

## First-run caveat

The first M=3 measured run immediately followed the equalizing warmup and produced only 93.4 tok/s aggregate, while the next six M=3 runs were 168.2–180.2 tok/s. It is retained rather than removed. This inflates the M=3 TTFT/E2E dispersion but does not affect the overload transition: exact queue p95 remains only 3.6 ms for M=3 and jumps by three orders of magnitude at M=4.

## Phase 2D design implication

The first challenger should remain benchmark-only and should not change placement. Admission should be based on **predicted wait horizon**, not GPU identity.

A minimal candidate can classify a new request at queue entry as:

- `route-now`: a compatible lane is idle;
- `bounded-wait`: no lane is idle, but estimated wait is within one service-wave budget;
- `defer`: estimated wait exceeds the configured benchmark wait budget.

The initial experiment should expose the decision and estimated wait without changing production semantics, then compare an enforcing challenger against the current unbounded-wait control. Existing-session affinity should not be broken by this experiment.

## Retained evidence

- `bench/phase2d_overload_baseline.py`
- `bench/raw/phase2-20261001/phase2d-overload-balanced.csv`
- `bench/raw/phase2-20261001/phase2d-overload-balanced-summary.json`
- `bench/raw/phase2-20261001/phase2d-overload-balanced-trace.jsonl`

The retained trace copy is byte-identical to the host-side source trace by SHA-256.
