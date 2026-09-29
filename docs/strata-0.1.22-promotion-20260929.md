# Strata 0.1.22 promotion — 2026-09-29

This record promotes the reference GPU-per-lane recipe from the Strata 0.1.21 integration baseline to the upstream-synced **Strata 0.1.22** fork state.

## Decision

**Accepted.** The current promoted recipe implementation is:

```text
repository  rhgo1749/Strata
commit      9dda206874387b20cac20837a1452f115a8f9f93
engine      0.1.22
architecture independent request-per-GPU lanes + one shared host expert arena
```

The architecture decision did not change. Upstream layer-split remains available in the same fork as a challenger path, while request-per-lane serving remains the production baseline for the target concurrent-agent workload.

## Reference host and unchanged recipe contract

```text
CPU                 Ryzen 9 9950X3D, 16C/32T
RAM                 128 GB DDR5
GPUs                RTX 5070 Ti 16 GB ×3
PCIe                Gen5 x8 / x4 / x8
model               Qwen3.8-Flash-Next IQ3_XXS
lane contexts        262144 / 262144 / 262144
host-KV guard        786432 tokens
resident KV          32768 / 32768 / 32768
physical CPU cores   5 / 6 / 5
pcie-frac            0.55 / 0.25 / 0.55
shared expert arena  ~39.97 GiB
```

The existing multi-lane recipe/CLI remained compatible. No new migration flag was required.

## Validation gates

The 0.1.22 candidate passed:

- server / multi-GPU / detokenizer tests: **41 passed, 3 skipped**;
- CUDA build: **121 / 121 build steps completed**;
- IQ3_XXS three-lane startup at **262K ×3**;
- unchanged shared-arena size and lane cache sizing;
- short single-lane decode smoke;
- repeated warm three-request wall-clock throughput;
- 15K no-reuse prompt-processing spot check;
- upstream 3-GPU layer-split startup at 262K;
- layer-split short decode and 15K prompt-processing smoke.

## Current promoted measurements

### Request-per-lane baseline (A)

Three identical concurrent short requests were warmed first so every lane could reuse the same short prefix. The two retained warm rounds were:

| Warm round | Completion tokens | Wall time | Wall aggregate |
| --- | ---: | ---: | ---: |
| 1 | 384 | 1.685 s | **227.9 tok/s** |
| 2 | 384 | 1.695 s | **226.5 tok/s** |

Current clean warm wall aggregate: **226.5–227.9 tok/s** (midpoint about **227.2 tok/s**).

Per-lane engine-reported TG in those rounds was roughly 79–85 tok/s; those lane-local rates are not substituted for the wall aggregate.

A no-reuse **15,064-token** prompt on one 262K lane processed in **6,044 ms = 2,492.2 tok/s**, followed by 16 generated tokens at 67.6 tok/s.

A short single-lane smoke on the same 0.1.22 candidate processed 79 prompt tokens and generated 128 tokens at **69.5 tok/s**. This short smoke is retained for compatibility, not promoted as the canonical multi-lane throughput number.

### Upstream layer-split challenger (B)

The same fork binary also started the upstream 3-GPU layer-split path at 262K successfully.

- short single-request decode: **80.6 tok/s**;
- 15,064-token no-reuse prompt processing: **1,142.3 tok/s**;
- following 16-token decode: **82.3 tok/s**.

For the retained 15K prompt-processing probe, request-per-lane A was about **2.18×** the B prompt-processing rate (2,492.2 / 1,142.3). B still showed the expected single-request decode advantage.

## 0.1.21 historical comparison

The immediately preceding 0.1.21 integration validation recorded:

- A warm three-request wall aggregate: **198.2 tok/s**;
- A ~15K prompt-processing spot check: **1,609.9 tok/s**.

Against those specific promotion runs, 0.1.22 measured approximately:

- **+14.6%** warm wall aggregate (227.2 vs 198.2 tok/s);
- **+54.8%** on the retained ~15K prompt-processing spot check (2,492.2 vs 1,609.9 tok/s).

These deltas are software-version promotion comparisons on the same reference architecture, not universal model-level speedup claims.

## Relationship to the older 237.3 tok/s lane-sum

The earlier second-undervolt record of **237.3 tok/s** remains valid as a historical **lane-sum of engine-reported TG**. It was never a clean wall-clock aggregate.

The 0.1.22 promotion therefore changes the headline concurrent-serving metric to the measured **226.5–227.9 tok/s wall aggregate** rather than replacing one lane-sum with another lane-sum.

Likewise, the older 45K–65K no-reuse PP observations remain useful historical long-prompt spot checks, but they are a different prompt-length/run generation and should not be directly treated as the denominator for the new 15K result.

## Architecture promotion outcome

The request-per-lane design remains promoted because the target workload is concurrent independent agent requests. The layer-split challenger remains available for workloads where single-request decode latency is more important.

A challenger should replace the baseline only after it wins the roadmap gates on representative concurrent serving, required context capacity, correctness, stability, and fallback behavior—not from a single-request result alone.
