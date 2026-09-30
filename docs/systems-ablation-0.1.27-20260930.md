# Strata 0.1.27 systems validation — 2026-09-30

This record is the current paper-facing systems evidence after the fork was advanced to upstream Strata 0.1.27. Historical 0.1.22/0.1.24 measurements remain version history and are not strict software A/Bs unless the measurement contract matches.

## Baseline provenance

| Item | Value |
| --- | --- |
| Fork | `rhgo1749/Strata` |
| Fork HEAD | `6cf101d5b98523cbaefc34a199faa5657c5c2719` |
| Upstream 0.1.27 | `a79080535d1b2a71a3419a0d97d8e7dca194b0f1` |
| Binary | `build-production-027/strata` |
| Binary SHA-256 | `b40c2cee92b4681d861548c7140219f4cc62ca47d28a6835020055e78266dee0` |
| NVIDIA driver / CUDA | 615.71.09 / 13.4 |
| Model / quant | Qwen3.8-Flash-Next GSQ-RCO IQ3_S |
| CPU / RAM | Ryzen 9 9950X3D / 128 GB DDR5 |
| GPUs | GPU0 5070 Ti x8; GPU1 5070 Ti x4; GPU2 5070 Ti x8; GPU3 5060 Ti x4 |

The three-lane architecture runs use GPU order **0,2,1 = x8+x8+x4**.

Validation gate:

- `pytest serve -q`: **77 passed, 3 skipped, 47 subtests passed**;
- server + multi-GPU subset: **53 passed, 39 subtests passed**;
- `file_expert_source_test`: PASS;
- `pinned_upstream_impl.cu` is the same Git blob as upstream 0.1.27 `src/core/pinned.cu` (`0e3e6b4...`);
- lane configs strip inherited `gpu` and `layer_split`;
- shared-arena interception is environment- and exact-size-gated, leaving the ordinary upstream mmap path unchanged when disabled.

## Controlled 1 -> 2 -> 3 lane scaling

Fixed prompt hash: `429fe691f25560a1`. Every retained run generates 512 completion tokens per active lane after warm-up. Context is 262144/lane and resident KV is 32768/lane. The primary metric is **total completion tokens divided by one common client wall interval**, not the sum of lane-local engine TG.

| Active lanes | n | Mean aggregate TG | SD | Min–max | Speedup | Efficiency |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 5 | **71.45 tok/s** | 1.12 | 69.59–72.54 | 1.000× | 100.0% |
| 2 | 5 | **137.57 tok/s** | 2.19 | 133.83–139.08 | **1.926×** | **96.3%** |
| 3 | 5 | **191.75 tok/s** | 7.24 | 182.63–199.20 | **2.684×** | **89.5%** |

The harness uses the **same prompt, temperature 0, and seed 1234 for every scaling repetition**. The 1- and 2-lane CSVs consequently share identical per-repetition cache/spec summaries, while the runtime's warm/cache/spec state evolves across successive repetitions. The five repetitions are therefore **not strictly IID**. Approximate t-based intervals may be useful as descriptive summaries of this stateful sequence but should not be interpreted as population-level IID confidence intervals.

No completed scaling observation was discarded.

## Shared arena physical-memory ablation

Two IQ3_S lanes were run at 32768 context and 8192 resident KV so the private control remained feasible. PSS comes from `/proc/<pid>/smaps_rollup` after both engines were fully ready.

| Arena mode | Two-engine PSS | Host-global used swap |
| --- | ---: | ---: |
| Private per-engine arena | **95.298 GiB** | **9.443 GiB** |
| Shared arena | **52.083 GiB** | **5.704 GiB** |
| PSS difference | **43.215 GiB / 45.35%** | — |

The shared arena is the same 49,116,200 KiB `rw-s` `/dev/shm` mapping in both processes. It is attributed as `Shared_Dirty=49,116,200 KiB` and `Private_Dirty=0`, with approximately half of the mapping attributed to each process by PSS. This is direct OS-level physical-sharing evidence.

### Swap accounting caveat

The public CSV's `swap_gib` field is **host-global used swap**, derived from `/proc/meminfo` as `(SwapTotal-SwapFree)`, not per-engine swap. Numerically, `PSS + host-global used swap` is 104.74 GiB in the private snapshot and 57.79 GiB in the shared snapshot, a 46.95-GiB difference close to the 46.84-GiB arena. Because the swap counter covers the whole machine, this near-match is suggestive only and is **not** proof that the arena alone caused the swap delta. PSS remains the directly attributable process metric.

## Same-generation heterogeneous pair

Fast lane: RTX 5070 Ti x8 (GPU0). Concurrent slower lane: RTX 5060 Ti x4 (GPU3). Both use the same shared arena, 262144 context, 32768 resident KV, fixed prompt, temperature 0, seed 1234, and 512 generated tokens. Trials are interleaved in `ABBAABBAABBAABBA` order.

### Lane-local decode rates

| Measurement | n | Mean TG | SD |
| --- | ---: | ---: | ---: |
| 5070 Ti x8 solo | 8 | **73.01** | 1.41 |
| 5070 Ti x8 concurrent | 8 | **72.36** | 2.26 |
| 5060 Ti x4 concurrent | 8 | **59.14** | 1.24 |

The unadjusted fast-lane concurrent-minus-solo difference is **-0.65 tok/s (-0.9%)**. A Welch comparison is inconclusive (`p≈0.50`, 95% difference interval approximately `[-2.71,+1.41] tok/s`).

Per-run fast-lane TG is strongly associated with speculative acceptance (`r≈0.93` solo; `r≈0.95` concurrent). An exploratory OLS/ANCOVA sensitivity model,

