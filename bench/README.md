# Benchmark and reporting contract

This repository keeps several benchmark classes separate so convenient numbers do not become misleading headline claims.

## 1. Real long-context concurrency

Purpose: production realism.

Use multiple independent client sessions with representative repository/code/document context and start them close together.

Record per request:

- input tokens;
- output tokens;
- client/API latency;
- server-side prompt-processing time;
- server-side decode throughput;
- finish reason;
- lane survival;
- context-overflow / OOM / API errors.

Only sum per-lane PP or TG when the relevant intervals actually overlap.

## 2. Short warm multi-lane decode

Purpose: stable same-host A/B comparison.

Use a fixed short prompt set, warm the expert/cache state, then send one request to each private lane endpoint concurrently.

Use environment-specific endpoints rather than copying ports from another host:

```text
lane 0 -> <lane-0-endpoint>
lane 1 -> <lane-1-endpoint>
lane N -> <lane-N-endpoint>
```

For low-variance throughput probes, keep sampling and output length fixed, for example:

```text
temperature = 0
max_tokens  = 256
```

Read TG from each Strata engine summary and record speculative acceptance (`drafts accepted A of B`). Report both wall-derived aggregate throughput and lane-sum only when each is actually valid.

Reference pre-second-undervolt baseline:

```text
~74–76 tok/s per lane
216.1 tok/s warm wall aggregate
221.1 tok/s best observed warm round
```

Reference second-undervolt lane-local round:

```text
78.8 / 78.4 / 80.1 tok/s
lane-sum = 237.3 tok/s
acceptance = 126/166, 129/157, 141/177
```

The 237.3 value is a lane-sum, not a clean wall aggregate.

## 3. Cold long-context admission

Purpose: memory/context/prefill validation.

Use prompts large enough to stress configured host-KV capacity and avoid prefix reuse.

Record:

- exact prompt tokens;
- cold/reused status;
- prompt-processing throughput;
- following decode throughput;
- peak VRAM;
- host available RAM;
- lane survival.

Reference older 512K-total validation:

```text
246,788 + 128,388 + 128,388 = 503,564 prompt tokens
PP: 1,499 / 1,542 / 1,724 tok/s
TG: 60.1 / 66.1 / 73.3 tok/s
```

Independent no-reuse PP spot checks must not be summed unless their prefill intervals actually overlap.

## 4. GPU undervolt A/B

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

1. pause or disable **your own workload dispatcher**;
2. wait for already in-flight client/tool loops to drain;
3. verify the serving layer reports zero active requests, if it exposes such a status;
4. verify the target GPUs are idle;
5. start the benchmark.

Do not copy a host-specific control command or localhost port from another deployment. The benchmark contract is about state, not one operator's process manager.

Useful GPU telemetry:

```bash
nvidia-smi \
  --query-gpu=index,power.draw,power.limit,clocks.current.graphics,clocks.current.memory,temperature.gpu,utilization.gpu \
  --format=csv
```

Sample telemetry over the same interval for power comparisons; do not compare an instantaneous reading to an interval average.

## Metric naming

- **PP** = prompt processing throughput, tokens/s.
- **TG** = token generation/decode throughput, tokens/s.
- **C1/C2/C3** = one/two/three concurrent requests when used.
- **aggregate TG** = overlapping multi-lane decode throughput; state whether wall-derived or lane-sum.
- **lane-sum TG** = sum of lane-local engine-reported TG; not automatically a clean wall aggregate.

`PP` does not mean pipeline parallelism here.

## Reproducibility metadata

Every promoted result should include at least:

```text
repo commit
model / quant
GPU count and link widths
CPU / RAM
lane contexts
resident KV
CPU partition
pcie-frac
MTP/spec settings
GPU tuning state
warm/cold state
prompt tokens
output tokens
concurrency
speculative acceptance
```

The goal is not leaderboard precision. It is to make architecture, scheduler and hardware-tuning changes comparable on the same host.