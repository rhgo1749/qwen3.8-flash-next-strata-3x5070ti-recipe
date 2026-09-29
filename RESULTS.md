# Results

This repository owns the reference-host measurements for the GPU-per-lane Strata recipe. The implementation fork intentionally keeps only generic runtime and roadmap contracts.

## Current promoted implementation

```text
repository       rhgo1749/Strata
promoted commit  3824f04003b79609a7cc6861ea5b4652a47d2ddb
0.1.24 merge     82a51614517392f2c5b83af7c39ffbb7abbc783e
upstream         3ce2523c2823687de5372be3af58534f56cbf286
engine           Strata 0.1.24
```

The 0.1.24 sync preserves the independent request-per-GPU lane architecture and shared host expert arena while absorbing upstream 0.1.23/0.1.24 serving and QSA long-prompt changes.

## Reference host

- CPU: AMD Ryzen 9 9950X3D, 16C/32T
- RAM: 128 GB DDR5
- GPU: 3 × RTX 5070 Ti 16 GB
- PCIe: Gen5 x8 / x4 / x8
- performance reference model: Qwen3.8-Flash-Next Strata IQ3_XXS
- current quality-oriented deployment: Qwen3.8-Flash-Next GSQ-RCO IQ3_S

## Reference three-lane policy

```text
lane contexts       262144 / 262144 / 262144
host-KV guard       786432 tokens
resident KV         32768 / 32768 / 32768
physical CPU cores  5 / 6 / 5
pcie-frac           0.55 / 0.25 / 0.55
```

IQ3_S uses a **46.84 GiB** shared expert arena and about **4524 slots / 8.63 GiB** of hot-expert VRAM per lane in the reference configuration.

## Strata 0.1.24 promotion matrix

The candidate passed 52 server/multi-GPU tests, the production CUDA build, both quantization matrices, and a concurrent ~140K-token no-reuse IQ3_S long-prompt validation.

### IQ3_XXS

| Mode | Decode / wall aggregate | 15K no-reuse PP |
| --- | ---: | ---: |
| 3 independent lanes | **218.4–233.7 tok/s**, mean **225.5** | **2453.5 / 2046.0 / 2450.8 tok/s** x8/x4/x8 |
| 3-GPU layer-split | **93.5–99.9 tok/s** single request | **1144.4 tok/s** |

### IQ3_S

| Mode | Decode / wall aggregate | 15K no-reuse PP |
| --- | ---: | ---: |
| 3 independent lanes | **176.8–199.4 tok/s**, mean **187.1** | **2381.8 / 1852.2 / 2371.8 tok/s** x8/x4/x8 |
| 3-GPU layer-split | **74.2–81.7 tok/s** single request | **938.0 tok/s** |

A fresh ~140K-token no-reuse request also completed concurrently on all three IQ3_S lanes without CUDA OOM or lane death.

For the target concurrent-agent workload, independent request lanes remain the promoted architecture. Layer-split remains the same-engine challenger for single-request-oriented workloads.

## Adaptive hot-expert replacement

Strata 0.1.24 defaults to adaptive replacement (`adapt_every=4`, `adapt_swaps=96`). A controlled IQ3_S single-lane A/B used the same configuration except the static control added `--adapt-swaps 0`.

| Mode | Retained 512-token mean TG | Expert-cache hit rate |
| --- | ---: | ---: |
| Adaptive | **69.43 tok/s** | **86.5–87%** |
| Static (`--adapt-swaps 0`) | **54.14 tok/s** | about **61%** |

Measured same-host improvement: **+28.3%**.

This is a workload-specific controlled result, not a universal speedup claim.

### Adaptive trace

`STRATA_ADAPT_TRACE` records the first miss timestamp internally, replacement selection, residency publication after async H2D completion, and the first later GPU-resident hit.

Retained trace counts:

```text
select               22,996
resident publication 22,900
first later GPU hit   6,937
```

| Interval | min | median | p95 | mean | max |
| --- | ---: | ---: | ---: | ---: | ---: |
| selected swap copy/event wall -> residency | 12.948 ms | **33.876 ms** | 49.751 ms | 33.044 ms | 83.533 ms |
| first miss -> residency | 20.205 ms | **10.716 s** | 26.602 s | 11.842 s | 29.920 s |
| residency -> first later GPU hit | **0.306 ms** | **154.249 ms** | 1.228 s | 325.423 ms | 6.742 s |
| first miss -> first later GPU hit | 57.284 ms | **3.430 s** | 18.126 s | 5.761 s | 28.650 s |

`first miss -> residency` includes adaptive-policy dwell time: the missing expert must accumulate enough decayed usage to justify replacing a current resident. It is **not raw PCIe latency**. The copy/event interval is likewise a runtime batch/event wall measurement, not the older standalone memcpy microbenchmark.

Full record: [`docs/strata-0.1.24-promotion-20260930.md`](docs/strata-0.1.24-promotion-20260930.md).  
Machine-readable summary: [`bench/adaptive-swap-20260930.csv`](bench/adaptive-swap-20260930.csv).

## Controlled systems ablations — retained architecture evidence

A separate 2026-09-29 benchmark set isolates scaling, RAM sharing, and heterogeneous-lane isolation.

### 1 -> 2 -> 3 GPU scaling

