# Fork relationship and implementation

This document separates the upstream engine, the implementation fork, the frozen paper-v1 evidence, and the moving development branches.

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
  public recipe / evidence repository
  - reference hardware
  - host-specific CPU/PCIe/KV tuning
  - canonical benchmark records
  - promotion records
  - capacity / serving validation
  - launch examples
```

The recipe is deliberately separate from the implementation fork. The fork can continue syncing upstream and carrying new execution strategies while a paper revision points to exact immutable commits.

## Paper v1 implementation and evidence pins

Paper v1 is **not** defined by the future state of either repository's `main` branch.

```text
recipe snapshot  f54597a071e56bb0412685c46c4d604d50e26e45
recipe branch    paper-v1  (convenience name for the frozen snapshot)
Strata fork      6cf101d5b98523cbaefc34a199faa5657c5c2719
upstream Strata  a79080535d1b2a71a3419a0d97d8e7dca194b0f1
engine           Strata 0.1.27
binary           build-production-027/strata
```

The submitted manuscript itself names `6cf101d` as the paper-validation fork commit and `a790805` as the upstream 0.1.27 baseline. For v1 reproduction, use the exact revisions above rather than resolving `main` at reproduction time.

See [`paper-v1-reproducibility.md`](paper-v1-reproducibility.md) for fixed permalinks to the v1 evidence files.

## Development after paper v1

The repositories remain usable after submission:

- `rhgo1749/Strata:main` may advance with later runtime work;
- the recipe `main` may advance with later experiments and documentation;
- experimental branches are not retroactively part of paper v1;
- a later manuscript revision should receive a new explicit snapshot and commit pins.

The frozen `paper-v1` snapshot should not be moved or rewritten.

## Production architecture principle

The multi-lane path does **not** turn every request into tensor/pipeline parallel inference. The normal execution unit remains one Strata engine lane per GPU.

The serving layer:

1. shares the large host expert arena between lane processes;
2. starts one ordinary Strata engine per GPU;
3. keeps context/KV/hot-cache/session state lane-local;
4. partitions CPU cores so expert workers do not collide;
5. leases whole generation requests to free lanes.

That means the normal parallelism unit is a **request/session**, not a token, tensor, layer, or expert.

## Shared expert arena

Implementation files in the paper-v1 Strata revision include the pinned-memory/shared-arena path under `src/core/`.

The fork adds an opt-in Linux file-backed path for the expert arena while retaining upstream pinned-memory behavior for unrelated allocations. Independent lane processes map the same physical host pages while keeping their own CUDA registration, streams, GPU hot-expert cache, resident KV, and session state.

The shared path is exact-size guarded so unrelated pinned allocations stay on the normal path. In the v1 IQ3_S measurements, the shared expert mapping is about **46.84 GiB**.

## Multi-GPU supervisor

Implementation file:

```text
serve/multigpu_server.py
```

The supervisor reads a working Strata config and creates one derived lane config per GPU. It can set per-lane context, PCIe/cache tuning, resident KV, CPU budget, log path, and private listen port.

In the v1 design, a generation request leases one free lane and the lane returns to the pool when the request completes. The v1 paper therefore evaluates request-level independent serving rather than intra-lane continuous batching.

## Coexistence with upstream layer-split

The fork preserves upstream Strata's native multi-GPU layer-split path rather than replacing it.

The two modes solve different problems:

- **request-per-lane:** several independent requests run concurrently, one request per GPU lane;
- **layer-split:** one request uses multiple GPUs as one model pipeline.

Historical 0.1.22 measurements on the same host lineage reported:

```text
request-per-lane warm 3-request wall aggregate  226.5–227.9 tok/s
request-per-lane 15,064-token no-reuse PP       2,492.2 tok/s
layer-split 15,064-token no-reuse PP            1,142.3 tok/s
layer-split short single-request decode            80.6 tok/s
```

Those values are historical context only. They are not a strict baseline for the paper-v1 0.1.27 IQ3_S campaign because engine generation, quant/profile, prompt contract, concurrency, and completion length differ. A controlled same-generation layer-split comparison remains separate from the v1 headline evidence.

## Reference-host tuning belongs in the recipe

The paper-v1 reference host uses:

```text
GPU topology         Gen5 x8 / x4 / x8 for the three RTX 5070 Ti lanes
CPU split            5 / 6 / 5 physical cores
lane contexts        262144 / 262144 / 262144
resident KV          32768 / 32768 / 32768
host-KV guard        786432 tokens total
shared expert arena  ~46.84 GiB for IQ3_S
```

These values are **reference-host values, not universal defaults**. Another host should begin from its own topology and validate each lane independently and concurrently.

The final paper-v1 benchmark bundle does not contain a dedicated benchmark-start clock/undervolt snapshot, so the v1 evidence does not attribute its results to a particular voltage/frequency profile.

## Why not cross-GPU decode by default?

The architecture deliberately avoids mandatory GPU-to-GPU expert or KV traffic in the normal independent-lane decode critical path. That provides several practical properties:

- a slower lane does not become a mandatory token-step pace setter for every other lane;
- lane failures remain comparatively isolated;
- mixed-performance GPUs are usable as independent request slots;
- no NVLink is required for normal request-per-lane decode;
- existing Strata execution is reused.

The trade-off is clear: one request normally uses only one GPU lane. When only one request is active, other lanes may be idle. Upstream layer-split remains available when that trade-off is undesirable.

## Roadmap relationship

The implementation fork keeps a moving development roadmap on its current branch:

[`rhgo1749/Strata/docs/multigpu-roadmap.md`](https://github.com/rhgo1749/Strata/blob/main/docs/multigpu-roadmap.md)

That roadmap link intentionally follows ongoing development and is **not** a paper-v1 reproducibility link. Paper-v1 reproduction should use the exact commits in this document instead.
