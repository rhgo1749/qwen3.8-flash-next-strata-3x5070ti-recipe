# Results

This repository owns the reference-host measurements for the GPU-per-lane Strata recipe. Generic runtime contracts stay in the implementation fork; machine-specific performance evidence lives here.

## Current promoted implementation

```text
repository       rhgo1749/Strata
promoted commit  6cf101d5b98523cbaefc34a199faa5657c5c2719
upstream 0.1.27  a79080535d1b2a71a3419a0d97d8e7dca194b0f1
engine           Strata 0.1.27
binary sha256    b40c2cee92b4681d861548c7140219f4cc62ca47d28a6835020055e78266dee0
```

The 0.1.27 sync preserves the production architecture: one independent engine/request lane per GPU, one shared host expert arena, lane-local CUDA/KV/cache/speculation state, and no mandatory token-step cross-GPU synchronization.

## 0.1.30 measurement candidate

The current implementation candidate is frozen at `rhgo1749/Strata-Lanes@7c95b2aa3799f1918f7450bae542d7bbe4f67284`, based on upstream Strata `30ec18ec7094550fcc594fd948220d511d80464e` (v0.1.30). The unpromoted 0.1.29 candidate was superseded before its full headline matrix was completed, so its intermediate measurements remain diagnostic only.

The 0.1.30 candidate adopts upstream's native shared-expert-arena primitive contributed through PR #129, removes the fork's duplicate pinned-arena implementation, adds stale-port preflight, and exposes opt-in exact lane-admission telemetry for the overload campaign. Its source/test/build and real two-lane shared-arena smoke gates have passed, but **none of the 0.1.27 headline numbers below are relabeled as 0.1.30 results**.

Promotion requires a fresh same-generation campaign covering 1→2→3 lane scaling, private↔shared PSS, heterogeneous isolation, workload sensitivity, mixed three-lane serving, PP/TTFT/TG and complete provenance. The extension campaign additionally covers three-lane oversubscription at 3/4/6/9 requests and a matched 0.1.30 independent-lanes↔three-GPU layer-split A/B. See [`bench/strata-0.1.30-campaign.md`](bench/strata-0.1.30-campaign.md) and [`bench/strata-0.1.30-candidate-20261001.csv`](bench/strata-0.1.30-candidate-20261001.csv).

Until that campaign is complete, **0.1.27 remains the promoted evidence generation**.

## Reference host

- CPU: AMD Ryzen 9 9950X3D, 16C/32T
- RAM: 128 GB DDR5
- GPU0: RTX 5070 Ti 16 GB, PCIe x8
- GPU1: RTX 5070 Ti 16 GB, PCIe x4
- GPU2: RTX 5070 Ti 16 GB, PCIe x8
- GPU3: RTX 5060 Ti 16 GB, PCIe x4
- driver: NVIDIA 615.71.09
- CUDA toolchain: 13.4
- paper-validation model: Qwen3.8-Flash-Next GSQ-RCO IQ3_S

Reference three-lane order is GPU0/GPU2/GPU1 = x8/x8/x4.

## 0.1.27 validation gate

- `pytest serve -q`: **77 passed, 3 skipped, 47 subtests passed**.
- server + multi-GPU subset: **53 passed, 39 subtests passed**.
- `file_expert_source_test`: **PASS**.
- `pinned_upstream_impl.cu` is byte-identical to upstream 0.1.27 `pinned.cu` (Git blob `0e3e6b4a...`).
- lane configs strip inherited `gpu` and `layer_split`.
- shared-arena interception is exact-size/environment gated; the ordinary upstream `mmap` path remains unchanged when those variables are absent.

Machine-readable gate: [`bench/strata-0.1.27-promotion-20260930.csv`](bench/strata-0.1.27-promotion-20260930.csv).

## Fresh 0.1.27 systems evidence

### 1 -> 2 -> 3 GPU scaling

Fixed prompt, 512 completion tokens/lane, 262144 context/lane, 32768 resident KV/lane, five retained repetitions per point. Aggregate TG uses a **single common wall interval**.

| Active lanes | Mean aggregate TG | SD | Speedup | Parallel efficiency |
| ---: | ---: | ---: | ---: | ---: |
| 1 | **71.45 tok/s** | 1.12 | 1.000× | 100.0% |
| 2 | **137.57 tok/s** | 2.19 | **1.926×** | **96.3%** |
| 3 | **191.75 tok/s** | 7.24 | **2.684×** | **89.5%** |

Ranges are 69.59–72.54, 133.83–139.08, and 182.63–199.20 tok/s. No retained slow run was discarded.

### Shared arena RAM ablation

| Arena mode | Two-engine PSS |
| --- | ---: |
| Private arena per process | **95.298 GiB** |
| Shared arena | **52.083 GiB** |
| Reduction | **43.215 GiB / 45.35%** |

The shared arena appears as the same `rw-s` `/dev/shm` mapping in both engines, with the 49,116,200 KiB mapping split by PSS and recorded as shared dirty rather than private dirty. This is physical-memory sharing evidence, not RSS inference.

### Heterogeneous isolation

Interleaved RTX 5070 Ti x8 solo vs RTX 5070 Ti x8 + RTX 5060 Ti x4 concurrent trials, 8 retained runs per condition:

| Measurement | Mean TG | SD |
| --- | ---: | ---: |
| RTX 5070 Ti x8 solo | **73.01** | 1.41 |
| RTX 5070 Ti x8 concurrent | **72.36** | 2.26 |
| RTX 5060 Ti x4 concurrent | **59.14** | 1.24 |

Nominal fast-lane difference: **0.89%**. Because this is smaller than ordinary run-to-run dispersion, the paper-safe conclusion is **no measurable degradation within run-to-run variance**, not a universal 0.89% slowdown claim.

