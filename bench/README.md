# Benchmark and reporting contract

The **current promoted software baseline** is Strata **0.1.27** on fork commit `6cf101d5b98523cbaefc34a199faa5657c5c2719`, upstream `a79080535d1b2a71a3419a0d97d8e7dca194b0f1`.

Current paper-facing evidence:

- `strata-0.1.27-promotion-20260930.csv` — validation/provenance;
- `systems-ablation-0.1.27-20260930.csv` — scaling, RAM sharing, heterogeneous pair, mixed three-lane runs;
- `workload-sensitivity-0.1.27-20260930.csv` — workload repetitions.

Historical 0.1.22/0.1.24 files remain historical and must not be treated as matched software A/Bs unless their measurement contracts also match.

## Metric contract

### Common-wall aggregate TG

For concurrent fixed-length requests:

```text
aggregate TG = total concurrent completion tokens / one common client wall interval
```

This is a makespan-based metric and is therefore gated by the last request to finish. It is the primary scaling metric. **Do not substitute lane-sum engine TG for common-wall aggregate TG.**

Current controlled scaling, five completed repetitions per point:

```text
1 lane   71.45 ± 1.12 tok/s
2 lanes 137.57 ± 2.19 tok/s  -> 1.926x / 96.3%
3 lanes 191.75 ± 7.24 tok/s  -> 2.684x / 89.5%
```

The harness uses one fixed prompt, `temperature=0`, and seed `1234` for every scaling repetition. Because cache/speculative statistics still evolve across the warm sequence, those repetitions are **not strictly IID**. Mean/SD and the reported t-based intervals are descriptive summaries of that stateful sequence, not population-level IID inference.

### Lane-local TG

`tg_tok_s` in the systems CSV is an engine-reported lane-local decode rate. It is useful for isolation/interference analysis but is not directly additive under a fixed-length makespan metric.

For the retained RTX 5070 Ti x8 + RTX 5060 Ti x4 concurrent runs:

```text
5070 Ti solo lane-local TG        73.01 ± 1.41 tok/s
5070 Ti concurrent lane-local TG  72.36 ± 2.26 tok/s
5060 Ti concurrent lane-local TG  59.14 ± 1.24 tok/s
common-wall concurrent aggregate  116.96 ± 2.42 tok/s
```

The unadjusted fast-lane difference is -0.65 tok/s (-0.9%) and is inconclusive by Welch analysis. Per-run TG is strongly associated with speculative acceptance; an exploratory OLS/ANCOVA sensitivity model (`TG ~ concurrent + spec_acceptance`) estimates a concurrent coefficient of about **-1.00 tok/s (-1.4%)**, 95% CI **[-1.71, -0.30]**, `p=0.009`. Because speculative acceptance is observed during execution and may itself respond to concurrency, this adjusted coefficient is **not a causal effect estimate**. Paper-safe interpretation: this one measured pair shows a small shared-resource cost rather than zero interference; do not generalize a numerical bound to other GPU mixes or lane counts.

## Shared-arena memory accounting

The two-engine structural snapshot records:

```text
private PSS  95.298 GiB
shared PSS   52.083 GiB
PSS saved    43.215 GiB / 45.35%
```

The shared arena is the same 49,116,200 KiB `rw-s` `/dev/shm` mapping in both engines, with `Shared_Dirty` rather than `Private_Dirty`, which is direct physical-sharing evidence.

### Important: `swap_gib` is host-global

The `swap_gib` column in `systems-ablation-0.1.27-20260930.csv` is **not per-process or per-engine swap**. It was derived from host-wide `/proc/meminfo` as:

```text
(SwapTotal - SwapFree) / GiB
```

The retained private/shared snapshots report 9.443 GiB and 5.704 GiB of host-global used swap respectively. Adding these host-global counters to process PSS happens to yield a difference close to the 46.84-GiB arena size, but that near-match must not be causally attributed to the arena because the swap counter covers the whole host.

## Heterogeneous and mixed-content reporting

The hetero protocol is interleaved (`ABBAABBAABBAABBA`) and uses the same fixed prompt/seed/temperature policy. Report both lane-local rates and common-wall aggregate throughput.

The mixed three-lane experiment rotates fiction/coding/reasoning across GPU0 x8 / GPU2 x8 / GPU1 x4. Nine common-wall runs average **187.15 ± 5.63 tok/s**. Averaged lane-local TG is approximately 66.27 / 67.03 / 66.99 tok/s for x8/x8/x4 respectively; this matrix does not isolate PCIe width. Historical 0.1.22 IQ3_S 15K no-reuse PP did show the x4 lane about 21.8% below the x8-lane mean, but that earlier software generation is qualitative context only.

## Workload sensitivity

Keep no-reuse PP/TTFT and warm steady-state decode as separate measurement classes. Cache-hit rate and speculative acceptance are observational correlates; do not infer causality without a controlled A/B. The retained 0.1.27 workload windows publish zero adaptive expert swaps, so they do not establish workload-specific adaptive-replacement benefit.

## Statistical/data hygiene

- retain completed runs unless an external contamination/failure criterion is documented;
- the hetero raw JSONL contains one malformed trailing fragment after the valid completed records; it is not a completed observation;
- report `n`, mean, SD, min/max, and metric definition;
- state when repetitions are stateful/non-IID;
- keep historical measurement-contract differences explicit;
- snapshot GPU tuning state in future campaigns rather than reconstructing it later.

## Reproducibility metadata

Promoted results should identify, where available: fork/upstream commit, binary hash, model/quant, GPU models and negotiated PCIe widths, CPU/RAM, driver/CUDA, lane context/KV, CPU partition, PCIe tuning, MTP/spec settings, sampling/seed, GPU tuning state, warm/cold/reuse state, prompt hash/tokens, output tokens, repetition count, common wall interval, and speculative acceptance when relevant.
