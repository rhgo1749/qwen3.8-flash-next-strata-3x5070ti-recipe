# Results

This repository keeps the current software baseline while preserving measured evidence under the engine generation that produced it.

## Current software baseline — Strata 0.1.38

```text
repository          rhgo1749/Strata-Lanes
operational main    3ccb7f9c6316ab51a696d621feb0502d083509fa
upstream 0.1.38     99f3dbd0b21d1401b3769e0c0d963913607f380b
engine              Strata 0.1.38
production binary   a1793a6e3f65dc271f8fa1af6148b374aac7398e431b3f94e40010846049a3bd
```

The bounded 0.1.38 upstream-sync compatibility gate passed:

- full Python serving suite: **256 tests run / 7 skipped / no failures**
- CUDA **13.4.92**, sm_120 Release configure/build: **PASS**
- focused shared-arena/profile/source CTests: **3/3 PASS**
- live model-backed 3-lane shared-arena startup and simultaneous request routing: **PASS**

A matched single-lane compatibility A/B against the installed 0.1.31 production binary found a clear long-prompt prefill movement:

| Fresh prompt | 0.1.31 | 0.1.38 | Delta |
| ---: | ---: | ---: | ---: |
| ~15K | 2498.4 tok/s | **2735.0 tok/s** | **+9.5%** |
| ~30K | 2594.7 tok/s | **2784.0 tok/s** | **+7.3%** |

This is a bounded one-sample-per-size directional A/B, not a replacement for the full model-backed benchmark campaign. Decode samples were too short and acceptance-sensitive for a version-level decode claim.

The current full architecture campaign has now been rerun on 0.1.38. The 0.1.31 Phase 3 lifecycle campaign and the 0.1.30 architecture matrix remain retained historical evidence; their measurements are not relabeled as 0.1.38.

Current sync record: [`docs/strata-0.1.38-promotion-20261003.md`](docs/strata-0.1.38-promotion-20261003.md). Current full campaign: [`docs/strata-0.1.38-full-campaign-20261003.md`](docs/strata-0.1.38-full-campaign-20261003.md). Current lane-local parking production/Hermes record: [`docs/lane-local-conversation-parking-20261003.md`](docs/lane-local-conversation-parking-20261003.md).

### Lane-local conversation parking — production path + Hermes eval

Current reference-host production uses three RTX 5070 Ti lanes only and enables upstream-native conversation parking at **4096 MiB / 4 slots / 8192 MiB MemAvailable floor per lane**. The RTX 5060 Ti is excluded from the serving pool.

In an exact matched production-path A/B through the real `8087 → 18087` route with the same patched engine in both arms, six stable mixed sessions measured:

| Turn | Wall OFF | Wall ON | Wall delta | Mean E2E delta | Aggregate completion TPS delta |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 cold/wake | 36.185 s | 36.223 s | +0.1% | +0.1% | -0.1% |
| 2 returning | 9.686 s | **6.232 s** | **-35.7%** | **-28.5%** | **+55.4%** |
| 3 returning | 9.688 s | **6.571 s** | **-32.2%** | **-25.7%** | **+59.1%** |

A later Hermes `eval` validation used real Hermes session persistence with the Strata provider override. Returning requests carried roughly **25K-token prompts**; normal hits reused about **25.1K–25.6K tokens** while reading only ~232–264 fresh tokens. Under the 4 GiB/lane byte budget, lane1 produced one real eviction; the affected revisit still completed with partial reuse (`16384` reused, ~9.5K freshly read) and preserved conversation continuity. Final observed parked state was ~1.73 GiB / 2.86 GiB / 1.10 GiB on lanes 0/1/2 with eviction counts 0/1/0.

## Current full benchmark generation — Strata 0.1.38

The current full campaign uses a fixed prompt contract within 0.1.38. Historical 0.1.30 prompt bytes were not retained, so cross-version workload deltas are descriptive unless separately byte-matched.

### Independent-lane scaling

| Active lanes | Common-wall aggregate TG | Speedup | Efficiency |
| ---: | ---: | ---: | ---: |
| 1 | **67.45 ± 2.20 tok/s** | 1.000× | 100.0% |
| 2 | **129.41 ± 2.95 tok/s** | **1.919×** | **95.9%** |
| 3 | **173.26 ± 6.67 tok/s** | **2.569×** | **85.6%** |

