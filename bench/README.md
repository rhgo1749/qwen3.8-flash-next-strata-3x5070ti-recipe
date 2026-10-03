# Benchmark and reporting contract

The **current operational software baseline** is Strata **0.1.38** on fork main `48a51d33a8436c9504dd24c180aa4fc7adcfdd66`, integrated from upstream `99f3dbd0b21d1401b3769e0c0d963913607f380b` (`v0.1.38`). The retained full 0.1.38 architecture campaign was measured at fork commit `8ea68eaab3ee93f1c820f5103d64ca251cfe52b6`; later serving-control/parking changes do not relabel those benchmark measurements. The full campaign reruns independent-lane scaling, workload sensitivity, corrected mixed serving, exact-queue oversubscription, heterogeneous isolation, private↔shared PSS, and three-GPU layer-split.

Current 0.1.38 evidence:

- `strata-0.1.38-campaign.md` — full campaign contract, results, caveats and interpretation;
- `systems-ablation-0.1.38-20261003.csv` — scaling, mixed serving, heterogeneous isolation and PSS;
- `workload-sensitivity-0.1.38-20261003.csv` — cold PP and warm decode summaries;
- `oversubscription-0.1.38-summary-20261003.csv` — corrected 3/4/6/9 request summaries;
- `layer-split-ab-0.1.38-20261003.csv` — current independent-lane ↔ layer-split comparison;
- `raw/0.1.38-20261003/` — retained non-contaminated raw JSON and machine-readable summary;
- `docs/strata-0.1.38-full-campaign-20261003.md` — human-readable current full benchmark promotion;
- `docs/strata-0.1.38-promotion-20261003.md` — software-sync compatibility gate and byte-matched bounded prefill A/B.

Historical evidence remains versioned under 0.1.31/0.1.30. The 0.1.30 fixed prompt bytes were not retained, so 0.1.30↔0.1.38 workload values are contract-matched rather than byte-identical; only the separately documented 0.1.31→0.1.38 bounded A/B is used for exact version-level prefill percentages.

Retained 0.1.30 architecture evidence:

- `strata-0.1.30-promotion-20261001.csv` — historical validation/provenance gate;
- `systems-ablation-0.1.30-20261001.csv` — historical scaling, native shared-arena PSS, heterogeneous isolation and mixed serving;
- `workload-sensitivity-0.1.30-20261001.csv` — historical PP/TTFT and warm decode summaries;
- `oversubscription-0.1.30-summary-20261001.csv` — historical 3/4/6/9 request summaries;
- `layer-split-ab-0.1.30-20261001.csv` — historical independent-lane ↔ layer-split A/B.

## Phase 1 cross-lane interference

The post-promotion observability campaign is documented in `phase1-interference-20261001.md`. It keeps one target request on lane 0 and compares solo / +1 / +2 peer-lane activity under scheduler-visible and direct-lane controls. The retained measurements cover exact-prefix reuse, zero reuse, short and longer cold prompts, and warm-target/cold-long-peer stress. Across the main matched controls the three-lane arm repeatedly slows target decode without a corresponding collapse in target expert-cache hit rate; the evidence is consistent with shared host/PCIe contention but does not yet isolate one causal resource. Phase 1 acceptance is complete: the interference evidence is combined with the existing 0.1.30 M>N queue campaign, long-window validation, current-main regression coverage, and a reproducible text/vision/multi-turn/malformed/disconnect live smoke. Machine-readable aggregates are in `raw/phase1-20261001/phase1-summary-20261001.json`, and the current correctness smoke result is in `raw/phase1-20261001/phase1-correctness-smoke-e947183.json`.

## Phase 2 scheduler replay

The first Phase-2A analysis is documented in `phase2-policy-replay-20261001.md`. It replays each retained trace-schema-2 scheduler snapshot independently to measure policy disagreement and signal coverage, without claiming counterfactual performance. On the 39-decision warm Phase-1 trace, 36 decisions are continuation affinity and a session-affinity-then-cache challenger agrees with the current safe control on 37/39 decisions (94.9%); policies that discard affinity change roughly half the choices. The replay also identified missing active-work, per-lane queue/session, shared-pressure and engine-truth cache signals that must be resolved or explicitly approximated before live policy conclusions. Machine-readable output is retained in `raw/phase2-policy-replay-20261001.json`.

Phase 2B promotion evidence is documented in `phase2-multiwave-promotion-20261001.md`. Under the required persistent-supervisor gate, the safe and unbalanced additive controls both develop 6-to-1 new-session concentration on later waves, while `balanced-additive-new-prefill-retained-state-proxy-v1` remains exactly 2/2/2 across six waves from two independent campaigns. The balanced policy therefore passes the placement/locality promotion gate and becomes the production default; `safe-affinity-live-state-v1` remains the explicit rollback control. Raw client evidence is retained under `raw/phase2-20261001/multiwave-*`.

