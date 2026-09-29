# Results

This repository owns the reference-host measurements for the GPU-per-lane Strata recipe. The implementation fork intentionally keeps only generic runtime and roadmap contracts.

## Current promoted implementation

```text
repository  rhgo1749/Strata
commit      9dda206874387b20cac20837a1452f115a8f9f93
engine      Strata 0.1.22
```

The 0.1.22 sync preserved the independent request-per-GPU lane architecture and the existing recipe command surface while inheriting upstream prompt-path optimizations.

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

IQ3_XXS uses an approximately **39.97 GiB** shared expert arena; IQ3_S uses **46.84 GiB**.

## Current promoted IQ3_XXS performance — Strata 0.1.22

### Clean warm three-request wall aggregate

Three identical concurrent short requests were warmed so each lane could reuse the same short prefix. The retained warm rounds were:

| Warm round | Completion tokens | Wall time | Aggregate TG |
| --- | ---: | ---: | ---: |
| 1 | 384 | 1.685 s | **227.9 tok/s** |
| 2 | 384 | 1.695 s | **226.5 tok/s** |

**Current promoted IQ3_XXS concurrent-serving result: 226.5–227.9 tok/s wall aggregate** (midpoint about 227.2 tok/s).

This is the preferred IQ3_XXS headline multi-lane throughput metric because it comes from a common wall interval. Per-lane engine-reported TG should not be substituted for the wall aggregate.

### 15K no-reuse prompt-processing spot check

One 262K lane processed a **15,064-token** no-reuse prompt in **6,044 ms**, or **2,492.2 tok/s**, followed by 16 generated tokens at 67.6 tok/s.

This is a promoted 0.1.22 software-version spot check on the reference host. It is not a universal long-prompt PP claim: prompt length/content matters, and older PP datasets are different benchmark generations.

## Upstream layer-split challenger on the same 0.1.22 fork

The same `9dda206` fork binary also preserved upstream 3-GPU layer-split at 262K.

| Measurement | Layer-split result |
| --- | ---: |
| Short single-request decode | **80.6 tok/s** |
| 15,064-token no-reuse PP | **1,142.3 tok/s** |
| Following 16-token decode | **82.3 tok/s** |

For the retained 15K prompt-processing probe, request-per-lane A measured about **2.18×** the layer-split B rate (2,492.2 / 1,142.3). Layer-split still showed the expected single-request decode advantage.

For this recipe's target concurrent-agent workload, independent lanes remain the architecture baseline; layer-split remains a useful challenger for single-request-oriented workloads.

## 0.1.21 historical IQ3_XXS promotion baseline

The immediately preceding 0.1.21 integration validation measured:

- warm three-request wall aggregate: **198.2 tok/s**;
- ~15K prompt-processing spot check: **1,609.9 tok/s**.

Against those specific same-host promotion runs, 0.1.22 measured about:

- **+14.6%** warm wall aggregate (227.2 vs 198.2 tok/s);
- **+54.8%** on the retained ~15K prompt-processing spot check (2,492.2 vs 1,609.9 tok/s).

These percentages describe this promotion comparison only; they are not universal speedup claims for every prompt or workload.

## Historical second-undervolt IQ3_XXS lane-local observation

The older second-undervolt fixed short lane-local probes recorded:

| Lane | Prompt reuse | TG | MTP/spec accepted |
| --- | --- | ---: | ---: |
| GPU0 | 72 reused + 5 read | **78.8 tok/s** | 126 / 166 (**75.9%**) |
| GPU1 | 69 reused + 5 read | **78.4 tok/s** | 129 / 157 (**82.2%**) |
| GPU2 | 73 reused + 5 read | **80.1 tok/s** | 141 / 177 (**79.7%**) |

Lane-sum:

```text
78.8 + 78.4 + 80.1 = 237.3 tok/s
```

**237.3 tok/s remains a valid historical lane-sum, not a clean wall-clock aggregate.** It is no longer the preferred IQ3_XXS headline concurrent-serving number now that a clean 0.1.22 wall aggregate exists.

## Full-window concurrency validation

Three independent real software-review prompts were run concurrently with every lane configured for a 262K context window:

| Client | Input tokens | Output tokens | Finish |
| --- | ---: | ---: | --- |
| A | 141,578 | 992 | `stop` |
| B | 144,875 | 1,295 | `stop` |
| C | 144,777 | 871 | `stop` |

All three inputs exceeded the former 131,072-token per-lane limit. No context-overflow error, CUDA OOM, API failure, or lane death occurred.

This run remains **262K ×3 capacity and client-compatibility evidence**, not a canonical throughput benchmark.

## Current IQ3_S performance — Strata 0.1.22