Corrected mixed fiction/coding/reasoning serving measured **178.86 ± 3.33 tok/s** over nine retained warm rotations.

### Shared arena memory

The historical 32K / resident-KV 8192 contract was rerun exactly for memory accounting:

| Arena mode | Two-engine PSS |
| --- | ---: |
| Private | **95.670 GiB** |
| Shared | **52.111 GiB** |
| Saved | **43.559 GiB / 45.53%** |

At the production 262K / resident-KV 32768 contract, PSS changed from **95.927 → 58.036 GiB**, saving **37.892 GiB / 39.50%**. The shared expert mapping remains 49,116,204 KiB `Shared_Dirty` with `Private_Dirty=0`.

### Heterogeneous isolation

After discarding an initial CPU-affinity-contaminated attempt, the retained disjoint-CPU ABBA run measured **68.90 tok/s** on the RTX 5070 Ti solo and **68.75 tok/s** while the RTX 5060 Ti ran concurrently. Raw fast-lane delta is **-0.22%**. An acceptance-adjusted model estimates **-0.74%**, with the arm coefficient interval crossing zero, so this run does not establish material fast-lane pacing.

### Independent lanes vs layer split

Within the 0.1.38 fixed campaign prompt, one warm request measured **67.45 tok/s** on one independent lane versus **101.90 ± 1.39 tok/s** on three-GPU layer split. Three simultaneous requests measured **173.26 tok/s** on three independent lanes versus **102.84 ± 0.70 tok/s** on the ordinary layer-split server's serial FIFO path.

Three-GPU layer-split cold PP measured **1033.1 ± 14.8 tok/s**. The old 0.1.30 contract measured 807.1 ± 11.8 tok/s, but those prompt bytes differ; the separately byte-matched 0.1.31→0.1.38 A/B remains the stronger version-level prefill evidence.

### Oversubscription

| Requests | Aggregate TG | Queue p50 | Queue p95 | E2E p95 |
| ---: | ---: | ---: | ---: | ---: |
| 3 | **173.55 ± 3.34** | 2.9 ms | 8.8 ms | 9.08 s |
| 4 | **130.88 ± 1.12** | 4.9 ms | 8.20 s | 15.71 s |
| 6 | **183.98 ± 2.97** | 4.01 s | 8.64 s | 16.65 s |
| 9 | **183.38 ± 3.90** | 8.23 s | 16.83 s | 25.26 s |

Full current record: [`docs/strata-0.1.38-full-campaign-20261003.md`](docs/strata-0.1.38-full-campaign-20261003.md). Machine-readable evidence: [`bench/raw/0.1.38-20261003/`](bench/raw/0.1.38-20261003/).

### Retained previous software gate — Strata 0.1.34

The previous 0.1.34 compatibility record remains at [`docs/strata-0.1.34-promotion-20261002.md`](docs/strata-0.1.34-promotion-20261002.md).
## Retained full live baseline — Strata 0.1.31

```text
repository          rhgo1749/Strata-Lanes
operational main    475e0766e8b41e17c978a6765ee0587f198790a3
measured runtime    4e333d8cd4731c8c365aeea984371f7853f27092
upstream 0.1.31     9259cad4cfa3543cd3b8decab5962672b968c649
engine              Strata 0.1.31
binary sha256       28b247fd94c49420a6c698630a7883fc8d7723543996b39987cfe54edd1db8ff
```

The 0.1.31 sync passed the current compatibility/parity gate:

- Python serving suite: **156 passed / 7 skipped**
- CUDA 13.4 sm_120 Release build: **PASS**
- CTests: **47 passed / 2 skipped / 3 external-fixture unavailable**
- live text, vision, malformed-input, session-affinity, disconnect and recovery smoke: **PASS**
- upstream-native shared expert arena: **PASS**
- promoted scheduler on one persistent supervisor: **2/2/2 placement in all three waves**, affinity preserved

Persistent-wave continuation throughput:

| Wave | Placement | Common-wall TG |
| ---: | ---: | ---: |
| 1 | 2 / 2 / 2 | **88.49 tok/s** |
| 2 | 2 / 2 / 2 | **87.17 tok/s** |
| 3 | 2 / 2 / 2 | **65.92 tok/s** |

