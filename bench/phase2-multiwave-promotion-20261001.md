# Phase 2B persistent multi-wave promotion — 2026-10-01

## Decision

Promote `balanced-additive-new-prefill-retained-state-proxy-v1` from a benchmark-only challenger to the production default for new-session placement. Keep `safe-affinity-live-state-v1` available as the explicit rollback control.

This closes the Phase-2B placement/locality promotion gate. It does **not** close the broader Phase 2 serving-control issue: shared-pressure validation, overload admission/tail control, and workload-regime testing remain later gates.

## Runtime and workload

Runtime under test:

- Strata-Lanes: `b40dc7538249f4b9d79c79a115e18babaace5877`
- three independent RTX 5070 Ti lanes;
- 262144 context per lane, aggregate KV budget 786432;
- 32768 resident KV per lane;
- persistent supervisor within each three-wave campaign;
- six fresh sessions per wave;
- 300 shared-prefix facts;
- 32-token first turn and synchronized 128-token continuation.

Each wave uses fresh session IDs while preserving supervisor affinity history and lane-local retained state from earlier waves. This is the required long-lived-state gate; restarting the supervisor between waves would hide the failure mode being tested.

Only isolated clean campaigns are retained below. An aborted pre-measurement launch and an overlapping duplicate-client attempt were discarded before the promotion comparison.

## Persistent control results

| Policy | Wave 1 starts | Wave 2 starts | Wave 3 starts | TG by wave (tok/s) | Mean p95 queue | Mean p95 token TTFT |
|---|---:|---:|---:|---:|---:|---:|
| safe rollback | 2/2/2 | 0/6/0 | 6/0/0 | 78.77 / 22.27 / 29.55 | 18.48 s | 21.52 s |
| additive | 2/2/2 | 6/0/0 | 0/0/6 | 64.30 / 29.33 / 32.13 | 15.89 s | 18.90 s |
| balanced-additive, campaign 1 | 2/2/2 | 2/2/2 | 2/2/2 | 64.79 / 66.99 / 65.98 | 5.97 s | 9.89 s |
| balanced-additive, campaign 2 | 2/2/2 | 2/2/2 | 2/2/2 | 88.62 / 84.59 / 82.72 | 4.13 s | 7.17 s |

The safe and unbalanced additive policies both reproduce the long-lived single-lane attractor on clean runs: after the first balanced wave, all six new sessions concentrate on one lane in each later wave. Their continuation throughput and tails collapse accordingly.

Balanced-additive does not reproduce that attractor in either independent campaign. Across all six retained balanced-additive waves:

- every wave places starts exactly 2/2/2;
- maximum observed single-lane share is 1/3;
- all underlying correctness/affinity gates pass;
- common-wall continuation TG spans 64.79–88.62 tok/s;
- pooled TG is 75.62 ± 10.81 tok/s across the six waves.

The difference between the two balanced campaigns' absolute throughput levels is treated as host/run variance; the promotion claim is the repeatable absence of progressive concentration together with non-regressed queue/TTFT tails.

## Promotion-gate assessment

The persistent-supervisor gate in `phase2-multiwave-policy-ab.md` requires:

1. **No correctness/affinity failures — PASS.** All 12 retained single-wave client runs across the four campaigns pass their correctness gates.
2. **No progressive session-start concentration — PASS for balanced-additive.** Six of six candidate waves stay 2/2/2. Both controls demonstrate the failure mode instead.
3. **No material p95 queue/TTFT regression — PASS.** Candidate tails remain far below the concentrated control waves.
4. **Repeatable throughput benefit or declared objective — PASS.** The declared objective is stable long-lived session placement without sacrificing continuation service; both independent candidate campaigns retain healthy throughput while controls collapse after concentration.
5. **Same result after retained state accumulates — PASS.** Waves 2 and 3 remain balanced in both candidate campaigns.

## Production semantics after promotion

The promotion changes only new-session selection among eligible idle lanes:

1. hard health/capability filtering remains first;
2. existing-session affinity remains strict and unchanged;
3. affinity reservations, compatible FIFO ordering, vision reservation, and one active generation per lane remain unchanged;
4. for a new session, candidate lanes are ordered first by remembered affinity-session count;
5. equally balanced candidates are ordered by estimated new-prefill bytes plus the retained last-request byte proxy;
6. live-state sequence and rotation remain tie-breakers.

The policy remains GPU/model/index agnostic. No GPU number, model name, or PCIe width is hard-coded.

`safe-affinity-live-state-v1` remains directly selectable as the rollback policy. Other experimental policies continue to require benchmark trace opt-in.

## Retained evidence

Client raw and summaries:

- `bench/raw/phase2-20261001/multiwave-safe/`
- `bench/raw/phase2-20261001/multiwave-additive/`
- `bench/raw/phase2-20261001/multiwave-balanced-r1/`
- `bench/raw/phase2-20261001/multiwave-balanced-r2/`

The earlier fresh-state policy campaign remains historical evidence in `bench/phase2-online-policy-ab-20261001.md`; its former no-promotion decision was correct for the evidence available at that time and is superseded by this persistent-state gate.

## Next gate

Phase 2C subsequently completed as an evidence-only gate; see `phase2c-shared-pressure-gate-20261001.md`. Active peer count generalizes as a shared-concurrency slowdown signal, but sampled CPU/PCIe telemetry does not improve held-out prediction beyond that simpler proxy, so no placement coupling coefficient is added. The next runtime gate is Phase 2D admission/tail control using bounded `route now | wait | defer` decisions under overload.
