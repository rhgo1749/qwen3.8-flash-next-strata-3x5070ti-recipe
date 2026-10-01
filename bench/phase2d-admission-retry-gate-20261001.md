# Phase 2D admission + retry gate — 2026-10-01

## Decision

**Do not promote the simple bounded-wait admission challenger for workloads where every offered request must complete as soon as possible.**

A 7.5 s new-session wait budget is useful when deferred requests are allowed to leave the immediate service path: before retry accounting, it sharply bounds the latency of the requests that remain admitted. But when every HTTP 429 is retried immediately until success, the apparent tail benefit disappears and retry amplification adds overhead.

The production default therefore remains `unbounded-wait-v1`.

The benchmark-only implementation used for this gate is retained on Strata-Lanes branch/commit:

- branch: `phase2d/bounded-admission`
- commit: `377fd535af8a`

It is **not promoted to main** by this result.

## Challenger semantics

The benchmark challenger changes only new-session admission:

- an idle compatible lane still routes immediately;
- a new session may wait up to the configured budget;
- if no lane becomes available before the budget expires, the supervisor returns HTTP 429 with a retryable admission-deferred result;
- existing-session affinity is exempt from admission defer and continues waiting for its remembered lane.

Placement remains the promoted `balanced-additive-new-prefill-retained-state-proxy-v1` policy.

Targeted tests plus the full serve suite passed on the challenger:

- targeted multi-GPU tests: 59 passed;
- full serve regression: 139 passed, 5 skipped.

## Preliminary no-retry result

The first experiment treats HTTP 429 as a real defer outcome and does **not** force every offered request to complete in the same burst.

### 5 s budget

- M=3: 100% accepted;
- M=4: 95.0% accepted;
- M=6: 58.3% accepted;
- M=9: 40.7% accepted.

At M=9, accepted-request p95 improves sharply relative to unbounded baseline:

- queue p95: 15.37 s -> 4.37 s;
- token TTFT p95: 18.87 s -> 8.67 s;
- E2E p95: 22.45 s -> 12.79 s.

However, the acceptance cost is too high for a general production default.

### 7.5 s budget

The less aggressive 7.5 s budget preserves more work:

- M=4: 100% accepted;
- M=6: 95.8% accepted;
- M=9: 55.6% accepted.

At M=9:

- queue p95: 15.37 s -> 6.97 s;
- token TTFT p95: 18.87 s -> 9.05 s;
- E2E p95: 22.45 s -> 12.79 s;
- successful accepted-request goodput: 102.5 -> 101.4 tok/s.

This establishes that bounded admission can protect the latency of the work that remains in the immediate service path. It does **not** yet establish that total workload completion improves.

## Retry-aware gate

To test the stronger claim, every logical request keeps the same session ID and retries immediately after each 429 until it succeeds. Metrics are measured from the **original logical submission** through the final successful completion.

Only the informative overload points are repeated:

- M=6: 4 runs / 24 logical requests;
- M=9: 3 runs / 27 logical requests.

Both unbounded and 7.5 s bounded arms use the same retry-aware client harness and the same promoted placement scheduler.

### M=6

| Metric | Unbounded | Bounded 7.5 s | Change |
|---|---:|---:|---:|
| Logical E2E p95 | 15.19 s | 15.05 s | -0.9% |
| Logical TTFT p95 | 11.20 s | 11.23 s | +0.2% |
| Mean run wall | 15.23 s | 14.08 s | -7.5% |
| Mean successful goodput | 100.99 tok/s | 110.16 tok/s | +9.1% |
| Requests retried | 0% | 8.3% | — |
| Attempt amplification | 1.00x | 1.083x | +8.3% |

M=6 is effectively neutral on logical-request tail. The bounded arm happened to show a better mean run wall/goodput in this small sample, but this is not accompanied by a repeatable p95 latency improvement and is not treated as promotion evidence.

### M=9

| Metric | Unbounded | Bounded 7.5 s | Change |
|---|---:|---:|---:|
| Logical E2E p95 | 22.47 s | 22.46 s | ~0% |
| Logical TTFT p95 | 18.72 s | 18.86 s | +0.7% |
| Mean run wall | 21.63 s | 22.34 s | +3.3% |
| Mean successful goodput | 107.00 tok/s | 103.17 tok/s | -3.6% |
| Requests retried | 0% | 40.7% | — |
| Attempt amplification | 1.00x | 1.481x | +48.1% |
| Retry-count p95 | 0 | 2 | — |

All 27 logical requests eventually complete in both arms. Under the bounded challenger, 11/27 logical requests require at least one retry, and p95 reaches two retries.

The key result is that the earlier accepted-request tail improvement disappears once deferred work is required to complete immediately. The bounded arm mostly moves waiting from the supervisor queue into repeated admission attempts.

## Interpretation

This architecture has one active generation per lane and cheap condition-variable waiters. A queued new session does not consume GPU inference capacity while waiting. Therefore, when every request must complete ASAP and retries immediately, rejecting it after a bounded wait does not remove work from the system. It only changes where the same wait occurs and adds request/retry overhead.

Admission control can still be useful, but only when a caller can do something meaningfully different with the defer result, for example:

- reschedule lower-priority work later;
- route it to another serving pool;
- enforce a user-facing latency SLO by failing fast;
- apply a real retry/backoff/deadline policy;
- distinguish interactive from batch/deferrable traffic.

Those are different workload semantics from the all-complete-immediately gate tested here.

## Phase 2D outcome

For the current homogeneous interactive overload workload:

- overload tail is material: **yes**;
- bounded wait protects admitted-request tail: **yes**;
- immediate retry preserves that logical-request tail benefit: **no**;
- immediate retry causes significant amplification at M=9: **yes**;
- promote bounded admission as the production default: **no**.

The next Phase-2D experiment should only proceed if Strata wants an explicit SLO/priority/defer contract. It should compare policies under a workload where a defer result is actually actionable rather than automatically and immediately retried.

## Reproduction

Pre-retry admission A/B:

```bash
python3 bench/phase2d_admission_ab.py ...
```

Retry-aware completion A/B:

```bash
python3 bench/phase2d_retry_completion_ab.py ...
```

Retained client raw, summaries, and exact supervisor traces live under `bench/raw/phase2-20261001/phase2d-*`.
