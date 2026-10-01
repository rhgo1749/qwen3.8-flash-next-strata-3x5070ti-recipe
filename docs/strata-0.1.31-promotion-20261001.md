# Strata 0.1.31 parity promotion — 2026-10-01

## Promotion scope

Strata 0.1.31 is promoted as the **current operational engine baseline** for the GPU-per-lane recipe after a matched compatibility/parity campaign.

This is intentionally narrower than the full Strata 0.1.30 measurement generation. The 0.1.30 campaign remains the retained source for the complete architecture matrix (1→2→3 scaling, private-vs-shared PSS, heterogeneous isolation, workload sensitivity, overload, and matched layer-split A/B). The 0.1.31 campaign verifies that the upstream sync does not regress the production lane architecture or promoted scheduler before roadmap work continues.

## Provenance

- measured fork runtime merge: `0e29989c8a1ba016950ec3722531edcae42bdae5`
- promoted fork main after documentation: `15be91859ffdc49010bf37ed60cb2dfaf4d6e7d5`
- upstream Strata 0.1.31 main: `9259cad4cfa3543cd3b8decab5962672b968c649`
- measured binary SHA-256: `afe4970c509860fe000131d20726972962b98179a04949212126c2742040dc4d`
- CUDA: 13.4, sm_120 Release build
- NVIDIA driver: 615.71.09
- model: Qwen3.8-Flash-Next GSQ-RCO IQ3_S
- host: Ryzen 9 9950X3D, 128 GB DDR5, RTX 5070 Ti ×3 + RTX 5060 Ti ×1

The 0.1.31 merge was clean at the textual level. The independent-lane supervisor remained fork-owned and was not modified by upstream; semantic overlap was concentrated in common engine files such as expert sources and generation setup.

## Implementation gate

- Python serving suite: **156 passed / 7 skipped**
- CUDA 13.4 sm_120 Release build: **PASS**
- registered CTests: **47 passed / 2 skipped / 3 unavailable fixture-dependent**
- unavailable external-fixture tests: `ple_parity`, `expert_parity`, `pool_test`

The first parallel CTest attempt was invalid because the production GPUs were still occupied and GPU tests exhausted free VRAM. After stopping the production engines and rerunning serially, every fixture-independent registered test passed.

## Live production-shape correctness

The candidate was launched with the production topology:

- GPU lanes: 0 / 1 / 2
- context: 262144 per lane
- aggregate host-KV budget: 786432
- resident GPU KV: 32768 per lane
- CPU partitions: 5 / 6 / 5 physical cores
- PCIe fractions: 0.55 / 0.25 / 0.55
- vision lane: lane 1
- scheduler: `balanced-additive-new-prefill-retained-state-proxy-v1`
- one shared upstream-native expert arena

Three independent correctness-smoke runs passed text routing, vision routing, malformed-input handling, two-turn session affinity, prompt-cache reuse, client-disconnect cleanup, and immediate recovery. The second turn retained the same lane and reported 56 cached tokens in all three candidate runs.

### Disconnect cleanup A/B

The current smoke workload showed slower disconnect cleanup than an older historical run, so the same harness was repeated against the pre-sync 0.1.30 production control.

| Engine | cleanup polls at 250 ms |
| --- | --- |
| 0.1.31 candidate | 36 / 29 / 31 |
| 0.1.30 control | 36 / 34 / 33 |

The behavior reproduces on the control and therefore is **not attributed to the 0.1.31 sync**. Both versions released the lane and passed immediate recovery.

## Persistent scheduler parity

On one persistent 0.1.31 supervisor, three fresh six-session waves used the Phase-2B workload: 300 shared-prefix facts, 32-token first turn, and synchronized 128-token continuations.

| Wave | New-session placement | Affinity | Common-wall continuation TG |
| ---: | ---: | ---: | ---: |
| 1 | 2 / 2 / 2 | preserved | **88.49 tok/s** |
| 2 | 2 / 2 / 2 | preserved | **87.17 tok/s** |
| 3 | 2 / 2 / 2 | preserved | **65.92 tok/s** |

Mean across the three waves is **80.52 ± 12.67 tok/s**. The 0.1.30 retained balanced-additive campaigns span roughly 64.79–88.62 tok/s, so this parity run stays inside the previously observed operating band while preserving the promoted 2/2/2 placement behavior.

## Shared-arena structural parity

All three 0.1.31 engine processes mapped the same shared payload:

- shared file size: **50,294,992,896 bytes**
- mapped payload per engine: **49,116,200 KiB**
- per-mapping PSS: **16,372,065 KiB**
- `Shared_Dirty`: **49,116,200 KiB**
- `Private_Dirty`: **0 KiB**

This confirms that the production path still uses one physical shared expert arena rather than silently falling back to private per-process copies.

Upstream 0.1.31 also adds low-RAM GGUF/RAM/SSD expert tiers and routing-aware file-tier prefetch. Those are separate engine paths and are **not enabled by this shared-arena production configuration**. On Linux, whole-arena pinning remains the default unless explicitly overridden.

## Decision

**Promote Strata 0.1.31 for current operation and continue the roadmap from this baseline.**

Do not relabel the full 0.1.30 architecture campaign as 0.1.31. Historical measurements retain their original engine generation; the 0.1.31 record is a compatibility/parity promotion proving that the current independent-lane + shared-arena + balanced-additive serving contract survives the upstream update.

Raw retained evidence lives under `bench/raw/0.1.31-20261001/`.
