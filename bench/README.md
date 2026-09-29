# Benchmark and reporting contract

This repository keeps benchmark classes separate so convenient numbers do not become misleading headline claims.

The **current promoted software baseline** is Strata **0.1.22** on fork commit `9dda206`. The current reference-host GPU tuning remains the 2300 MHz / 875 mV state documented in [`docs/undervolt-v2-20260929.md`](../docs/undervolt-v2-20260929.md).

Current promotion details: [`docs/strata-0.1.22-promotion-20260929.md`](../docs/strata-0.1.22-promotion-20260929.md).

## 1. Real long-context concurrency

Purpose: capacity, client compatibility, and production realism.

Use multiple independent client sessions with representative repository/code/document context and start them close together.

Record per request:

- input tokens;
- output tokens;
- client/API latency;
- server-side prompt-processing time when the run is intended as a throughput measurement;
- server-side decode throughput when the run is intended as a throughput measurement;
- finish reason;
- lane survival;
- context-overflow / OOM / API errors.

Only sum per-lane PP or TG when the relevant intervals actually overlap. A long-context admission run can be retained purely as a capacity/stability result without promoting its throughput numbers.

## 2. Short warm multi-lane decode

Purpose: stable same-host throughput comparison.

Use a fixed short prompt, warm the expert/cache/prefix state on every lane, then send one request to each lane concurrently.

The preferred aggregate metric is:

```text
aggregate TG = total completion tokens / common wall interval
```

Current promoted 0.1.22 reference-host rounds:

```text
384 completion tokens / 1.685 s = 227.9 tok/s
384 completion tokens / 1.695 s = 226.5 tok/s
```

So the current clean warm headline result is **226.5–227.9 tok/s wall aggregate**.

Per-lane engine-reported TG remains useful diagnostic evidence, but a lane-sum is not automatically a wall aggregate.

Historical second-undervolt lane-local round:

```text
78.8 / 78.4 / 80.1 tok/s
lane-sum = 237.3 tok/s
```

The **237.3 tok/s value remains valid historical lane-sum evidence, not a clean wall aggregate**.

## 3. Cold / no-reuse prompt processing

Purpose: memory/context/prefill validation and prompt-processing sanity checks.

Record:

- exact prompt tokens;
- prompt content/class when practical;
- cold/reused status;
- prompt-processing throughput;
- following decode throughput;
- peak VRAM;
- host available RAM;
- lane survival;
- Strata commit/version.

Current 0.1.22 promotion spot check:

```text
15,064 tokens, no reuse -> 2,492.2 tok/s
```

This is a same-host software-promotion spot check, **not a universal long-prompt PP claim**.

Historical longer-prompt independent observations:

```text
GPU0: 45,519 tokens -> 1,529.7 tok/s
GPU1: 45,812 tokens -> 1,421.6 tok/s
GPU2: 64,972 tokens -> 1,536.9 tok/s
mean: ~1,496 tok/s/lane
```

Do not directly compute a software speedup between mismatched prompt lengths/classes. Use same-shape promotion runs when claiming version deltas.

## 4. Architecture A/B

Purpose: compare request-per-lane serving against more coupled multi-GPU challengers.

Hold constant where possible:

- Strata fork commit;
- model / quant;
- max context;
- prompt and output target;
- warm/cold state;
- sampling;
- host/GPU tuning.

Current 0.1.22 same-fork challenger smoke:

```text
A: request-per-lane 15,064-token no-reuse PP = 2,492.2 tok/s
B: 3-GPU layer-split 15,064-token no-reuse PP = 1,142.3 tok/s
A/B PP ratio ~= 2.18x

B short single-request decode = 80.6 tok/s
```

A single-request win is not sufficient to promote a challenger for this recipe's concurrent-agent workload. Promotion follows the implementation roadmap's aggregate throughput, context, correctness, stability and fallback gates.

## 5. GPU tuning A/B

Purpose: isolate power/frequency tuning from software architecture.

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

Before starting:

1. pause or disable your own workload dispatcher;
2. wait for in-flight client/tool loops to drain;
3. verify zero active requests where exposed;
4. verify target GPUs are idle;
5. start the benchmark.

## Metric naming

- **PP** = prompt processing throughput, tokens/s.
- **TG** = token generation/decode throughput, tokens/s.
- **aggregate TG** = overlapping multi-lane completion throughput derived from one common wall interval.
- **lane-sum TG** = sum of lane-local engine-reported TG; not automatically a wall aggregate.
- **capacity validation** = admission/stability evidence; not automatically a throughput benchmark.

`PP` does not mean pipeline parallelism here.

## Reproducibility metadata

Every promoted result should include at least:

```text
repo commit / engine version
model / quant
GPU count and link widths
CPU / RAM
lane contexts
resident KV
CPU partition
pcie-frac
MTP/spec settings
GPU tuning state
warm/cold/reuse state
prompt tokens and prompt class
output tokens
concurrency
wall interval when claiming aggregate throughput
speculative acceptance when relevant
```

The goal is not leaderboard precision. It is to make architecture, scheduler, engine-version and hardware-tuning changes comparable without mixing measurement generations.