### Mixed real-serving support run

Fiction/coding/reasoning were rotated across the three 5070 Ti lanes. Nine common-wall runs produced **187.15 ± 5.63 tok/s** aggregate, range **176.85–196.18 tok/s**. This is supporting evidence, not the controlled scaling headline.

Full systems methodology: [`docs/systems-ablation-0.1.27-20260930.md`](docs/systems-ablation-0.1.27-20260930.md).  
Raw retained observations: [`bench/systems-ablation-0.1.27-20260930.csv`](bench/systems-ablation-0.1.27-20260930.csv).

## 0.1.27 workload sensitivity

Five repetitions were retained per workload/bucket/state. No-reuse PP and warm steady-state TG are kept as separate measurement classes.

### No-reuse PP / TTFT

| Workload | Prompt size | Mean PP | Mean TTFT |
| --- | ---: | ---: | ---: |
| Fiction short | 1,517 | **887.88 tok/s** | 1.73 s |
| Coding short | 1,446 | **895.93 tok/s** | 1.64 s |
| Reasoning short | 1,490 | **939.10 tok/s** | 1.61 s |
| Fiction medium | 14,957 | **2553.38 tok/s** | 5.91 s |
| Coding medium | 15,012 | **2542.27 tok/s** | 5.96 s |
| Reasoning medium | 15,026 | **2553.71 tok/s** | 5.94 s |
| Long review | 109,958 | **2554.09 tok/s** | 43.32 s |

At matched ~15K lengths, content-class PP means are within about 0.5%; prompt-length regime is the larger effect in this matrix.

### Warm decode / locality / speculation

| Workload | Mean TG | Cache hit | Spec acceptance |
| --- | ---: | ---: | ---: |
| Fiction short | **68.64** | 90.56% | 50.77% |
| Fiction medium | **67.98** | 89.42% | 56.28% |
| Coding short | **79.30** | 86.96% | 73.70% |
| Coding medium | **79.42** | 86.22% | 75.27% |
| Reasoning short | **76.98** | 87.78% | 72.14% |
| Reasoning medium | **68.06** | 86.50% | 63.66% |
| Long review | **62.98** | 84.14% | 68.73% |

Fiction has higher cache-hit rates than coding while coding is faster, so expert-cache hit rate alone does not explain TG ordering. Speculative acceptance also differs materially by workload. The dataset is observational and does not claim causation.

All retained workload windows report **zero adaptive swap publications**, so workload-specific adaptive-replacement benefit is **not** established by this matrix.

Full analysis: [`docs/workload-sensitivity-0.1.27-20260930.md`](docs/workload-sensitivity-0.1.27-20260930.md).  
Raw repetitions: [`bench/workload-sensitivity-0.1.27-20260930.csv`](bench/workload-sensitivity-0.1.27-20260930.csv).

## Historical evidence

Historical files are intentionally retained rather than overwritten.

### 0.1.24

The previous promoted engine generation recorded IQ3_S three-lane clean-warm aggregate **176.8–199.4 tok/s, mean 187.1**, plus the controlled adaptive-on/off result **69.43 vs 54.14 tok/s (+28.3%)**. See [`docs/strata-0.1.24-promotion-20260930.md`](docs/strata-0.1.24-promotion-20260930.md).

### Earlier architecture ablation / 0.1.22 generation

The historical controlled systems set reported:

- scaling: **72.59 -> 137.01 -> 188.23 tok/s**;
- private/shared PSS: **95.33 -> 52.03 GiB**;
- heterogeneous: **70.336 solo / 70.321 concurrent / 57.246 slow lane**.

The fresh 0.1.27 results reproduce the same qualitative architecture conclusions. Do not treat unmatched prompt/engine generations as a strict software speed comparison.

See [`docs/systems-ablation-20260929.md`](docs/systems-ablation-20260929.md) and [`bench/systems-ablation-20260929.csv`](bench/systems-ablation-20260929.csv).

## Paper-safe claims

For this reference host and the retained 0.1.27 IQ3_S configuration, the fresh data supports:

- request-per-GPU lanes scale strongly through three GPUs;
- shared host expert backing materially reduces physical host-memory use;
- a slower independent lane does not measurably pace the faster lane within observed variance;
- real workload class affects decode behavior, expert locality, and speculative acceptance;
- ~110K no-reuse review input remains stable with ~2.55k tok/s PP and ~43.3 s TTFT on the measured x8 lane.

## Claims not justified

- universal scaling/slowdown constants across other hosts or GPUs;
- causal attribution of workload TG differences to cache hit rate or speculation without controlled A/Bs;
- workload-specific adaptive replacement benefit from this measurement generation;
- PCIe-width PP effects from the single-lane workload matrix;
- strict version speedups from unmatched historical runs.

## Reproducibility caveat

The recovered 0.1.27 benchmark bundle did not include a dedicated benchmark-start snapshot of GPU clock/undervolt state. The repository's reference tuning profile remains documented separately, but this run does not claim that tuning metadata as independently verified provenance.

## Current artifacts

- [`docs/systems-ablation-0.1.27-20260930.md`](docs/systems-ablation-0.1.27-20260930.md)
- [`docs/workload-sensitivity-0.1.27-20260930.md`](docs/workload-sensitivity-0.1.27-20260930.md)
- [`bench/systems-ablation-0.1.27-20260930.csv`](bench/systems-ablation-0.1.27-20260930.csv)
- [`bench/workload-sensitivity-0.1.27-20260930.csv`](bench/workload-sensitivity-0.1.27-20260930.csv)
- [`bench/strata-0.1.27-promotion-20260930.csv`](bench/strata-0.1.27-promotion-20260930.csv)