Phase 2C is documented in `phase2c-shared-pressure-gate-20261001.md`. Across leave-one-campaign-out matched slowdown tests, active peer count reduces pooled prediction RMSE by 40.4% versus a no-pressure model, confirming that shared concurrency matters. However, on the aligned warm-short telemetry campaign, adding sampled CPU or PCIe pressure does not improve grouped held-out RMSE beyond peer count alone. No CPU/PCIe placement coupling term is therefore promoted; active-concurrency pressure moves forward as an input to the Phase-2D admission/tail gate instead.

The Phase 2D current-default overload baseline is documented in `phase2d-overload-baseline-20261001.md`. Under balanced-additive placement, 92/92 synchronized requests complete successfully and total lane assignments remain 29/32/31, but exact queue p95 jumps from 3.6 ms at M=3 to 4.17 s at M=4, 7.74 s at M=6, and 15.37 s at M=9. This establishes the admission-control target: prevent multi-wave tail growth without reintroducing placement imbalance or breaking affinity.

The first Phase 2D admission gate is documented in `phase2d-admission-retry-gate-20261001.md`. A benchmark-only 7.5 s bounded-wait challenger substantially reduces the tail of requests that remain admitted, but when every 429 is immediately retried until all logical requests complete, the M=9 logical E2E p95 is unchanged (~22.47 s vs ~22.46 s), logical TTFT p95 is slightly worse, attempt amplification rises to 1.48x, and goodput falls 3.6%. Bounded admission is therefore not promoted for all-complete-immediately interactive overload; a future admission experiment requires an actionable SLO/priority/defer contract rather than automatic immediate retry.

Phase 2E is documented in `phase2e-workload-regime-gate-20261001.md`. On one persistent supervisor, a short -> long -> short sequence (60 facts / 64-token continuation -> 900 facts / 192-token continuation -> short again) keeps new-session placement exactly 2/2/2 in all six waves. The fixed balanced-additive policy therefore remains the promoted policy and workload-regime adaptation is not triggered by current evidence.

## 0.1.30 retained benchmark generation

Strata 0.1.30 is the **retained full benchmark generation**. The measured implementation is `rhgo1749/Strata-Lanes@dcdd46ff37b1baf5172a96389fbdc0c7b51a7dbc`, based on upstream tag `Niko1221/Strata@30ec18ec7094550fcc594fd948220d511d80464e`. The unpromoted 0.1.29 campaign was superseded before its headline matrix was completed.

Upstream 0.1.30 contains the shared-arena primitive contributed through Strata PR #129. The lane runtime uses native `--shared-expert-arena`, forces conversation parking off until scheduler locality is modeled, preflights stale listeners, and exposes opt-in exact lane-admission telemetry. Gate 0 and the complete Gate 1 matrix passed on one generation; the 3/4/6/9 oversubscription extension and matched three-GPU layer-split A/B also completed. See `docs/strata-0.1.30-promotion-20261001.md`.

## Metric contract

### Common-wall aggregate TG

For concurrent fixed-length requests:

```text
aggregate TG = total concurrent completion tokens / one common client wall interval
```

This is a makespan-based metric and is therefore gated by the last request to finish. It is the primary scaling metric. **Do not substitute lane-sum engine TG for common-wall aggregate TG.**

Retained 0.1.30 controlled scaling, five completed repetitions per point:

```text
1 lane   70.804 ± 1.546 tok/s
2 lanes 132.760 ± 3.129 tok/s -> 1.875x / 93.8%
3 lanes 189.486 ± 3.205 tok/s -> 2.676x / 89.2%
```

The harness uses one fixed prompt, `temperature=0`, and seed `1234` for every scaling repetition. Because cache/speculative statistics still evolve across the warm sequence, those repetitions are **not strictly IID**. Mean/SD and the reported t-based intervals are descriptive summaries of that stateful sequence, not population-level IID inference.

### Queue wait, TTFT and end-to-end latency

For oversubscribed serving, timestamps have distinct meanings and must not be collapsed into one latency number:

- **queue wait**: request accepted by the public supervisor → request admitted to a lane;
- **service time**: lane admission → request completion;
- **end-to-end latency**: public request submission → request completion;
- **TTFT**: public request submission → first generated model token. SSE keep-alive comments during prompt reading are not first tokens;
- **common-wall aggregate throughput**: total completed output tokens divided by the common interval from synchronized submission to the last completion.

Exact queue wait uses the supervisor's `--bench-trace-jsonl` lease record: queue entry is taken after request parsing/classification, admission is the return from `LanePool.acquire()`, and release is after the proxied request completes. The client sends benchmark run/request/submit-rank headers, while response headers expose lane index, 0-based admission rank and queue wait as a cross-check. Client time-to-response-headers is **not** the source of truth because it also includes downstream/server work. Streaming-cancellation cleanup remains a separate failure-path measurement and must not be mixed into ordinary FIFO queue-wait percentiles.

