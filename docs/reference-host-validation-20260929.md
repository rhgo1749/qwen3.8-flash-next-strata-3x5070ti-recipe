# Reference-host validation — 2026-09-29

This document keeps host-specific **capacity, concurrency, and serving validation** out of the Strata implementation fork while preserving the reproducible evidence behind this recipe.

Performance numbers promoted by this repository live in [`undervolt-v2-20260929.md`](undervolt-v2-20260929.md), which is the canonical current tuning dataset. Earlier pre-second-undervolt throughput figures are intentionally not retained here.

No private repository names, local checkout paths, or session identifiers are included.

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

## Promoted three-lane runtime policy

```text
lane contexts       262144 / 262144 / 262144
host-KV guard       786432 tokens
resident KV         32768 / 32768 / 32768
physical CPU cores  5 / 6 / 5
pcie-frac           0.55 / 0.25 / 0.55
shared expert arena ~39.97 GiB
```

The host expert arena is physically shared through one Linux `MAP_SHARED` file-backed mapping. Each lane remains an independent Strata engine process with lane-local CUDA state, GPU hot-expert cache, resident KV, and session state.

The CPU and PCIe values above are host-specific tuning choices, not portable defaults. They are kept here as part of the reproducible configuration, while historical tuning-throughput tables are intentionally excluded from the promoted recipe.

## Full-window three-lane validation

Three independent real software-review prompts were launched through the normal OpenAI-compatible provider path within roughly two seconds of one another. The source repositories are intentionally unnamed; only workload sizes and runtime outcomes matter to this public record.

| Client | Input tokens | Output tokens | Finish | Completion marker observed |
| --- | ---: | ---: | --- | --- |
| A | 141,578 | 992 | `stop` | yes |
| B | 144,875 | 1,295 | `stop` | yes |
| C | 144,777 | 871 | `stop` | yes |

All three inputs exceeded the former 131,072-token per-lane limit. No API error, context-overflow error, CUDA OOM, or lane death occurred.

During the overlapping prefill interval all three GPU lanes were active concurrently. The acceptance criteria were:

- full-window admission on every lane;
- three concurrent generations;
- valid task-specific responses;
- completion-marker persistence;
- no context overflow;
- no CUDA OOM;
- no lane death.

This run is retained as **262K ×3 capacity and client-compatibility evidence**, not as the canonical throughput benchmark.

## Resident-KV boundary

A larger GPU-resident KV window was rejected because it displaced too much of the GPU hot-expert tier and degraded the measured serving behavior. The promoted reference configuration therefore keeps **32K resident KV on every lane** and leaves more VRAM for hot experts.

This document records the resulting configuration decision but intentionally omits the earlier throughput comparison. Current performance claims come only from the canonical tuning dataset.

## Agent / tool-call soak

The endpoint was also tested as an agent server rather than only as a text-generation endpoint. Coverage included:

- automatic and forced tool selection;
- named functions;
- streamed argument deltas;
- structured arguments;
- tool-result follow-up turns;
- malformed inputs/output markup;
- cancellation recovery;
- concurrent tool requests.

Recorded soak results:

```text
18/18 concurrent non-streaming tool calls
18/18 concurrent streaming tool calls
 9/9  concurrent tool_choice=none requests
```

All three lane processes remained alive at the end of the run.

## Interpretation

The validation supports the current recipe's coarse-grained design on this reference host:

- one independent Strata process per GPU;
- one shared host expert arena;
- lane-local hot cache and KV;
- disjoint CPU affinity;
- topology-aware tuning where measurements justify it;
- request-level routing rather than mandatory cross-GPU decode synchronization.

It does not claim that the same numeric tuning is optimal on another machine. The implementation fork intentionally keeps only the generic runtime contract; this repository owns the host-specific recipe and measurements.

For current performance measurements, use [`undervolt-v2-20260929.md`](undervolt-v2-20260929.md) and [`../RESULTS.md`](../RESULTS.md).
