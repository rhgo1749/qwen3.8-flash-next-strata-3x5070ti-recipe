# Strata 0.1.22 promotion — 2026-09-29

This record promotes the reference GPU-per-lane recipe from the Strata 0.1.21 integration baseline to the upstream-synced **Strata 0.1.22** fork state and records the current 0.1.22 validation for both IQ3_XXS and the deployed IQ3_S profile.

## Decision

**Accepted.** The current promoted recipe implementation is:

```text
repository  rhgo1749/Strata
commit      9dda206874387b20cac20837a1452f115a8f9f93
engine      0.1.22
architecture independent request-per-GPU lanes + one shared host expert arena
```

The architecture decision did not change. Upstream layer-split remains available in the same fork as a challenger path, while request-per-lane serving remains the production baseline for the target concurrent-agent workload.

IQ3_XXS remains the performance-oriented comparison profile. The current reference-host deployment uses IQ3_S as the quality-oriented model.

## Reference host and unchanged recipe contract

```text
CPU                 Ryzen 9 9950X3D, 16C/32T
RAM                 128 GB DDR5
GPUs                RTX 5070 Ti 16 GB ×3
PCIe                Gen5 x8 / x4 / x8
lane contexts        262144 / 262144 / 262144
host-KV guard        786432 tokens
resident KV          32768 / 32768 / 32768
physical CPU cores   5 / 6 / 5
pcie-frac            0.55 / 0.25 / 0.55
```

The existing multi-lane recipe/CLI remained compatible. No new migration flag was required.

## Validation gates

The 0.1.22 candidate passed:

- server / multi-GPU / detokenizer tests: **41 passed, 3 skipped**;
- CUDA build: **121 / 121 build steps completed**;
- IQ3_XXS three-lane startup at **262K ×3**;
- unchanged IQ3_XXS shared-arena and lane cache sizing;
- IQ3_XXS repeated warm three-request wall-clock throughput;
- IQ3_XXS 15K no-reuse prompt-processing spot check;
- upstream 3-GPU layer-split startup at 262K;
- layer-split short decode and 15K prompt-processing smoke;
- IQ3_S production startup at **262K ×3**;
- IQ3_S repeated warm three-request wall aggregate;
- IQ3_S concurrent 15K no-reuse PP on all three lanes;
- IQ3_S concurrent 30K no-reuse PP on all three lanes;
- live public `8087` completion smoke on the 0.1.22 IQ3_S production binary.

## IQ3_XXS promoted measurements

### Request-per-lane baseline (A)

Three identical concurrent short requests were warmed first so every lane could reuse the same short prefix. The two retained warm rounds were:

| Warm round | Completion tokens | Wall time | Wall aggregate |
| --- | ---: | ---: | ---: |
| 1 | 384 | 1.685 s | **227.9 tok/s** |
| 2 | 384 | 1.695 s | **226.5 tok/s** |

Current clean warm wall aggregate: **226.5–227.9 tok/s** (midpoint about **227.2 tok/s**).

A no-reuse **15,064-token** prompt on one 262K lane processed in **6,044 ms = 2,492.2 tok/s**, followed by 16 generated tokens at 67.6 tok/s.

### Upstream layer-split challenger (B)

The same fork binary also started the upstream 3-GPU layer-split path at 262K successfully.

- short single-request decode: **80.6 tok/s**;
- 15,064-token no-reuse prompt processing: **1,142.3 tok/s**;
- following 16-token decode: **82.3 tok/s**.

For the retained 15K prompt-processing probe, request-per-lane A was about **2.18×** the B prompt-processing rate. B still showed the expected single-request decode advantage.

## IQ3_S current 0.1.22 validation

### Runtime sizing

The deployed IQ3_S profile uses:

```text
shared expert arena  46.84 GiB
hot-expert cache     4524 slots / 8.63 GiB per lane
fully-loaded free VRAM ~225 MiB per lane
```

This differs slightly from the older IQ3_S benchmark generation, which reported 4548 slots / 8.67 GiB.