For fixed three-lane overload runs, publish request-level rows for 3, 4, 6 and 9 simultaneous requests, then summarize end-to-end and queue-wait p50/p95 and p99 when the repetition count supports a meaningful p99. Lane utilization is each lane's admitted-busy time divided by the common wall interval. With equal fixed-length requests, fairness is reported both as FIFO overtaking (`admission_rank - submit_rank`) and Jain's index over per-request service throughput; these diagnose different failure modes.

### Lane-local TG

`tg_tok_s` in the systems CSV is an engine-reported lane-local decode rate. It is useful for isolation/interference analysis but is not directly additive under a fixed-length makespan metric.

For the retained RTX 5070 Ti x8 + RTX 5060 Ti x4 concurrent runs:

```text
5070 Ti solo lane-local TG        71.563 ± 1.760 tok/s
5070 Ti concurrent lane-local TG  71.163 ± 1.456 tok/s
5060 Ti concurrent lane-local TG  57.575 ± 1.527 tok/s
common-wall concurrent aggregate  113.898 ± 2.985 tok/s
```

The fast-lane mean difference is **-0.400 tok/s (-0.56%)**, smaller than the observed run-to-run dispersion in either condition. The conservative interpretation is **no material pacing of the fast lane within this measured pair and run set**; do not generalize a numerical bound to other GPU mixes or lane counts.

## Shared-arena memory accounting

The two-engine structural snapshot records:

```text
private PSS  98.924864 GiB
shared PSS   52.083863 GiB
PSS saved    46.841001 GiB / 47.35%
```

The shared arena is the same 49,116,200 KiB `rw-s` `/dev/shm` mapping in both engines, with `Shared_Dirty` rather than `Private_Dirty`, which is direct physical-sharing evidence.

## Heterogeneous and mixed-content reporting

The hetero protocol is interleaved (`ABBAABBAABBAABBA`) and uses the same fixed prompt/seed/temperature policy. Report both lane-local rates and common-wall aggregate throughput.

The mixed three-lane experiment rotates fiction/coding/reasoning across GPU0 x8 / GPU2 x8 / GPU1 x4. Nine common-wall runs average **184.669 ± 5.966 tok/s**. Across all rotations, fiction/coding/reasoning lane-local TG average **62.689 / 69.922 / 65.944 tok/s** respectively. Because workload assignments rotate, this support matrix does not isolate PCIe width.

## Matched independent-lane ↔ layer-split A/B

The retained 0.1.30 comparison is a **matched workload-region study**, not a single winner score. Both arms use Strata 0.1.30, IQ3_S, the same prompt bytes/hash, context, completion length, sampling/seed, warm/cold/reuse contract, driver/toolchain, and GPU tuning snapshot. Upstream conversation parking stays disabled in the primary comparison so it does not become an unmatched hidden state variable.

The retained A/B is now complete. One warm request measures **70.804 ± 1.546 tok/s** on one independent lane versus **102.976 ± 1.527 tok/s** on three-GPU layer split (+45.4%). Three simultaneous requests measure **189.486 ± 3.205 tok/s** common-wall on independent lanes versus **102.588 ± 1.629 tok/s** under the ordinary layer-split server's serial FIFO execution; independent lanes therefore provide 84.7% more aggregate throughput in that three-request region. Short-reasoning no-reuse PP/TTFT are 850.67 tok/s / 1.781 s for one independent lane and 807.11 tok/s / 1.867 s for layer split. Layer-split auto selected K=18,33 after per-stage PCIe probing.

The ordinary upstream one-engine server serializes generation through its FIFO lock rather than continuously batching requests inside one GPU. Therefore a one-GPU "continuous batching" baseline is not currently equivalent to a supported execution mode. A serial one-GPU queue may be reported as such, but it must not be labeled continuous batching.

## Workload sensitivity

Keep no-reuse PP/TTFT and warm steady-state decode as separate measurement classes. Cache-hit rate and speculative acceptance are observational correlates; do not infer causality without a controlled A/B. The retained 0.1.30 summary is in `workload-sensitivity-0.1.30-20261001.csv`.

## Statistical/data hygiene

- retain completed runs unless an external contamination/failure criterion is documented;
- failed/overlapped client runs are excluded from the retained raw directory; the four retained hetero ABBA chunks are complete JSONL files;
- report `n`, mean, SD, min/max, and metric definition;
- state when repetitions are stateful/non-IID;
- keep versioned measurement-contract differences explicit;
- snapshot GPU tuning state in future campaigns rather than reconstructing it later.

## Reproducibility metadata

Retained results should identify, where available: fork/upstream commit, binary hash, model/quant, GPU models and negotiated PCIe widths, CPU/RAM, driver/CUDA, lane context/KV, CPU partition, PCIe tuning, MTP/spec settings, sampling/seed, GPU tuning state, warm/cold/reuse state, prompt hash/tokens, output tokens, repetition count, common wall interval, and speculative acceptance when relevant.