IQ3_S was rerun on the same promoted `9dda206` / 0.1.22 engine with the same `262144 / 262144 / 262144` context policy, `32768` resident KV per lane, `5 / 6 / 5` physical-core split, and `0.55 / 0.25 / 0.55` PCIe fractions.

Current runtime sizing:

- shared expert arena: **46.84 GiB**;
- hot-expert cache: **4524 slots / 8.63 GiB per lane**;
- fully-loaded VRAM free: about **225 MiB per lane**.

### IQ3_S clean warm wall aggregate

Four retained warm rounds across two backend sessions measured:

```text
183.9 / 190.8 / 196.8 / 209.7 tok/s wall aggregate
```

The current reproducible range is therefore **183.9–209.7 tok/s**, with a four-round mean of **195.3 tok/s**.

This wall-derived aggregate replaces the older **183.4 tok/s lane-sum** as the preferred IQ3_S concurrent-serving headline. The old value remains historical lane-local evidence and is not directly comparable to wall aggregate.

### IQ3_S concurrent 15K no-reuse PP

Each lane received **15,048 prompt tokens** with **0 reused**:

| Lane | PP | Following TG |
| --- | ---: | ---: |
| GPU0 / x8 | **2,325.6 tok/s** | 42.9 tok/s |
| GPU1 / x4 | **1,806.5 tok/s** | 48.8 tok/s |
| GPU2 / x8 | **2,293.0 tok/s** | 45.5 tok/s |

The x8 mean was **2,309.3 tok/s**; the x4 middle lane was about **21.8% slower**.

### IQ3_S concurrent 30K no-reuse PP

Each lane received **30,024 prompt tokens** with **0 reused**:

| Lane | PP | Following TG |
| --- | ---: | ---: |
| GPU0 / x8 | **2,352.1 tok/s** | 44.5 tok/s |
| GPU1 / x4 | **1,812.9 tok/s** | 50.0 tok/s |
| GPU2 / x8 | **2,348.3 tok/s** | 46.2 tok/s |

The three-lane mean was **2,171.1 tok/s/lane**. The x8 mean was **2,350.2 tok/s**; the x4 middle lane was about **22.9% slower**.

The historical ~30K IQ3_S dataset measured **1,553.7 / 1,323.9 / 1,545.1 tok/s**. Relative to that older benchmark generation, the new rates are approximately **+51.4% / +36.9% / +52.0%**, with a three-lane mean increase of about **+47.3%**. This is an indicative software-generation comparison, not a strict same-prompt A/B.

No retained 0.1.22 IQ3_S long-prompt run had prompt reuse, CUDA OOM, API failure, or lane death.

Full IQ3_S details and measurement caveats are in [`docs/iq3-s-3lane-benchmark-20260929.md`](docs/iq3-s-3lane-benchmark-20260929.md).

## Controlled systems ablations — IQ3_S

A separate 2026-09-29 benchmark set isolates scaling, RAM sharing, and heterogeneous-lane isolation. It uses the same 0.1.22 / `9dda206` IQ3_S software generation but is **not** a replacement for the promoted clean-warm result above.

### 1 → 2 → 3 GPU scaling

Five 512-token steady-state decode repetitions per point, shared expert arena, 262K context per lane, 32K resident KV. The two-GPU point uses the two x8 RTX 5070 Ti cards before adding the x4 middle card.

| Active lanes | Mean wall aggregate | Speedup | Parallel efficiency |
| ---: | ---: | ---: | ---: |
| 1 | **72.59 tok/s** | 1.000× | 100.0% |
| 2 | **137.01 tok/s** | **1.887×** | **94.4%** |
| 3 | **188.23 tok/s** | **2.593×** | **86.4%** |

### Shared arena RAM ablation

Two otherwise matched 32K-context / 8K-resident-KV lanes were measured after both engines were ready.

| Arena mode | Two-engine PSS |
| --- | ---: |
| Private arena per process | **95.33 GiB** |
| Shared arena | **52.03 GiB** |
| Reduction | **43.30 GiB / 45.4%** |

### Heterogeneous isolation — RTX 5070 Ti + RTX 5060 Ti

A 5070 Ti x8 lane was measured alone and then while a 5060 Ti x4 lane served its own request concurrently, five 512-token repetitions in each condition.

| Measurement | Mean TG |
| --- | ---: |
| RTX 5070 Ti alone | **70.336 tok/s** |
| RTX 5070 Ti with RTX 5060 Ti active | **70.321 tok/s** |
| RTX 5060 Ti concurrent lane | **57.246 tok/s** |

The measured 5070 Ti decrease was **0.0215%**; its concurrent/solo ratio was **0.999785**. This is far smaller than run-to-run variance, so on this host the slower 5060 Ti lane did not measurably reduce the faster 5070 Ti lane's decode rate.

This is direct evidence for the intended request-level isolation property: a slower card slows its own request rather than becoming a mandatory token-step pace setter for the faster card. It remains a measured-host result, not a universal no-contention guarantee for every CPU/PCIe topology.

