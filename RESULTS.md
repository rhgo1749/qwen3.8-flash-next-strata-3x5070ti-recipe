# Results

This repository keeps the current software baseline while preserving measured evidence under the engine generation that produced it.

## Current software baseline — Strata 0.1.34

```text
repository          rhgo1749/Strata-Lanes
operational main    4b5b47d6e50250b71c52fe4fe7d33593684dce91
integration merge   a96b2cd7d9c4a505c4bdb5cb9c2a87ade5f32684
upstream 0.1.34     1678de333d0e0711bc414ad992b640e1a37dd814
engine              Strata 0.1.34
binary sha256       8d34efb9161b64a68029feffa780d24e7f5b27dbcad3d96b3508231924d3fc87
```

The bounded 0.1.34 upstream-sync compatibility gate passed:

- Lanes-specific Python suite: **58 passed**
- full Python serving suite: **204 passed / 7 skipped**
- CUDA **13.4.92**, sm_120 Release configure/build: **PASS (237/237 build steps)**
- registered CTests: **48 passed / 2 skipped / 3 external-fixture unavailable**
- known unavailable external-fixture tests: `ple_parity`, `expert_parity`, `pool_test`
- no new fixture-independent test failure

This sync did **not** rerun the long model-backed three-lane benchmark campaign. The latest full live serving/lifecycle evidence remains the 0.1.31 Phase 3 campaign below, and the complete architecture-performance matrix remains 0.1.30. Those measurements are intentionally not relabeled as 0.1.34.

Current sync record: [`docs/strata-0.1.34-promotion-20261002.md`](docs/strata-0.1.34-promotion-20261002.md).

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
