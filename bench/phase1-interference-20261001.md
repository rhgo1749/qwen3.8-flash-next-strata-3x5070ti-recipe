# Phase 1 matched cross-lane interference — 2026-10-01

This note records the first reference-host Phase 1 interference campaign for the 3-lane Strata deployment after the per-lane telemetry fix.

## Reference configuration

- Strata fork commit: `e947183a6a819dfe567a6bfbb87e5a2528590a8e` (PR #15 included)
- 3 x RTX 5070 Ti, one engine per lane
- lane 0 / GPU 0: PCIe x8, target lane
- lane 1 / GPU 1: PCIe x4, vision-capable
- lane 2 / GPU 2: PCIe x8
- lane contexts: 262144 each
- KV budget: 786432 aggregate
- shared pinned expert arena: 50,294,988,800 bytes
- direct-lane peer order: lane 2 first, then lane 1
- synthetic prompts only; prompt text is not retained in the result files
- client TTFT is the first meaningful SSE model delta, excluding keep-alive comments and role-only chunks

The telemetry fix was verified live before retaining measurements: private lane metrics reported x8 / x4 / x8 for lanes 0 / 1 / 2 respectively.

## Main result

The target lane has a repeatable non-additive slowdown when the other lanes are active. The effect survives scheduler removal, exact-prefix reuse, zero prefix reuse, and a longer cold prompt.

| experiment | target cache | reps / arm | solo TG | +1 TG | +2 TG | +1 decode vs solo | +2 decode vs solo |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| public scheduler, warm short | 2327 tokens | 6 | 70.8 tok/s | 61.3 | 60.0 | +15.9% | +17.8% |
| direct lane, warm short | 2327 tokens | 6 | 68.2 tok/s | 63.6 | 56.5 | +7.3% | +20.7% |
| direct lane, cold short | 0 tokens | 6 | 71.3 tok/s | 65.2 | 60.5 | +9.7% | +17.7% |
| direct lane, cold long | 0 tokens | 3 | 68.3 tok/s | 63.4 | 60.0 | +7.4% | +13.6% |
| warm short target + cold-long peers | 2327 tokens | 3 | 64.9 tok/s | 62.4 | 57.3 | +3.9% | +13.7% |

The strongest repeatable result is the three-lane arm: across the scheduler-visible warm run and the direct warm/cold controls, target decode time rises by roughly 14–21% while the target request itself is held fixed.

## Prefill and TTFT

For the direct cold-short control, target prefill is about 1.82 s solo. One peer leaves it essentially unchanged, while two peers raise it to about 2.12 s (+16.4%). For the cold-long control, target prefill is about 11.51 s solo and 11.81 s with two peers (+2.6%).

For the direct warm-short run, only five new prompt tokens are read after 2327 cached tokens. Mean prompt time rises from 55.3 ms solo to 79.5 ms with two peers (+43.7%), although the absolute increase is small compared with decode time.

Client token TTFT follows the same direction in the clean direct warm run: median 86.4 ms solo, 100.3 ms with one peer, and 116.6 ms with two peers.

The public scheduler warm run contains one 599 ms solo TTFT outlier. It is retained in raw evidence; summaries use the median for TTFT rather than deleting that observation.

## What the data suggests

The slowdown is not explained by a collapse in target expert-cache hit rate. Across the retained runs the target hit rate stays broadly around 0.78–0.81, including the +2 arms.

The telemetry-fixed warm scheduler run also shows system pressure increasing with concurrency while target decode slows: target/host CPU activity and aggregate PCIe traffic rise as one and then two peer lanes become active. In that run, decode time correlates positively with sampled CPU pressure and aggregate PCIe RX traffic (about 0.71 and 0.73 respectively across 18 arm observations). These are correlations, not a causal decomposition.

The current evidence is therefore consistent with shared host/PCIe contention being a material component of cross-lane interference. It does not prove that PCIe bandwidth alone is the bottleneck, and the campaign did not independently force expert-cache miss rate while holding all other variables constant.

## Scheduler check

The scheduler-visible campaign and the direct-port control point in the same direction. Bypassing the scheduler does not remove the slowdown, so queue selection itself is not sufficient to explain it.

The scheduler trace records:
- exact queue entry/admission/release timing
- selected lane and selection reason
- active-lane count at selection
- prompt-history reuse estimate
- completion outcome
- streaming first-response-byte timing

For strict TTFT analysis, client-side first meaningful SSE token remains the preferred measurement.

## Correctness and workload gates

The performance campaign is paired with the existing 0.1.30 serving campaign and current-main correctness checks rather than treating interference measurements as the only Phase 1 evidence.

- The promoted 0.1.30 oversubscription path already retains synchronized `M=3,4,6,9` request runs with exact queue admission/service timing, common-wall throughput, utilization and FIFO/fairness summaries.
- Long-window reference-host validation already completed three overlapping 141k-145k-token requests without context overflow, CUDA OOM or lane death.
- Agent/tool-call soak already covered malformed inputs, cancellation recovery and concurrent tool requests.
- Current `Strata-Lanes@e947183` full serve regression passes 130 tests with 5 expected skips. Coverage includes session-affinity continuation, vision-only lane selection, vision affinity rebinding, exclusion of a wrapper-alive/child-dead lane, engine error propagation and engine restart after unexpected exit.
- A current-main live text smoke returned HTTP 200 on a normal text lane.
- A current-main live valid 64x64 BMP vision request returned HTTP 200 on lane 1, the configured vision-capable lane.
- The retained two-turn live smoke stayed on the same lane for both turns (lane 0 in that run); turn 2 reported 56 cached prompt tokens, confirming lane-local continuation reuse.
- A malformed live request returned HTTP 400.
- The reproducible live smoke records a streaming client disconnect releasing all lane leases within four 250 ms status polls; the immediately following request returned HTTP 200.

The live checks above are operational smoke evidence, not benchmark samples, and are intentionally not mixed into the performance aggregates. They are reproducible with `bench/phase1_correctness_smoke.py`; the retained output is `bench/raw/phase1-20261001/phase1-correctness-smoke-e947183.json`.

## Raw evidence retained

Canonical retained files:

- `bench/raw/phase1-20261001/strata-phase1-warm-client-telemetryfix.jsonl`
- `bench/raw/phase1-20261001/strata-phase1-warm-trace-162253.jsonl`
- `bench/raw/phase1-20261001/phase1-direct-warm-short-warm-short-telemetryfix.jsonl`
- `bench/raw/phase1-20261001/phase1-direct-cold-short-cold-short-v1.jsonl`
- `bench/raw/phase1-20261001/phase1-direct-cold-short-cold-short-v2.jsonl`
- `bench/raw/phase1-20261001/phase1-direct-cold-long-cold-long-v1.jsonl`
- `bench/raw/phase1-20261001/phase1-direct-warm-short-cold-long-v1.jsonl`
- `bench/raw/phase1-20261001/phase1-summary-20261001.json`
- `bench/raw/phase1-20261001/phase1-correctness-smoke-e947183.json`

Incomplete diagnostic/retry files are intentionally not part of the retained evidence set.

## Phase 1 acceptance

The combined evidence satisfies the Phase 1 acceptance contract:

1. repeatable 1/2/3-request scaling and `M > N` overload paths exist;
2. cold, warm and cache-reuse state are explicit;
3. queue delay, token TTFT, E2E, throughput and tail-oriented overload summaries are captured;
4. exact engine reuse plus the supervisor's explicitly approximate routing-history reuse/new-prefill signals are retained;
5. scheduler decisions and component state are auditable in trace schema 2;
6. matched solo / +1 / +2 controls show material, repeatable cross-lane coupling even with the scheduler bypassed;
7. long context, multi-turn continuation, text/vision capability routing, malformed input, cancellation/disconnect recovery and lane/engine failure handling are covered;
8. commit, config, topology and run metadata are sufficient to reproduce the retained measurements;
9. the independent-lane 0.1.30 baseline remains rerunnable as the control for Phase 2.

A deliberately forced expert-residency/miss perturbation would still be useful for **causal decomposition**, but it is no longer required to establish that shared-pressure coupling is material because the retained cold-long peer run already supplies a higher host-traffic regime. Likewise, wall-meter power would improve energy analysis but is not needed for the serving decision gate.

The serving scheduler is unchanged by Phase 1. The correct Phase 2 implication is narrow: retain the current local/session-aware baseline, then test whether a small shared-pressure term improves decisions out of sample. The correlations above are predictive candidates, not proof that PCIe bandwidth, CPU pressure or any one resource is the sole physical cause.
