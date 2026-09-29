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
- model: Qwen3.8-Flash-Next, Strata IQ3_XXS

## Reference three-lane policy

```text
lane contexts       262144 / 262144 / 262144
host-KV guard       786432 tokens
resident KV         32768 / 32768 / 32768
physical CPU cores  5 / 6 / 5
pcie-frac           0.55 / 0.25 / 0.55
shared expert arena ~39.97 GiB
```

## Current promoted IQ3_XXS performance — Strata 0.1.22

### Clean warm three-request wall aggregate

Three identical concurrent short requests were warmed so each lane could reuse the same short prefix. The retained warm rounds were:

| Warm round | Completion tokens | Wall time | Aggregate TG |
| --- | ---: | ---: | ---: |
| 1 | 384 | 1.685 s | **227.9 tok/s** |
| 2 | 384 | 1.695 s | **226.5 tok/s** |

**Current promoted concurrent-serving result: 226.5–227.9 tok/s wall aggregate** (midpoint about 227.2 tok/s).

This is the preferred headline multi-lane throughput metric because it comes from a common wall interval. Per-lane engine-reported TG in the retained warm rounds was roughly 79–85 tok/s and should not be substituted for the wall aggregate.

### 15K no-reuse prompt-processing spot check

One 262K lane processed a **15,064-token** no-reuse prompt in **6,044 ms**, or **2,492.2 tok/s**, followed by 16 generated tokens at 67.6 tok/s.

This is a promoted 0.1.22 software-version spot check on the reference host. It is not a universal long-prompt PP claim: prompt length/content matters, and the older 45K–65K PP dataset is a different benchmark generation.

### Single-lane short smoke

A short compatibility smoke on the 0.1.22 candidate processed 79 prompt tokens and generated 128 tokens at **69.5 tok/s**. This is retained as a functional/single-lane observation, not the canonical aggregate result.

## Upstream layer-split challenger on the same 0.1.22 fork

The same `9dda206` fork binary also preserved upstream 3-GPU layer-split at 262K.

| Measurement | Layer-split result |
| --- | ---: |
| Short single-request decode | **80.6 tok/s** |
| 15,064-token no-reuse PP | **1,142.3 tok/s** |
| Following 16-token decode | **82.3 tok/s** |

For the retained 15K prompt-processing probe, request-per-lane A measured about **2.18×** the layer-split B rate (2,492.2 / 1,142.3). Layer-split still showed the expected single-request decode advantage.

This does not promote one design universally. For this recipe's target concurrent-agent workload, independent lanes remain the production baseline; layer-split remains a useful challenger for single-request-oriented workloads.

## 0.1.21 historical promotion baseline

The immediately preceding 0.1.21 integration validation measured:

- warm three-request wall aggregate: **198.2 tok/s**;
- ~15K prompt-processing spot check: **1,609.9 tok/s**.

Against those specific same-host promotion runs, 0.1.22 measured about:

- **+14.6%** warm wall aggregate (227.2 vs 198.2 tok/s);
- **+54.8%** on the retained ~15K prompt-processing spot check (2,492.2 vs 1,609.9 tok/s).

These percentages describe this promotion comparison only; they are not universal speedup claims for every prompt or workload.

## Historical second-undervolt lane-local observation

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

**237.3 tok/s remains a valid historical lane-sum, not a clean wall-clock aggregate.** It is no longer the preferred headline concurrent-serving number now that a clean 0.1.22 wall aggregate exists.

## Historical no-reuse PP spot checks

Older independent lane observations after the second undervolt were:

| Lane | Prompt tokens | PP | Following TG |
| --- | ---: | ---: | ---: |
| GPU0 | 45,519 | **1,529.7 tok/s** | 56.4 tok/s |
| GPU1 | 45,812 | **1,421.6 tok/s** | 50.1 tok/s |
| GPU2 | 64,972 | **1,536.9 tok/s** | 57.2 tok/s |