### Expert free-slot admission H2D timing

IQ3_S expert blobs span 1.440–2.539 MiB. A 200-iteration-per-size CUDA-runtime microbenchmark measured layer-distribution-weighted wall means of:

- RTX 5070 Ti x8: **0.081 ms pinned**, **0.117 ms ordinary resident/pageable**;
- RTX 5060 Ti x4: **0.155 ms pinned**, **0.190 ms ordinary resident/pageable**.

Largest-blob pageable p95 wall time was **0.140 ms** on the 5070 Ti x8 and **0.244 ms** on the 5060 Ti x4.

These are **free-slot admission transfer** measurements, not full-cache miss penalties. The current hot-expert cache has no eviction; once full, a non-resident expert uses the CPU path instead of replacing a resident GPU expert.

Full methodology and caveats: [`docs/systems-ablation-20260929.md`](docs/systems-ablation-20260929.md).  
Machine-readable retained observations: [`bench/systems-ablation-20260929.csv`](bench/systems-ablation-20260929.csv).

## Promotion decision

**Accepted:** Strata 0.1.22 / fork commit `9dda206` is the current promoted engine baseline for this recipe, and the 0.1.22 IQ3_S measurements above are the current IQ3_S benchmark generation.

The architecture decision is unchanged:

- baseline: independent request/session lanes sharing one host expert arena;
- challenger: upstream layer-split in the same fork;
- promotion criterion: representative end-to-end concurrent workload, required context capacity, correctness, stability, and fallback behavior—not a single-request win alone.

IQ3_XXS remains the performance-oriented comparison profile. IQ3_S is the current quality-oriented deployment on the reference host; a controlled same-prompt quality/performance A/B is still required before making a universal quantization recommendation.

## Reporting rule

For this repository:

- **226.5–227.9 tok/s** is the current promoted IQ3_XXS clean warm **wall aggregate**;
- **2,492.2 tok/s** is the promoted IQ3_XXS **15,064-token no-reuse single-lane PP spot check**;
- **183.9–209.7 tok/s**, mean **195.3 tok/s**, is the current IQ3_S clean warm **wall-aggregate range** across four retained warm rounds;
- **72.59 / 137.01 / 188.23 tok/s** is the separate controlled IQ3_S **1→2→3 GPU scaling** dataset, not a replacement warm headline;
- **95.33 → 52.03 GiB PSS** is the controlled two-lane **private→shared arena RAM ablation**;
- **70.336 → 70.321 tok/s** on the RTX 5070 Ti while an RTX 5060 Ti x4 runs at **57.246 tok/s** is the controlled **heterogeneous-isolation** dataset;
- IQ3_S 15K no-reuse PP is **2,325.6 / 1,806.5 / 2,293.0 tok/s**;
- IQ3_S 30K no-reuse PP is **2,352.1 / 1,812.9 / 2,348.3 tok/s**;
- **237.3 tok/s** and **183.4 tok/s** are retained as historical engine-reported **lane-sums**, not wall aggregates;
- the 141K–145K ×3 run is capacity/stability/client-compatibility evidence;
- expert-admission H2D numbers describe **free-slot transfer**, not current full-cache miss replacement;
- do not infer universal version, undervolt, quantization, architecture, or heterogeneous-topology speedups from mismatched prompt lengths, prompt content, or metric classes.

## More detail

- [`docs/systems-ablation-20260929.md`](docs/systems-ablation-20260929.md) — controlled scaling, RAM-sharing, heterogeneous-isolation and expert-admission results
- [`bench/systems-ablation-20260929.csv`](bench/systems-ablation-20260929.csv) — machine-readable retained observations for those controlled experiments
- [`docs/strata-0.1.22-promotion-20260929.md`](docs/strata-0.1.22-promotion-20260929.md) — current engine promotion, A/B smoke, and current IQ3_S validation
- [`docs/iq3-s-3lane-benchmark-20260929.md`](docs/iq3-s-3lane-benchmark-20260929.md) — current IQ3_S three-lane benchmark
- [`docs/undervolt-v2-20260929.md`](docs/undervolt-v2-20260929.md) — historical second-undervolt GPU tuning and lane-local IQ3_XXS dataset
- [`docs/reference-host-validation-20260929.md`](docs/reference-host-validation-20260929.md) — sanitized full-window and serving validation
- [`bench/README.md`](bench/README.md) — measurement/reporting rules
- [`docs/multigpu-shared-runtime.md`](https://github.com/rhgo1749/Strata/blob/main/docs/multigpu-shared-runtime.md) — generic implementation contract
- [`docs/multigpu-roadmap.md`](https://github.com/rhgo1749/Strata/blob/main/docs/multigpu-roadmap.md) — generic implementation roadmap
