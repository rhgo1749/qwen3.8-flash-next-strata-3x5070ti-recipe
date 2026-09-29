# Controlled systems ablations — 2026-09-29

This record isolates three architectural questions that are easy to blur together in ordinary serving benchmarks:

1. does request-per-GPU throughput scale from one to two to three lanes;
2. does the shared host expert arena materially reduce RAM versus independent private arenas;
3. does a slower heterogeneous GPU reduce the throughput of a faster lane running concurrently.

A fourth microbenchmark measures the H2D cost of admitting one expert into a still-free GPU cache slot. It is reported separately because current Strata does **not** evict experts from a full hot-expert cache.

## Software and host

```text
engine              Strata 0.1.22
fork commit         9dda206874387b20cac20837a1452f115a8f9f93
model               Qwen3.8-Flash-Next GSQ-RCO IQ3_S
CPU                 Ryzen 9 9950X3D, 16C/32T
RAM                 128 GB DDR5
5070 Ti topology    GPU0 x8 / GPU1 x4 / GPU2 x8
heterogeneous GPU   RTX 5060 Ti 16 GB, GPU3 x4
expert arena        50,294,988,800 bytes = 46.84 GiB
```

These experiments answer architecture questions. They do **not** replace the repository's promoted IQ3_S warm-throughput headline, which uses a different retained benchmark set.

Machine-readable retained observations are in [`../bench/systems-ablation-20260929.csv`](../bench/systems-ablation-20260929.csv).

## 1 → 2 → 3 GPU scaling

Steady-state decode used 512 completion tokens, five repetitions per point, one shared expert arena, 262,144 context per lane, and 32,768 resident KV per lane. Lane order was GPU0 x8, GPU2 x8, then GPU1 x4 so the two-GPU point used the two x8 cards.

| Active lanes | Mean wall aggregate | Median | Std. dev. | Speedup | Parallel efficiency |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | **72.59 tok/s** | 72.50 | 0.53 | 1.000× | 100.0% |
| 2 | **137.01 tok/s** | 136.85 | 2.01 | **1.887×** | **94.4%** |
| 3 | **188.23 tok/s** | 185.15 | 7.79 | **2.593×** | **86.4%** |

The three-GPU point includes the x4 middle card and shared host resources, so perfect 3.0× scaling is not expected. The useful result is that whole-request lanes retain most of the single-lane throughput while increasing wall-clock aggregate serving capacity.

## Shared arena RAM ablation

To isolate the arena itself without forcing a private two-lane run into an avoidable long-context memory failure, both arms used the same two lanes with 32,768 context and 8,192 resident KV. PSS was read from `/proc/<pid>/smaps_rollup` for the two native Strata engine processes after both lanes were ready.

| Arena mode | Two-engine PSS |
| --- | ---: |
| Private arena per process | **95.33 GiB** |
| Shared file-backed arena | **52.03 GiB** |
| Measured reduction | **43.30 GiB (45.4%)** |

The expert arena itself is 46.84 GiB. The PSS delta is smaller than one full arena because PSS also reflects paging, sharing, and unrelated process mappings. The private arm also consumed substantial swap while the shared arm did not need a duplicated expert arena.

This is direct evidence for the memory-sharing claim: independent engines do not need independent physical copies of the largest host allocation.

## Heterogeneous isolation: RTX 5070 Ti + RTX 5060 Ti

Two shared-arena lanes were run concurrently:

- fast lane: RTX 5070 Ti 16 GB, PCIe x8;
- slower lane: RTX 5060 Ti 16 GB, PCIe x4;
- 262,144 context each;
- 32,768 resident KV each;
- five 512-token repetitions after warmup.

The 5070 Ti was first measured alone, then measured again while the 5060 Ti served its own request concurrently.

| Measurement | Mean TG |
| --- | ---: |
| RTX 5070 Ti alone | **70.336 tok/s** |
| RTX 5070 Ti while RTX 5060 Ti is active | **70.321 tok/s** |
| RTX 5060 Ti concurrently | **57.246 tok/s** |

Fast-lane concurrent/solo ratio: **0.999785**. The observed 5070 Ti decrease was **0.0215%**, far below the run-to-run standard deviation (0.69 tok/s solo, 1.27 tok/s concurrent).

Within measurement noise, the slower 5060 Ti did not reduce the 5070 Ti lane's decode throughput. This is the intended failure/performance-isolation property of request-per-GPU lanes: a slower card makes **its own request** slower rather than becoming the token-step pace setter for every GPU.

This result should not be generalized into a claim that heterogeneous cards can never contend for CPU or PCIe resources. It demonstrates isolation on this measured host and topology under this workload.

## Expert-cache admission H2D microbenchmark

Current production uses `--expert-profile` with `--expert-cache auto`, so the GPU hot-expert cache is prefilled at startup. `ExpertCache` currently has no eviction policy. Once the cache is full, a non-resident expert falls through to the CPU expert path rather than replacing a resident GPU expert.

Therefore the following numbers measure **free-slot admission**, not a full-cache production miss penalty.

IQ3_S native expert blobs vary by layer from 1,510,400 to 2,662,400 bytes (1.440–2.539 MiB). One H2D copy per expert was measured over all seven actual blob sizes, 200 iterations per size after warmup.

| GPU / link | Host memory | Layer-weighted wall mean | Largest-blob p95 wall |
| --- | --- | ---: | ---: |
| RTX 5070 Ti x8 | pinned | **0.081 ms** | — |
| RTX 5070 Ti x8 | ordinary resident/pageable | **0.117 ms** | **0.140 ms** |
| RTX 5060 Ti x4 | pinned | **0.155 ms** | — |
| RTX 5060 Ti x4 | ordinary resident/pageable | **0.190 ms** | **0.244 ms** |

Pinned transfer bandwidth was about 26.2–26.5 GiB/s on the x8 5070 Ti and 13.25–13.35 GiB/s on the x4 5060 Ti.

The transfer itself is small enough that a future measured eviction/admission policy could plausibly be practical, but that is a future design question. These measurements do not imply that the current full-cache miss path performs a 0.1–0.2 ms replacement.

## What these results establish

Taken together, the controlled experiments support three separate properties of the current architecture on the reference host:

- **scalability:** 1 → 2 → 3 independent lanes increased aggregate decode from 72.59 to 188.23 tok/s;
- **memory sharing:** the shared arena reduced two-engine PSS by 43.30 GiB versus private arenas;
- **heterogeneous isolation:** a concurrent RTX 5060 Ti lane changed the RTX 5070 Ti mean from 70.336 to 70.321 tok/s, within noise.

They are deliberately kept separate from quantization-quality claims, long-prompt PP claims, and the promoted warm-throughput headline.