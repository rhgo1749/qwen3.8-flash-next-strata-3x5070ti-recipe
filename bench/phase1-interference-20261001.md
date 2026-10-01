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

Incomplete diagnostic/retry files are intentionally not part of the retained evidence set.

## Phase 1 status after this campaign

This campaign satisfies the core matched target-lane interference gate for:
- solo vs +1 vs +2 active lanes
- high exact-prefix reuse
- zero prefix reuse
- short vs longer cold context
- warm target under cold-long peer traffic
- scheduler-visible and scheduler-bypassed controls
- per-lane GPU telemetry after physical-GPU binding repair

Still open before Phase 1 can be called complete:
- a deliberately controlled expert-miss / expert-residency perturbation if we want causal separation from host/PCIe pressure
- the remaining workload matrix evidence: mixed text/vision overlap, M>N overload on trace schema 2, cancellation/client disconnect, malformed request, and lane-failure recovery
- optional wall-power capture if a hardware power meter is available during the retained campaign

The serving scheduler is not changed by these measurements. Phase 2 should use only signals that survive the remaining validation work.
