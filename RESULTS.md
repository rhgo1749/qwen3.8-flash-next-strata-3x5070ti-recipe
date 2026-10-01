# Results

This repository keeps the current operational baseline and the immediately preceding benchmark generation for the GPU-per-lane Strata recipe.

## Current operational baseline — Strata 0.1.31

```text
repository          rhgo1749/Strata-Lanes
operational main    15be91859ffdc49010bf37ed60cb2dfaf4d6e7d5
measured runtime    0e29989c8a1ba016950ec3722531edcae42bdae5
upstream 0.1.31     9259cad4cfa3543cd3b8decab5962672b968c649
engine              Strata 0.1.31
binary sha256       afe4970c509860fe000131d20726972962b98179a04949212126c2742040dc4d
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

Full record: [`docs/strata-0.1.31-promotion-20261001.md`](docs/strata-0.1.31-promotion-20261001.md).

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

Phase 1 and Phase 2 are complete on the independent-lane architecture.

- production new-session placement: `balanced-additive-new-prefill-retained-state-proxy-v1`
- rollback policy: `safe-affinity-live-state-v1`
- extra CPU/PCIe shared-pressure placement coefficients: not promoted
- bounded admission for the all-complete-immediately workload: not promoted
- workload-regime adaptation: not promoted

The next roadmap focus is startup/runtime lifecycle overhead on the 0.1.31 baseline.

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
