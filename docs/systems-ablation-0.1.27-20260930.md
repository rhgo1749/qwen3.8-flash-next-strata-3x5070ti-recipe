# Strata 0.1.27 systems validation — 2026-09-30

This record re-runs the paper-facing systems checks after the fork was advanced to upstream Strata 0.1.27. It supersedes older versions only for the **current 0.1.27 baseline**; historical 0.1.22/0.1.24 evidence remains useful as version history.

## Baseline provenance

| Item | Value |
| --- | --- |
| Fork | `rhgo1749/Strata` |
| Fork HEAD | `6cf101d5b98523cbaefc34a199faa5657c5c2719` (`Sync upstream Strata 0.1.27`) |
| Upstream 0.1.27 | `a79080535d1b2a71a3419a0d97d8e7dca194b0f1` (`v0.1.27`) |
| Production patch lineage | retained from the promoted 0.1.26 shared-lane integration in the ancestry of `6cf101d` |
| Binary | `build-production-027/strata` |
| Binary SHA-256 | `b40c2cee92b4681d861548c7140219f4cc62ca47d28a6835020055e78266dee0` |
| NVIDIA driver | 615.71.09 |
| CUDA toolchain | 13.4 |
| Model / quant | Qwen3.8-Flash-Next GSQ-RCO IQ3_S |
| CPU / RAM | Ryzen 9 9950X3D, 128 GB DDR5 |
| GPUs | GPU0 RTX 5070 Ti x8; GPU1 RTX 5070 Ti x4; GPU2 RTX 5070 Ti x8; GPU3 RTX 5060 Ti x4 |

The 3-lane architecture runs use GPU order **0,2,1**, therefore x8+x8+x4.

### Validation gate

- `pytest serve -q`: **77 passed, 3 skipped, 47 subtests passed**.
- `pytest serve/test_server.py serve/test_multigpu_server.py -q`: **53 passed, 39 subtests passed**.
- `build-production-027/file_expert_source_test`: **PASS**.
- `src/core/pinned_upstream_impl.cu` and upstream 0.1.27 `src/core/pinned.cu` resolve to the same Git blob: `0e3e6b4a057bb292c44c44e7eaf45ba668497ba5`.
- The lane supervisor removes inherited `gpu` and `layer_split`; the corresponding anti-re-expansion test passes.
- Shared arena behavior remains explicitly environment-gated. With `STRATA_SHARED_ARENA_FILE` / `STRATA_SHARED_ARENA_BYTES` absent, the wrapper passes the upstream `mmap` path through unchanged.
- The 0.1.27 production binary served the real benchmark workloads below, so executable/startup validation is covered by the retained runs.

Machine-readable gate evidence: [`../bench/strata-0.1.27-promotion-20260930.csv`](../bench/strata-0.1.27-promotion-20260930.csv).

## Controlled 1 -> 2 -> 3 lane scaling

Fixed prompt hash: `429fe691f25560a1`. Each retained run generates 512 tokens per active lane after warm-up. Context is 262144/lane and resident KV is 32768/lane. The primary metric is **total concurrent completion tokens divided by one common wall interval**, not lane-sum TG.

| Active lanes | n | Mean aggregate TG | SD | Median | Min–max | Speedup | Parallel efficiency |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 5 | **71.45 tok/s** | 1.12 | 71.76 | 69.59–72.54 | 1.000× | 100.0% |
| 2 | 5 | **137.57 tok/s** | 2.19 | 138.51 | 133.83–139.08 | **1.926×** | **96.3%** |
| 3 | 5 | **191.75 tok/s** | 7.24 | 189.21 | 182.63–199.20 | **2.684×** | **89.5%** |

Approximate t-based 95% CIs for the means are 70.06–72.84, 134.85–140.30, and 182.77–200.74 tok/s respectively.

The 0.1.27 result therefore preserves strong request-level scaling on this reference host. The larger 3-lane variance should remain visible rather than being hidden by selecting only the faster repetitions.

### Historical context

The retained 0.1.22 architecture experiment reported 72.59 / 137.01 / 188.23 tok/s. The fresh 0.1.27 values are similar in shape and slightly higher at three lanes, but this document does **not** treat that as a strict software-version speedup because historical measurement generations are not guaranteed to be perfectly matched.

## Shared arena physical-memory ablation

Two IQ3_S lanes were run at 32768 context and 8192 resident KV so the private control remained feasible. PSS comes from `/proc/<pid>/smaps_rollup` after both engines were fully ready.

| Arena mode | Two-engine PSS | Difference vs private |
| --- | ---: | ---: |
| Private per-engine arena | **95.298 GiB** | — |
| Shared arena | **52.083 GiB** | **-43.215 GiB / -45.35%** |