```text
TG ~ concurrent + speculative_acceptance
```

estimates the concurrent coefficient at about **-1.00 tok/s (-1.4%)**, with 95% CI **[-1.71,-0.30] tok/s** and `p≈0.009`; residual SD is about 0.65 tok/s. Because speculative acceptance is measured during execution and may itself respond to concurrency, this coefficient is **not interpreted causally**.

**Paper-safe interpretation:** the unadjusted estimate is inconclusive; the acceptance-adjusted sensitivity model indicates a small shared-resource cost in this one measured 5070 Ti + 5060 Ti pair. Do not claim zero interference, and do not generalize a low-single-digit numerical bound to other lane counts or hardware combinations.

### Common-wall aggregate

The two lane-local TG means sum to about 131.5 tok/s, but that is not the fixed-length request aggregate. The retained concurrent requests complete at a **common-wall aggregate of 116.96 ± 2.42 tok/s**, because the wall interval extends until the slower request finishes. Report both views with their metric definitions rather than summing engine TG as though it were wall throughput.

## Mixed-content three-lane rotation

Fiction, coding, and reasoning are rotated across GPU0 x8 / GPU2 x8 / GPU1 x4. Nine retained common-wall runs produce:

- aggregate mean **187.15 ± 5.63 tok/s**;
- range **176.85–196.18 tok/s**.

Averaged lane-local TG across the rotations is approximately:

| GPU | Link | Mean lane TG | Mean cache hit |
| --- | --- | ---: | ---: |
| GPU0 | x8 | 66.27 | 0.860 |
| GPU2 | x8 | 67.03 | 0.866 |
| GPU1 | x4 | 66.99 | 0.816 |

This matrix does not isolate PCIe width, but it shows no obvious x4 lane-local TG penalty in the current mixed decode runs. Historical 0.1.22 IQ3_S concurrent 15K no-reuse PP did show the x4 lane at 1,806.5 tok/s versus a 2,309.3 tok/s x8 mean (**21.8% lower**). Because that is an earlier software generation, it is qualitative evidence that PCIe width can matter more for PP than the current mixed-decode TG matrix suggests.

## Historical layer-split context

The same fork lineage retained upstream Strata's native multi-GPU layer split. A historical 0.1.22 IQ3_XXS promotion record measured:

- 3-GPU layer-split short single-request decode: **80.6 tok/s**;
- layer-split 15,064-token no-reuse PP: **1,142.3 tok/s**;
- one request-per-lane 15,064-token PP probe: **2,492.2 tok/s**, followed by 67.6 tok/s for 16 generated tokens.

These values are **context only**, not a strict baseline for the current 0.1.27 IQ3_S experiments: engine generation, quant/profile, prompt contract, concurrency, and output length differ. Likewise, the historical 226.5–227.9 tok/s three-request aggregate used 384 total completion tokens and a different warm-run contract, so it should not be compared numerically with the current 512-token/lane scaling table.

## Implementation caveats relevant to the paper

The shared wrapper maps the arena `rw-s` and does not call `mprotect` after population. Each lane populates the arena during startup; sequential startup avoids simultaneous initial writes, but a live lane restart can rewrite pages other lanes map. The exact-size gate verifies allocation size/path, not model-content identity. The shared wrapper also rejects the upstream `MAP_HUGETLB` attempt for the target allocation and falls back to a regular file-backed mapping. The retained benchmark package does not contain the host hugetlb-pool state.

The three RTX 5070 Ti cards have a documented non-stock reference V/F profile (2300 MHz at >=875 mV, VRAM +2500), but the exact benchmark-start application state was not snapshotted. The RTX 5060 Ti tuning state is undocumented. The paper therefore discloses the profile without attributing final results to a precisely verified start-state setting.

## Data hygiene

- The heterogeneous raw JSONL has one malformed trailing fragment after the valid summary record. All 8 solo and 8 concurrent completed repetitions are valid and retained; the fragment is not a completed observation.
- The scaling dataset retains all completed runs, including the slowest 3-lane repetition.
- No claim is made that the 0.1.22/0.1.24/0.1.27 generations form strict software A/Bs unless their full measurement contracts match.

## Current paper-safe claims

Fresh 0.1.27 evidence directly supports these statements for this reference host and IQ3_S configuration:

1. Independent request-per-GPU lanes show strong common-wall scaling through three 5070 Ti GPUs, reaching a 2.684× point speedup and 89.5% point parallel efficiency under the controlled warm workload.
2. A shared host expert backing reduces the two-engine PSS snapshot by about 43.2 GiB (45.35%) and the arena mapping is physically shared at the OS level.
3. In one 5070 Ti + 5060 Ti pair, lane-local concurrency imposes a small shared-resource cost according to an acceptance-adjusted sensitivity model; the unadjusted difference alone is inconclusive.
4. Mixed request classes remain concurrently serviceable in the same broad aggregate-throughput regime as the controlled three-lane experiment.

## Claims not justified

- universal scaling or interference bounds across machines, GPU generations, lane counts, models, or quants;
- superiority over coupled layer/tensor/expert parallelism on the current 0.1.27 baseline;
- causal attribution of the heterogeneous adjusted coefficient to a specific CPU/DRAM/PCIe mechanism;
- a causal workload-specific relationship between cache hit/spec acceptance and TG;
- workload-specific adaptive-replacement benefit in this measurement generation.

## Artifacts

- `../bench/systems-ablation-0.1.27-20260930.csv` — retained scaling, RAM, heterogeneous and mixed observations;
- `../bench/strata-0.1.27-promotion-20260930.csv` — validation/provenance matrix;
- `workload-sensitivity-0.1.27-20260930.md` — workload-specific PP/TG/cache/spec analysis.
