# Benchmark and reporting contract

This repository keeps benchmark classes separate so convenient numbers do not become misleading headline claims.

The **current promoted software baseline** is Strata **0.1.27** on fork commit `6cf101d5b98523cbaefc34a199faa5657c5c2719`, upstream `a79080535d1b2a71a3419a0d97d8e7dca194b0f1`.

Current paper-facing evidence:

- [`strata-0.1.27-promotion-20260930.csv`](strata-0.1.27-promotion-20260930.csv) — validation and provenance;
- [`systems-ablation-0.1.27-20260930.csv`](systems-ablation-0.1.27-20260930.csv) — scaling, physical-memory sharing, heterogeneous isolation, mixed three-lane serving;
- [`workload-sensitivity-0.1.27-20260930.csv`](workload-sensitivity-0.1.27-20260930.csv) — fiction/coding/reasoning/long-review repetitions.

Interpretation lives in [`../docs/systems-ablation-0.1.27-20260930.md`](../docs/systems-ablation-0.1.27-20260930.md) and [`../docs/workload-sensitivity-0.1.27-20260930.md`](../docs/workload-sensitivity-0.1.27-20260930.md).

Historical 0.1.22/0.1.24 files remain in place and must stay labeled historical.

## 1. Controlled multi-lane scaling

Purpose: measure request-level parallel scaling while keeping the workload fixed.

Hold constant:

- Strata fork commit;
- model / quant;
- prompt content/hash;
- output target;
- sampling;
- context and resident KV per lane;
- shared-arena mode;
- MTP/spec settings;
- warm/cold/reuse state.

Warm up first, then retain at least five repetitions. Do not discard legitimate slow runs.

The primary aggregate metric is:

```text
aggregate TG = total concurrent completion tokens / common wall interval
```

**Do not substitute lane-sum TG for common-wall aggregate TG.**

Current 0.1.27 IQ3_S reference:

```text
1 lane  71.45 ± 1.12 tok/s
2 lanes 137.57 ± 2.19 tok/s  -> 1.926x / 96.3% efficiency
3 lanes 191.75 ± 7.24 tok/s  -> 2.684x / 89.5% efficiency
```

## 2. Shared-arena physical-memory ablation

Purpose: prove physical host-memory sharing, not merely similar RSS.

Use an otherwise matched private-arena and shared-arena pair. After both engines are fully ready, record `/proc/<pid>/smaps_rollup` and the arena mapping itself.

Required fields include:

- RSS;
- PSS;
- `Private_Dirty`;
- `Shared_Dirty`;
- `Pss_Anon` / `Pss_Shmem` where available;
- mapping size/path/type;
- MemAvailable and swap.

Current 0.1.27 reference:

```text
private two-engine PSS  95.298 GiB
shared two-engine PSS   52.083 GiB
saved                   43.215 GiB / 45.35%
```

## 3. Heterogeneous isolation

Purpose: determine whether a slower independent lane measurably drags down a faster lane.

Use an interleaved protocol rather than running all solo trials before all concurrent trials. Report the fast-lane solo/concurrent mean and variance plus the slow-lane throughput.

Current 0.1.27 reference:

```text
5070 Ti x8 solo        73.01 ± 1.41 tok/s
5070 Ti x8 concurrent  72.36 ± 2.26 tok/s
5060 Ti x4 concurrent  59.14 ± 1.24 tok/s
```

The nominal 0.89% fast-lane difference is below normal run-to-run dispersion. Report this as **no measurable degradation within run-to-run variance**, not as a universal slowdown constant.

## 4. Workload sensitivity

Purpose: observe how PP, TG, expert locality, and speculative acceptance vary by request class.

Keep this separate from the fixed scaling benchmark.

Use fixed/reproducible prompts for:

- fiction/prose;
- coding;
- reasoning/technical analysis;
- long-context review.

Separate measurement classes:

- no-reuse PP/TTFT;
- warm steady-state decode;
- prompt reuse.

Never pool them into one distribution.

The current 0.1.27 workload CSV retains five repetitions per class/bucket/state. Workload-specific adaptive replacement is **not** established by this generation because measured adaptive swap publications were zero.

## 5. Real long-context concurrency

Purpose: capacity, client compatibility, and production realism.

Record per request:

- input tokens;
- output tokens;
- client/API latency;
- server-side PP when relevant;
- server-side TG when relevant;
- finish reason;
- lane survival;
- context-overflow / OOM / API errors.

A long-context admission run can be retained purely as capacity/stability evidence without promoting its throughput numbers.

## 6. Architecture challenger A/B

Request-per-lane and upstream layer-split answer different questions. When comparing them, hold constant where practical:

- commit;
- model / quant;
- max context;
- prompt/output target;
- warm/cold state;
- sampling;
- host/GPU tuning.

A single-request win is not sufficient to promote a challenger for this recipe's concurrent-agent workload. Promotion follows aggregate throughput, context, correctness, stability, and fallback behavior.

## 7. GPU tuning A/B

Power/frequency tuning must not be silently mixed into architecture or engine comparisons.

Hold constant:

- Strata commit;
- model / quant;
- lane contexts;
- resident KV;
- CPU partition;
- `pcie-frac`;
- MTP/spec settings;
- request set;
- warm/cold state;
- concurrency;
- sampling/output target.

Snapshot the actual clock/voltage/power-limit state before the benchmark. If that snapshot is missing, say so rather than reconstructing it from a separate reference profile.

## Metric naming

- **PP** = prompt processing throughput, tokens/s.
- **TG** = token generation/decode throughput, tokens/s.
- **aggregate TG** = overlapping multi-lane completion throughput derived from one common wall interval.
- **lane-sum TG** = sum of lane-local engine-reported TG; not automatically a wall aggregate.
- **capacity validation** = admission/stability evidence; not automatically a throughput benchmark.

`PP` does not mean pipeline parallelism here.

## Statistical hygiene

For primary claims retain and report at least:

- n;
- mean;
- median;
- standard deviation;
- min/max.

Use p95 or confidence intervals where useful and sample size permits. Keep outliers unless there is a concrete external contamination/failure reason. Record the exclusion reason for any removed run.

## Reproducibility metadata

Every promoted result should identify as much of the following as is available:

```text
fork commit / upstream engine version
binary hash
model / quant
GPU models and negotiated PCIe widths
CPU / RAM
driver / CUDA
lane contexts
resident KV
CPU partition
pcie-frac
adaptive-cache settings
MTP/spec settings
sampling
GPU tuning state
warm/cold/reuse state
prompt class/hash and token count
output tokens
repetition count
common wall interval when claiming aggregate throughput
speculative acceptance when relevant
```

The goal is not leaderboard precision. It is to make architecture, scheduler, engine-version, workload, and hardware-tuning changes comparable without mixing measurement generations.