Mean PP was about **1,496 tok/s/lane**. These remain useful historical longer-prompt observations, but they are not directly comparable to the promoted 15K 0.1.22 probe because prompt length/content and software generation differ.

## Full-window concurrency validation

Three independent real software-review prompts were run concurrently with every lane configured for a 262K context window:

| Client | Input tokens | Output tokens | Finish |
| --- | ---: | ---: | --- |
| A | 141,578 | 992 | `stop` |
| B | 144,875 | 1,295 | `stop` |
| C | 144,777 | 871 | `stop` |

All three inputs exceeded the former 131,072-token per-lane limit. No context-overflow error, CUDA OOM, API failure, or lane death occurred.

This run remains **262K ×3 capacity and client-compatibility evidence**, not a canonical throughput benchmark.

## IQ3_S challenger profile — 2026-09-29

A clean three-lane IQ3_S run was also completed on the same reference host with the same `262144 / 262144 / 262144` context policy, `32768` resident KV per lane, `5 / 6 / 5` physical-core split, and `0.55 / 0.25 / 0.55` PCIe fractions.

Key clean observations:

- shared expert arena: **46.84 GiB**;
- hot-expert cache: **4548 slots / 8.67 GiB per lane**;
- controlled concurrent short TG: **60.5 / 63.8 / 59.1 tok/s**;
- short TG lane-sum: **183.4 tok/s**;
- concurrent ~30K no-reuse PP: **1,553.7 / 1,323.9 / 1,545.1 tok/s**;
- the x4 middle lane was about **14.6% slower** in PP than the mean of the two x8 lanes;
- no lane death or CUDA OOM occurred during the run.

IQ3_S remains a quality-oriented challenger profile rather than the canonical performance profile. Its results were collected in a separate benchmark generation and should not be mixed into the 0.1.22 IQ3_XXS software-promotion deltas.

## Promotion decision

**Accepted:** Strata 0.1.22 / fork commit `9dda206` is the current promoted engine baseline for this recipe.

The multi-GPU architecture decision is unchanged:

- production baseline: independent request/session lanes sharing one host expert arena;
- challenger: upstream layer-split in the same fork;
- promotion criterion: representative end-to-end concurrent workload, required context capacity, correctness, stability, and fallback behavior—not a single-request win alone.

## Reporting rule

For this repository:

- **226.5–227.9 tok/s** is the current promoted clean warm **wall aggregate** for three concurrent short requests on 0.1.22;
- **2,492.2 tok/s** is the promoted **15,064-token no-reuse single-lane PP spot check**, not a universal long-context PP claim;
- **237.3 tok/s** is retained as a historical engine-reported **lane-sum**, not a wall aggregate;
- the 141K–145K ×3 run is capacity/stability/client-compatibility evidence;
- **183.4 tok/s** remains the IQ3_S historical controlled short lane-sum;
- do not infer universal version, undervolt, quantization, or architecture speedups from mismatched prompt lengths or benchmark classes.

## More detail

- [`docs/strata-0.1.22-promotion-20260929.md`](docs/strata-0.1.22-promotion-20260929.md) — current engine promotion, A/B smoke, and 0.1.21 comparison
- [`docs/undervolt-v2-20260929.md`](docs/undervolt-v2-20260929.md) — historical second-undervolt GPU tuning and lane-local IQ3_XXS dataset
- [`docs/iq3-s-3lane-benchmark-20260929.md`](docs/iq3-s-3lane-benchmark-20260929.md) — IQ3_S three-lane challenger benchmark
- [`docs/reference-host-validation-20260929.md`](docs/reference-host-validation-20260929.md) — sanitized full-window and serving validation
- [`bench/README.md`](bench/README.md) — measurement/reporting rules
- [`docs/multigpu-shared-runtime.md`](https://github.com/rhgo1749/Strata/blob/main/docs/multigpu-shared-runtime.md) — generic implementation contract
- [`docs/multigpu-roadmap.md`](https://github.com/rhgo1749/Strata/blob/main/docs/multigpu-roadmap.md) — generic implementation roadmap
