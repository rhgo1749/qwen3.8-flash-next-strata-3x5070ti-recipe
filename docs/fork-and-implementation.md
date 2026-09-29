# Fork relationship and implementation

This document separates the upstream engine, the implementation fork, and the public hardware recipe.

## Repository roles

```text
Niko1221/Strata
  upstream engine / normal single-GPU path / native layer-split
          |
          v
rhgo1749/Strata
  implementation fork
  - upstream engine syncs
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
  - canonical benchmark records
  - promotion records
  - capacity / serving validation
  - launch examples
```

The recipe is deliberately separate from the implementation fork. The fork can sync upstream and carry multiple execution strategies while the recipe keeps a stable public record of measured host-specific behavior.

## Current promoted implementation

```text
repository  rhgo1749/Strata
commit      9dda206874387b20cac20837a1452f115a8f9f93
engine      Strata 0.1.22
promoted    2026-09-29
```

The 0.1.22 sync preserved both execution paths:

1. the fork's independent request-per-GPU lane supervisor and shared host expert arena;
2. upstream Strata's native multi-GPU layer-split challenger.

The recipe's existing multi-lane command surface remained compatible across the promotion.

## Production architecture principle

The multi-lane production path does **not** turn every request into tensor/pipeline parallel inference. The normal execution unit remains one Strata engine lane per GPU.

The fork's production serving layer:

1. shares the large host expert arena between lane processes;
2. starts one ordinary Strata engine per GPU;
3. keeps context/KV/hot-cache/session state lane-local;
4. partitions CPU cores so expert workers do not collide;
5. leases whole generation requests to free lanes.

That means the production parallelism unit is a **request/session**, not a token, tensor, layer, or expert.

## Shared expert arena

Implementation files:

```text
src/core/pinned.cu
src/core/pinned_upstream_impl.cu
```

The fork adds an opt-in Linux file-backed path for the expert arena while retaining upstream pinned-memory behavior for unrelated allocations. Independent lane processes map the same physical host pages while keeping their own CUDA registration, streams, GPU hot-expert cache, resident KV, and session state.

The shared path is exact-size guarded so unrelated pinned allocations stay on the normal path.

## Multi-GPU supervisor

Implementation file:

```text
serve/multigpu_server.py
```

The supervisor reads a working Strata config and creates one derived lane config per GPU. It can set per-lane context, PCIe/cache tuning, resident KV, CPU budget, log path, and private listen port.

Lane startup is currently sequential because ordinary engine initialization still populates the shared expert arena. A future leader/follower initialization path may remove that repeated source load.

## Coexistence with upstream layer-split

Upstream Strata 0.1.22 can also run one model split across several GPUs. The fork preserves that path rather than replacing it.

The two modes solve different problems:

- **request-per-lane:** several independent requests run concurrently, one request per GPU lane;
- **layer-split:** one request uses multiple GPUs as one model pipeline.

On the 0.1.22 reference-host promotion run:

```text
request-per-lane warm 3-request wall aggregate  226.5–227.9 tok/s
request-per-lane 15,064-token no-reuse PP       2,492.2 tok/s
layer-split 15,064-token no-reuse PP            1,142.3 tok/s
layer-split short single-request decode            80.6 tok/s
```

This evidence keeps request-per-lane as the production baseline for the target concurrent-agent workload while preserving layer-split as a challenger for single-request-oriented workloads.

See [`strata-0.1.22-promotion-20260929.md`](strata-0.1.22-promotion-20260929.md) for the full promotion record and caveats.

## Reference-host tuning belongs in the recipe

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

Current performance source of truth is [`../RESULTS.md`](../RESULTS.md). GPU tuning history remains in [`undervolt-v2-20260929.md`](undervolt-v2-20260929.md), while full-window capacity/serving validation remains in [`reference-host-validation-20260929.md`](reference-host-validation-20260929.md).

## Why not cross-GPU decode by default?

The current production design deliberately avoids mandatory GPU-to-GPU expert or KV traffic in the normal decode critical path. That provides several practical properties:

- a slower lane does not force every other lane to wait;
- lane failures remain comparatively isolated;
- mixed-performance GPUs are usable as independent request slots;
- no NVLink is required;
- existing Strata execution is reused.

The trade-off is clear: one request normally uses only one GPU lane. When only one request is active, other lanes may be idle. Upstream layer-split remains available when that trade-off is undesirable.

## Roadmap relationship

The implementation fork keeps the generic development roadmap:

[`rhgo1749/Strata/docs/multigpu-roadmap.md`](https://github.com/rhgo1749/Strata/blob/main/docs/multigpu-roadmap.md)

The roadmap's promotion rule is evidence-first: a more coupled architecture should replace the independent-lane baseline only after repeatable end-to-end measurements show a material benefit without giving up required context capacity, correctness, stability, or a clean fallback path.
