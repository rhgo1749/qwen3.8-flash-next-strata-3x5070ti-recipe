# Fork relationship and implementation

This document separates the upstream engine, the implementation fork, and the public hardware recipe.

## Repository roles

```text
Niko1221/Strata
  upstream engine / normal single-GPU path
          |
          v
rhgo1749/Strata
  implementation fork
  - shared expert arena
  - multi-lane supervisor
  - request-level dispatcher
  - serving hardening and tests
  - generic architecture/roadmap docs
          |
          v
rhgo1749/qwen3.8-flash-next-strata-gpu-per-lane-recipe
  public recipe
  - reference hardware
  - host-specific CPU/PCIe/KV tuning
  - canonical GPU tuning and benchmark records
  - capacity / serving validation
  - launch examples
```

The recipe is deliberately separate from the implementation fork. The fork can rebase, sync upstream, or experiment with scheduling and distributed-cache ideas while the recipe keeps a stable public record of measured host-specific behavior.

Sanitized implementation pin for the current public recipe:

```text
rhgo1749/Strata
844d62064b4327f80eae0f2980ccbd83b04fbe9a
```

## Upstream principle preserved

The multi-GPU fork does **not** turn Strata into a tensor-parallel engine. The existing single-GPU numerical engine remains the execution unit.

The fork adds a coarse-grained serving layer around it:

1. share the large host expert arena between processes;
2. start one ordinary Strata engine per GPU;
3. keep context/KV/hot-cache/session state lane-local;
4. partition CPU cores so expert workers do not collide;
5. lease whole generation requests to free lanes.

That means the production parallelism unit is a **request/session**, not a token, tensor, layer, or expert.

## Shared expert arena

Implementation file:

```text
src/core/pinned.cu
```

The fork adds an opt-in Linux file-backed path for the expert arena. Independent lane processes map the same physical host pages while keeping their own CUDA registration, streams, GPU hot-expert cache, resident KV, and session state.

The shared path is exact-size guarded so unrelated pinned allocations stay on the normal Strata path.

## Multi-GPU supervisor

Implementation file:

```text
serve/multigpu_server.py
```

The supervisor reads a normal working Strata config and creates one derived lane config per GPU. It can set per-lane context, PCIe/cache tuning, resident KV, CPU budget, log path, and private listen port.

Lane startup is currently sequential because ordinary engine initialization still populates the shared expert arena. A future leader/follower initialization path may remove that repeated source load.

## Reference-host tuning belongs here

The measured reference host uses:

```text
GPU topology         Gen5 x8 / x4 / x8
CPU split            5 / 6 / 5 physical cores
pcie-frac            0.55 / 0.25 / 0.55
lane contexts        262144 / 262144 / 262144
resident KV          32768 / 32768 / 32768
host-KV guard        786432 tokens
shared expert arena  ~39.97 GiB
core V/F plateau     2300 MHz @ >=875 mV
VRAM offset          +2500
```

These values are **not** generic defaults. Another host should begin from its own topology and validate each lane independently and concurrently.

The current public performance source of truth is [`undervolt-v2-20260929.md`](undervolt-v2-20260929.md). Earlier pre-second-undervolt throughput figures are intentionally not promoted by the recipe.

Full-window capacity and serving validation is kept separately in [`reference-host-validation-20260929.md`](reference-host-validation-20260929.md).

## Why not cross-GPU decode by default?

The current design deliberately avoids mandatory GPU-to-GPU expert or KV traffic in the normal decode critical path. That provides several practical properties:

- a slower lane does not force every other lane to wait;
- lane failures remain comparatively isolated;
- mixed-performance GPUs are usable as independent request slots;
- no NVLink is required;
- existing single-GPU Strata execution is reused.

The trade-off is equally clear: one request normally uses only one GPU lane. When only one request is active, other lanes may be idle.

## What is not implemented in the production path

The current production path does not require:

- tensor parallelism;
- pipeline parallelism;
- cross-GPU expert parallelism;
- distributed non-overlapping expert ownership;
- GPU-to-GPU KV migration;
- a dynamic shared KV allocator;
- single-process multi-GPU decode.

These remain possible roadmap challengers rather than assumed upgrades.

## Roadmap relationship

The implementation fork keeps the generic development roadmap:

[`rhgo1749/Strata/docs/multigpu-roadmap.md`](https://github.com/rhgo1749/Strata/blob/main/docs/multigpu-roadmap.md)

The roadmap's promotion rule is evidence-first: a more coupled architecture should replace the independent-lane baseline only after repeatable end-to-end measurements show a material benefit without giving up required context capacity, correctness, stability, or a clean fallback path.