| Active lanes | Mean wall aggregate | Speedup | Parallel efficiency |
| ---: | ---: | ---: | ---: |
| 1 | **72.59 tok/s** | 1.000× | 100.0% |
| 2 | **137.01 tok/s** | **1.887×** | **94.4%** |
| 3 | **188.23 tok/s** | **2.593×** | **86.4%** |

### Shared arena RAM ablation

| Arena mode | Two-engine PSS |
| --- | ---: |
| Private arena per process | **95.33 GiB** |
| Shared arena | **52.03 GiB** |
| Reduction | **43.30 GiB / 45.4%** |

### Heterogeneous isolation

| Measurement | Mean TG |
| --- | ---: |
| RTX 5070 Ti x8 alone | **70.336 tok/s** |
| RTX 5070 Ti x8 while RTX 5060 Ti x4 is active | **70.321 tok/s** |
| Concurrent RTX 5060 Ti x4 lane | **57.246 tok/s** |

The measured RTX 5070 Ti decrease was **0.0215%**, far below ordinary run-to-run variance on this host. The slower card did not measurably become the faster card's token-step pace setter.

### Historical free-slot expert admission

The earlier standalone CUDA-runtime microbenchmark measured layer-weighted H2D means of:

- RTX 5070 Ti x8: **0.081 ms pinned / 0.117 ms ordinary host memory**;
- RTX 5060 Ti x4: **0.155 / 0.190 ms**.

These remain valid **free-slot transfer** measurements. The old conclusion that a full cache cannot evict is now historical: 0.1.24 adds adaptive victim replacement.

Full methodology: [`docs/systems-ablation-20260929.md`](docs/systems-ablation-20260929.md).  
Machine-readable observations: [`bench/systems-ablation-20260929.csv`](bench/systems-ablation-20260929.csv).

## Historical 0.1.22 promoted baseline

The prior promoted generation remains useful for version history:

- IQ3_XXS warm three-request wall aggregate: **226.5–227.9 tok/s**;
- IQ3_XXS 15,064-token no-reuse single-lane PP: **2492.2 tok/s**;
- IQ3_S warm aggregate: **183.9–209.7 tok/s**, mean **195.3 tok/s**;
- IQ3_S 15K no-reuse PP: **2325.6 / 1806.5 / 2293.0 tok/s**;
- IQ3_S 30K no-reuse PP: **2352.1 / 1812.9 / 2348.3 tok/s**;
- IQ3_XXS layer-split: **80.6 tok/s** short decode and **1142.3 tok/s** 15K PP.

Do not treat mismatched prompt generations as strict software-version A/Bs.

## Long-context validation

- 0.1.22: three concurrent real software-review prompts of **141,578 / 144,875 / 144,777 input tokens** all completed without context overflow, OOM, API failure, or lane death.
- 0.1.24: a fresh **~140K no-reuse request on all three IQ3_S lanes concurrently** completed without OOM or lane death.

These runs are capacity/stability/client-compatibility evidence, not throughput headlines.

## Promotion decision

**Accepted:** Strata 0.1.24 / promoted fork commit `3824f04` is the current engine baseline for this recipe and for the reference IQ3_S server.

The architecture decision remains:

- baseline: independent request/session lanes sharing one host expert arena;
- challenger: upstream layer-split in the same fork;
- production hot-expert policy: adaptive replacement enabled by default;
- promotion criterion: representative concurrent workload, required context capacity, correctness, stability and fallback behavior—not a single-request win alone.

## Reporting rule

For current 0.1.24 results:

- **225.5 tok/s mean** is the current IQ3_XXS clean-warm three-request wall aggregate, range 218.4–233.7;
- IQ3_XXS 15K PP is **2453.5 / 2046.0 / 2450.8 tok/s**;
- IQ3_XXS layer-split is **93.5–99.9 tok/s** decode and **1144.4 tok/s** PP;
- **187.1 tok/s mean** is the current IQ3_S clean-warm aggregate, range 176.8–199.4;
- IQ3_S 15K PP is **2381.8 / 1852.2 / 2371.8 tok/s**;
- IQ3_S layer-split is **74.2–81.7 tok/s** decode and **938.0 tok/s** PP;
- adaptive IQ3_S A/B is **69.43 vs 54.14 tok/s (+28.3%)**, with hit rate roughly **86.5–87% vs 61%**;
- systems-ablation values remain a separate controlled dataset and must not be substituted for the promoted clean-warm metrics;
- adaptive trace times must not be described as pure PCIe transfer latency.

## More detail

- [`docs/strata-0.1.24-promotion-20260930.md`](docs/strata-0.1.24-promotion-20260930.md) — current promotion and adaptive replacement
- [`bench/adaptive-swap-20260930.csv`](bench/adaptive-swap-20260930.csv) — adaptive trace summary
- [`docs/systems-ablation-20260929.md`](docs/systems-ablation-20260929.md) — scaling, RAM sharing, heterogeneous isolation, free-slot admission
- [`bench/systems-ablation-20260929.csv`](bench/systems-ablation-20260929.csv) — controlled systems observations
- [`docs/strata-0.1.22-promotion-20260929.md`](docs/strata-0.1.22-promotion-20260929.md) — historical 0.1.22 promotion
- [`docs/iq3-s-3lane-benchmark-20260929.md`](docs/iq3-s-3lane-benchmark-20260929.md) — historical IQ3_S 0.1.22 benchmark detail
- [`docs/reference-host-validation-20260929.md`](docs/reference-host-validation-20260929.md) — 262K ×3 validation