The shared arena remained one physical mapping across all three lane engines: 49,116,200 KiB payload per mapping, `Shared_Dirty=49,116,200 KiB`, `Private_Dirty=0`.

Phase 3 then removed duplicate shared-arena source loading on the same 0.1.31 engine generation. Matched direct 3-lane ready time changed from **42.218 s → 27.133 s** (**-35.73%**), while the full production idle-proxy wake changed from the previously recorded **42.042 s → 34.031 s** (**-19.05%**). Lane 0 remains the population leader; lane 1/2 attach only after pack/size/readiness validation and skip their duplicate source loads. Production correctness smoke remained PASS.

Current lifecycle record: [`docs/phase3-shared-arena-lifecycle-20261002.md`](docs/phase3-shared-arena-lifecycle-20261002.md). Initial 0.1.31 parity record: [`docs/strata-0.1.31-promotion-20261001.md`](docs/strata-0.1.31-promotion-20261001.md).

## Retained benchmark generation — Strata 0.1.30

The complete architecture-performance matrix was measured on Strata 0.1.30 and remains versioned as such. It is not relabeled as 0.1.31.

### 1 → 2 → 3 independent-lane scaling

| Active lanes | Common-wall aggregate TG | Speedup | Parallel efficiency |
| ---: | ---: | ---: | ---: |
| 1 | **70.804 ± 1.546 tok/s** | 1.000× | 100.0% |
| 2 | **132.760 ± 3.129 tok/s** | **1.875×** | **93.8%** |
| 3 | **189.486 ± 3.205 tok/s** | **2.676×** | **89.2%** |

### Shared expert arena memory

| Arena mode | Two-engine PSS |
| --- | ---: |
| Private | **98.924864 GiB** |
| Shared | **52.083863 GiB** |
| Saved | **46.841001 GiB / 47.35%** |

### Heterogeneous isolation

RTX 5070 Ti x8 vs RTX 5070 Ti x8 + RTX 5060 Ti x4:

| Measurement | Mean TG |
| --- | ---: |
| RTX 5070 Ti solo | **71.563 ± 1.760 tok/s** |
| RTX 5070 Ti concurrent | **71.163 ± 1.456 tok/s** |
| RTX 5060 Ti concurrent | **57.575 ± 1.527 tok/s** |
| Common-wall concurrent aggregate | **113.898 ± 2.985 tok/s** |

The fast-lane difference is smaller than ordinary run-to-run dispersion in this measured pair.

### Mixed three-lane serving

Rotating fiction/coding/reasoning across the three RTX 5070 Ti lanes produced **184.669 ± 5.966 tok/s** common-wall aggregate across nine retained runs.

### Independent lanes vs layer split

Matched 0.1.30 comparison:

- one warm request: one independent lane **70.804 ± 1.546 tok/s** vs three-GPU layer split **102.976 ± 1.527 tok/s**
- three simultaneous requests: three independent lanes **189.486 ± 3.205 tok/s** vs the ordinary layer-split server's serial FIFO path **102.588 ± 1.629 tok/s**

These are workload-region measurements, not a universal winner claim.

Full 0.1.30 record: [`docs/strata-0.1.30-promotion-20261001.md`](docs/strata-0.1.30-promotion-20261001.md).

## Serving-control state

Phase 1, Phase 2, and the current Phase 3 shared-arena lifecycle gate are complete on the independent-lane architecture.

- production new-session placement: `balanced-additive-new-prefill-retained-state-proxy-v1`
- rollback policy: `safe-affinity-live-state-v1`
- extra CPU/PCIe shared-pressure placement coefficients: not promoted
- bounded admission for the all-complete-immediately workload: not promoted
- workload-regime adaptation: not promoted

There is no mandatory next serving phase. Architecture challengers remain evidence-triggered and stay deferred until a measured bottleneck activates them.

## Reference host

- CPU: AMD Ryzen 9 9950X3D, 16C/32T
- RAM: 128 GB DDR5
- GPU lanes: RTX 5070 Ti 16 GB ×3
- PCIe: x8 / x4 / x8
- context: 262144 per lane
- resident KV: 32768 per lane
- driver: NVIDIA 615.71.09
- CUDA: 13.4
- quant: Qwen3.8-Flash-Next GSQ-RCO IQ3_S

Older generations are intentionally not mirrored on the moving `main` branch. They remain recoverable from Git history and named snapshots.