### Warm three-request wall aggregate

Two independent backend sessions each used one cold short round followed by retained warm rounds. The four retained warm wall aggregates were:

```text
183.9 / 190.8 / 196.8 / 209.7 tok/s
```

Current reproducible range: **183.9–209.7 tok/s**.  
Four-round mean: **195.3 tok/s**.

This is now the preferred IQ3_S concurrent-serving headline metric. The older **183.4 tok/s** value was an engine-reported lane-sum, not a wall aggregate.

### Concurrent 15K no-reuse PP

Each lane received **15,048 prompt tokens** with **0 reused**:

| Lane | Read time | PP | Following TG |
| --- | ---: | ---: | ---: |
| GPU0 / x8 | 6,471 ms | **2,325.6 tok/s** | 42.9 tok/s |
| GPU1 / x4 | 8,330 ms | **1,806.5 tok/s** | 48.8 tok/s |
| GPU2 / x8 | 6,563 ms | **2,293.0 tok/s** | 45.5 tok/s |

The x8 mean was **2,309.3 tok/s**. The x4 middle lane was about **21.8% slower**.

### Concurrent 30K no-reuse PP

Each lane received **30,024 prompt tokens** with **0 reused**:

| Lane | Read time | PP | Following TG |
| --- | ---: | ---: | ---: |
| GPU0 / x8 | 12,765 ms | **2,352.1 tok/s** | 44.5 tok/s |
| GPU1 / x4 | 16,561 ms | **1,812.9 tok/s** | 50.0 tok/s |
| GPU2 / x8 | 12,785 ms | **2,348.3 tok/s** | 46.2 tok/s |

Mean across all three lanes: **2,171.1 tok/s/lane**.  
Mean of the two x8 lanes: **2,350.2 tok/s**.  
The x4 middle lane was about **22.9% slower** than the x8 mean.

No retained IQ3_S long-prompt request reported prompt reuse, CUDA OOM, API failure, or lane death.

## IQ3_S historical comparison

The older IQ3_S benchmark generation measured ~30K no-reuse PP of:

```text
1553.7 / 1323.9 / 1545.1 tok/s
```

The current 0.1.22 rates are higher by approximately:

- GPU0: **+51.4%**;
- GPU1: **+36.9%**;
- GPU2: **+52.0%**;
- three-lane mean: **+47.3%**.

This is an **indicative software-generation comparison**, not a strict same-prompt A/B. The prompt lengths were nearly identical (~30K) but prompt content and runtime generation differed.

## IQ3_XXS 0.1.21 historical comparison

The immediately preceding 0.1.21 integration validation recorded:

- A warm three-request wall aggregate: **198.2 tok/s**;
- A ~15K prompt-processing spot check: **1,609.9 tok/s**.

Against those specific promotion runs, 0.1.22 IQ3_XXS measured approximately:

- **+14.6%** warm wall aggregate;
- **+54.8%** on the retained ~15K prompt-processing spot check.

These deltas are software-version promotion comparisons on the same reference architecture, not universal model-level speedup claims.

## Measurement-hygiene note

One intermediate IQ3_S rerun was discarded when the public idle proxy parked the backend between direct private-lane benchmark requests. Private-lane traffic does not reset that public idle timer. The backend was woken through the public endpoint, and the retained 15K, 30K, and warm-repeat runs then completed inside one active backend interval.

This did not affect the promoted results, but it is an operational caveat for future private-lane benchmark automation.

## Architecture promotion outcome

The request-per-lane design remains promoted because the target workload is concurrent independent agent requests. The layer-split challenger remains available for workloads where single-request decode latency is more important.

A challenger should replace the baseline only after it wins the roadmap gates on representative concurrent serving, required context capacity, correctness, stability, and fallback behavior—not from a single-request result alone.

The current model deployment decision and the architecture decision are intentionally separate: IQ3_S can be the quality-oriented deployed model while IQ3_XXS remains the performance reference and independent request lanes remain the multi-GPU architecture baseline.
