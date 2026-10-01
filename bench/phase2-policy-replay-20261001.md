# Phase 2A one-step scheduler replay — 2026-10-01

This note is the first Phase-2 placement analysis over the retained Phase-1 trace. It is deliberately a **one-step snapshot replay**, not a counterfactual serving simulator.

## Input and scope

Input:

- `raw/phase1-20261001/strata-phase1-warm-trace-162253.jsonl`
- trace schema: 2
- measured Strata-Lanes commit: `e947183a6a819dfe567a6bfbb87e5a2528590a8e`
- 39 scheduler decisions
- 36 decisions selected by existing session affinity
- 3 decisions selected by new-session live-state placement

Each replay policy sees the exact recorded lane snapshot at one real decision. If a policy chooses another lane, later lane/session/cache state would diverge from the recorded run. Therefore the replay can answer **whether policies make distinct decisions and whether the trace exposes their required inputs**. It cannot claim that an alternate policy would have improved latency or throughput.

The machine-readable result is `raw/phase2-policy-replay-20261001.json`.

## Policy disagreement

| policy | agreement with current safe policy | disagreements / 39 |
| --- | ---: | ---: |
| session affinity then cache-aware fallback | **94.9%** | **2** |
| least retained live state | 51.3% | 19 |
| round-robin first-free | 48.7% | 20 |
| cache-aware | 46.2% | 21 |
| multiplicative new-prefill × retained-state proxy | 43.6% | 22 |
| additive new-prefill + retained-state proxy | 41.0% | 23 |

The retained warm trace is dominated by continuation turns. The strongest first-order result is therefore not that a more complicated score is better; it is that **discarding session locality changes roughly half of the observed decisions**, while a session-first/cache-aware policy reproduces the current control on 37 of 39 decisions.

This is evidence for keeping session locality as a strong baseline in live Phase-2 comparisons. It is not evidence that strict affinity is globally optimal.

## Signal coverage found insufficient for live policy evaluation

The old trace is enough for one-step locality disagreement, but not for an honest wait-vs-recompute or admission model. In particular it lacked:

- per-lane affinity-session count for balancing new session starts;
- active in-flight request size/progress distinct from retained post-request state;
- lane-specific compatible queued work and queue age;
- time-aligned shared-pressure input at the scheduler decision;
- engine-truth per-lane prefix/KV overlap.

The additive and multiplicative replay variants therefore use `live_request_bytes` only as a retained-state/load proxy. Bytes are not engine-truth work and must not be interpreted as compute cost.

Strata-Lanes PR #16 addresses the first three observability gaps without changing the production placement policy. Engine-truth cache overlap and a validated shared-pressure term remain later evidence-gated work.

## Phase-2 implication

The next live comparison should keep the current safe policy as the rollback control and evaluate strong simple challengers only after the new work/queue signals are captured. The initial objective is to measure whether session-first cache-aware placement or another simple policy improves a declared end-to-end/tail metric; the Phase-1 shared-pressure residual justifies testing a small coupling term later, not assuming one now.
