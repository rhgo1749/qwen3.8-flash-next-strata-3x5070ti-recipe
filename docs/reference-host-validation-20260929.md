# Reference-host validation — 2026-09-29

This document keeps host-specific measurements out of the Strata implementation fork while preserving the reproducible evidence behind this recipe.

No private repository names, local checkout paths, or session identifiers are included here.

## Reference host

- CPU: AMD Ryzen 9 9950X3D, 16C/32T
- RAM: 128 GB DDR5, 4 × 32 GB, DDR5-5800 CL40
- Fabric / SoC: FCLK 2000 MHz, VSOC ~1.05 V
- GPU: 3 × RTX 5070 Ti 16 GB
- NVIDIA enumeration during validation: GPU0 x8, GPU1 x4, GPU2 x8
- PCIe generation: Gen5
- no NVLink
- NVIDIA driver: 615.71.09
- model: Qwen3.8-Flash-Next, Strata IQ3_XXS
- sanitized implementation pin: [`rhgo1749/Strata@844d6206`](https://github.com/rhgo1749/Strata/commit/844d62064b4327f80eae0f2980ccbd83b04fbe9a)

## Promoted three-lane policy

```text
lane contexts       262144 / 262144 / 262144
host-KV guard       786432 tokens
resident KV         32768 / 32768 / 32768
physical CPU cores  5 / 6 / 5
pcie-frac           0.55 / 0.25 / 0.55
shared expert arena ~39.97 GiB
```

The host expert arena is physically shared through one Linux `MAP_SHARED` file-backed mapping. Each lane remains an independent Strata engine process with lane-local CUDA state, GPU hot-expert cache, resident KV, and session state.

## CPU affinity and PCIe tuning progression

Running several Strata processes with overlapping process affinity first caused the lanes to pin expert workers onto the same physical cores. Fixing that collision produced the largest early gain before further topology tuning.

Representative 256-token warm measurements:

| CPU cores | per-lane `pcie-frac` | warm aggregate |
| --- | --- | ---: |
| overlap-prone baseline | default | ~50 tok/s |
| disjoint automatic partition | default | ~136–138 tok/s |
| 5/6/5 | 0.55 / 0.55 / 0.55 | 174.5 tok/s |
| 5/6/5 | 0.55 / 0.35 / 0.55 | 202.9 tok/s |
| **5/6/5** | **0.55 / 0.25 / 0.55** | **216.1 tok/s** |
| 5/6/5 | 0.55 / 0.15 / 0.55 | 213.1 tok/s |
| 5/6/5 | 0.65 / 0.25 / 0.65 | 206.9 tok/s |
| 5/7/4 | 0.55 / 0.25 / 0.55 | 215.1 tok/s |

The best individual warm round reached 221.1 tok/s wall aggregate, with all three lanes around 74–76 tok/s. These are host-specific measurements, not portable performance promises.

## Long-context three-lane validation

Three independent real software-review prompts were launched through the normal OpenAI-compatible provider path within roughly two seconds of one another. The source repositories are intentionally unnamed here; only the workload sizes and runtime outcomes matter to this public recipe.

| Client | Input tokens | Output tokens | API latency | Finish | Completion marker observed |
| --- | ---: | ---: | ---: | --- | --- |
| A | 141,578 | 992 | 298.7 s | `stop` | yes |
| B | 144,875 | 1,295 | 229.3 s | `stop` | yes |
| C | 144,777 | 871 | 211.4 s | `stop` | yes |

All three inputs exceeded the former 131,072-token per-lane limit. No API error, context-overflow error, CUDA OOM, or lane death occurred.

During the overlapping prefill interval all three GPU lanes were active concurrently. The acceptance criteria were full-window admission, concurrent execution, valid task-specific responses, completion-marker persistence, and runtime stability.

The latency figures above should not be used as a raw throughput comparison because a small amount of prior work was still draining near the beginning of the controlled run.

## Prompt-processing and decode observations

Server progress timing during the long-context run showed approximately:

| Metric | Observation |
| --- | ---: |
| PP / lane | ~1.5–1.6k tok/s |
| PP aggregate | ~4.5–4.8k tok/s |
| TG / lane | ~54–64 tok/s |
| TG aggregate | ~175–190 tok/s |

One concrete lane observation was 144,875 prompt tokens over roughly 93 seconds of prefill, or about 1,558 prompt-processing tok/s.

These are approximate progress-log measurements rather than a synthetic microbenchmark.

## Earlier 512K total-capacity cold validation

Before promoting the full window on every lane, the earlier static layout was validated with 503,564 prompt tokens across three simultaneous requests:

```text
246,788 + 128,388 + 128,388 = 503,564
```

No prompt tokens were reused. Approximate prefill rates were 1,499 / 1,542 / 1,724 tok/s, followed by decode rates of 60.1 / 66.1 / 73.3 tok/s.

## Resident-KV boundary

Increasing one lane's GPU-resident KV from 32K to 64K was rejected in testing:

- hot-expert cache shrank to about 8.64 GiB;
- measured expert-cache hit rate fell to 54.2%;
- cold long-context decode dropped from 60.1 tok/s to 45.0 tok/s.

The promoted reference host therefore keeps 32K resident KV on every lane and leaves more VRAM for the hot-expert tier.

## Agent / tool-call soak

The endpoint was also tested as an agent server rather than only as a text-generation benchmark. Coverage included automatic and forced tool selection, named functions, streamed argument deltas, structured arguments, tool-result follow-up turns, malformed inputs, cancellation recovery, and concurrent tool requests.

Recorded soak results:

```text
18/18 concurrent non-streaming tool calls
18/18 concurrent streaming tool calls
 9/9  concurrent tool_choice=none requests
```

All three lane processes remained alive at the end of the run.

## Interpretation

The evidence supports the current recipe's coarse-grained design on this reference host:

- one independent Strata process per GPU;
- one shared host expert arena;
- lane-local hot cache and KV;
- disjoint CPU affinity;
- topology-aware tuning where measurements justify it;
- request-level routing rather than mandatory cross-GPU decode synchronization.

This does not claim that the same numeric tuning is optimal on another machine. The implementation fork intentionally keeps only the generic runtime contract; this repository owns the host-specific recipe and measurements.