The shared mapping itself was 49,116,200 KiB per engine and appeared as `rw-s` on the same `/dev/shm` backing. Each process attributed roughly half of that mapping as PSS (24,558,100 KiB), with `Shared_Dirty=49,116,200 KiB` and `Private_Dirty=0` for the arena mapping. This is direct physical-sharing evidence, not an RSS inference.

The result closely reproduces the historical 95.33 -> 52.03 GiB / 45.4% observation.

## Heterogeneous lane isolation

Fast lane: RTX 5070 Ti x8 (GPU0). Slow lane: RTX 5060 Ti x4 (GPU3). Both use the same shared arena, 262144 context, 32768 resident KV, and the fixed 512-token workload. Solo and concurrent trials were interleaved rather than run in two large time blocks.

| Measurement | n | Mean TG | SD | Approx. 95% CI |
| --- | ---: | ---: | ---: | ---: |
| 5070 Ti x8 solo | 8 | **73.01** | 1.41 | 71.84–74.19 |
| 5070 Ti x8 concurrent | 8 | **72.36** | 2.26 | 70.47–74.25 |
| 5060 Ti x4 concurrent | 8 | **59.14** | 1.24 | 58.10–60.18 |

The nominal fast-lane difference is 0.65 tok/s, or **0.89%**. That difference is smaller than ordinary run-to-run dispersion and the confidence intervals overlap substantially. The paper-safe wording is therefore:

> **No measurable fast-lane degradation within run-to-run variance.**

Do not promote 0.89% as a universal slowdown constant.

## Mixed real-serving support experiment

Three workloads — fiction, coding, and reasoning — were assigned to the three 5070 Ti lanes and rotated across GPU0/GPU2/GPU1 so workload effects were not permanently tied to x8/x8/x4 topology.

Nine retained common-wall runs produced:

- mean aggregate TG: **187.15 tok/s**;
- SD: **5.63 tok/s**;
- range: **176.85–196.18 tok/s**.

This is useful supporting evidence that heterogeneous request content can coexist in the independent-lane architecture. It is not the headline scaling result because workload content differs across lanes.

## Anomalies and data hygiene

- The original heterogeneous JSONL had one malformed trailing fragment after the valid summary record. All 8 solo and 8 concurrent retained repetitions are valid JSON and were preserved; only the unparsable trailing fragment was excluded from the publication CSV.
- The 3-lane scaling distribution has visibly larger variance than the 1- and 2-lane distributions. No slow retained repetition was discarded.
- Exact GPU clock/undervolt state was **not separately snapshotted at benchmark start** in the recovered 0.1.27 evidence bundle. The repository has a separately documented reference tuning profile, but this run does not claim that metadata as independently verified provenance.
- Laya, Qwen-TTS, and normal production-Strata restoration are intentionally outside this experiment's completion scope.

## Paper-safe claims

Fresh 0.1.27 evidence directly supports these statements for the reference host and IQ3_S configuration:

1. Independent request-per-GPU lanes scale from one to three active GPUs, reaching 2.684× speedup and 89.5% parallel efficiency at three lanes under the controlled warm workload.
2. A shared host expert backing reduces two-engine physical-memory PSS by about 43.2 GiB (45.35%) versus private expert arenas.
3. Running a slower RTX 5060 Ti x4 lane concurrently does not produce a measurable throughput degradation on the RTX 5070 Ti x8 lane beyond run-to-run variance.
4. Mixed request classes can be served concurrently without mandatory token-step synchronization; the rotated three-lane support experiment remained in the same broad aggregate-throughput regime as the homogeneous three-lane test.

## Claims not yet justified

- A universal scaling efficiency across machines, GPU generations, PCIe layouts, models, or quants.
- A universal numerical heterogeneous-lane slowdown such as 0.89%.
- A workload-specific causal link between expert hit rate and TG; the workload study is observational and speculative acceptance also differs materially.
- A workload-specific benefit from adaptive replacement in this measurement generation; retained workload repetitions show zero adaptive swap publications.
- A strict 0.1.22/0.1.24/0.1.27 software A/B unless prompt generation, engine state, and all tuning variables are matched exactly.

## Artifacts

- [`../bench/systems-ablation-0.1.27-20260930.csv`](../bench/systems-ablation-0.1.27-20260930.csv) — all retained scaling, RAM, heterogeneous, and mixed-workload observations.
- [`../bench/strata-0.1.27-promotion-20260930.csv`](../bench/strata-0.1.27-promotion-20260930.csv) — validation/provenance matrix.
- [`workload-sensitivity-0.1.27-20260930.md`](workload-sensitivity-0.1.27-20260930.md) — workload-specific PP/TG/cache/spec analysis.
