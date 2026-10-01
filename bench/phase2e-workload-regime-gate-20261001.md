# Phase 2E workload-regime gate — 2026-10-01

## Decision

**Do not add workload-regime adaptation.**

The promoted fixed policy, `balanced-additive-new-prefill-retained-state-proxy-v1`, remains balanced across a persistent short -> long -> short workload transition. The conditional Phase-2E branch is therefore not triggered by current evidence.

## Experiment

One supervisor stays alive for all six waves so affinity history and retained lane state accumulate across regime changes.

Sequence:

1. short A: 2 waves, 6 fresh sessions/wave, 60 facts, 32-token turn 1, 64-token continuation;
2. long: 2 waves, 6 fresh sessions/wave, 900 facts, 32-token turn 1, 192-token continuation;
3. short B: 2 waves, same short settings as step 1.

Runtime is the promoted Strata-Lanes main `0f23d435dda9`. No scheduler restart occurs between the three regime blocks.

## Result

Every one of the six waves places new sessions exactly **2/2/2**.

| Regime | Wave | Starts | Max lane share | Continuation TG |
|---|---:|---:|---:|---:|
| short A | 1 | 2/2/2 | 1/3 | 43.64 tok/s |
| short A | 2 | 2/2/2 | 1/3 | 69.49 tok/s |
| long | 1 | 2/2/2 | 1/3 | 104.03 tok/s |
| long | 2 | 2/2/2 | 1/3 | 85.18 tok/s |
| short B | 1 | 2/2/2 | 1/3 | 69.19 tok/s |
| short B | 2 | 2/2/2 | 1/3 | 45.43 tok/s |

All wave correctness gates pass. The return from long back to short also remains balanced, so accumulated long-regime state does not create a new-session attractor when the workload contracts again.

Absolute throughput and latency vary materially by regime and run, as expected. This gate is about whether those regime changes require a different placement policy; the retained evidence does not show that they do.

## Phase-2E outcome

- fixed policy remains balanced under short workload: **yes**;
- fixed policy remains balanced under long workload: **yes**;
- fixed policy survives a persistent short -> long -> short transition: **yes**;
- workload-specific scheduler adaptation justified now: **no**.

Keep one fixed promoted placement policy. Re-open Phase 2E only if a future held-out workload shows repeatable imbalance or a policy-specific performance regression that cannot be explained by normal runtime variance.
