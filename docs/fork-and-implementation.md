# Fork relationship and implementation

This document separates the upstream engine, the implementation fork, the frozen paper-v1 evidence, and the moving post-paper operational state.

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
  - independent GPU-per-lane supervisor
  - capability-aware routing
  - session-aware serving hardening
  - tests and runtime contracts
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

The recipe is deliberately separate from the implementation fork. The fork may continue to evolve while a paper revision points to exact immutable commits.

## Paper v1 implementation and evidence pins

Paper v1 is **not** defined by the future state of either repository's `main` branch.

```text
recipe snapshot  f54597a071e56bb0412685c46c4d604d50e26e45
recipe branch    paper-v1
Strata fork      6cf101d5b98523cbaefc34a199faa5657c5c2719
upstream Strata  a79080535d1b2a71a3419a0d97d8e7dca194b0f1
engine           Strata 0.1.27
```

For v1 reproduction, use those exact revisions rather than resolving `main` at reproduction time. See [`paper-v1-reproducibility.md`](paper-v1-reproducibility.md).

The frozen `paper-v1` snapshot must not move or be rewritten.

## Current post-paper operational state

The moving Strata `main` currently follows post-paper serving work. At the time of this document update:

```text
Strata operational main  614b2ae904bbe949144c694388b985fc6a0d20d8
engine baseline           Strata 0.1.27
paper-v1 Strata pin       6cf101d5b98523cbaefc34a199faa5657c5c2719
paper-v1 recipe snapshot  f54597a071e56bb0412685c46c4d604d50e26e45
```

`614b2ae` includes capability-aware vision routing, session-aware scheduler hardening, per-lane VRAM reserve controls, and child-engine-aware lane health. A live Python lane wrapper is no longer sufficient for scheduling: the supervisor verifies that the lane still exposes its model through `/v1/models`, so an OOM-killed child engine is excluded from routing. These changes are **post-paper operational work** and do not retroactively change paper-v1 measurements.

## Production architecture principle

The normal execution unit remains one independent Strata engine lane per GPU. The serving layer:

1. shares the large host expert arena between lane processes;
2. starts one ordinary Strata engine per GPU;
3. keeps context/KV/hot-cache/session state lane-local;
4. partitions CPU cores so expert workers do not collide;
5. leases whole generation requests to one lane at a time;
6. preserves session locality when useful instead of blindly rotating multi-turn requests across lane-local caches.

The normal parallelism unit is therefore a **request/session**, not a token, tensor, layer, or expert.

## Shared expert arena

The fork adds an opt-in Linux file-backed path for the expert arena while retaining upstream pinned-memory behavior for unrelated allocations. Independent lane processes map the same physical host pages while keeping their own CUDA registration, streams, GPU hot-expert cache, resident KV, and session state.

The shared path is exact-size guarded so unrelated pinned allocations stay on the normal path. In the paper-v1 IQ3_S measurements, the shared expert mapping is about **46.84 GiB**.

## Multi-GPU supervisor

Implementation file:

```text
serve/multigpu_server.py
```

The supervisor derives one lane config per GPU and can set per-lane context, PCIe/cache tuning, resident KV, CPU budget, log path, private port, and capabilities such as vision.

Paper-v1 evaluated independent request-level serving. Post-paper `main` adds a conservative session-aware scheduler because production logs showed that request-level rotation could move a long multi-turn conversation away from its lane-local prompt/KV state and trigger a full re-prefill.

The current operational policy is a **safe baseline, not the final scheduler design**. It keeps known sessions associated with a lane, reserves that lane for a waiting continuation, never inserts new work into a busy single-request lane, uses compatible FIFO ordering for queued new sessions, and applies hardware-agnostic live-state-aware placement among eligible idle lanes. The roadmap now tracks a more principled cache/load cost model separately.

## Coexistence with upstream layer-split

The fork preserves upstream Strata's native multi-GPU layer-split path.

- **request-per-lane:** several independent requests run concurrently, one active request per GPU lane;
- **layer-split:** one request uses multiple GPUs as one model pipeline.

They solve different problems. Historical performance values are retained in `RESULTS.md` and the frozen evidence files rather than treated as universal cross-version comparisons.

## Reference-host tuning belongs in the recipe

The paper-v1 reference host uses three RTX 5070 Ti lanes with asymmetric PCIe topology, explicit CPU partitions, 262144 context per lane, and 32768 resident KV per lane. These are **reference-host measurements, not universal defaults**.

## Why not cross-GPU decode by default?

The independent-lane path avoids mandatory GPU-to-GPU expert or KV traffic in the normal decode critical path. This keeps slower GPUs from becoming mandatory token-step pace setters, preserves lane-local failure domains, supports mixed-performance GPUs as independent request slots, and avoids requiring NVLink.

The trade-off is that one request normally uses only one GPU lane. Upstream layer-split remains available when that trade-off is undesirable.

## Roadmap authority

The **GitHub Issue tree in `rhgo1749/Strata` is the canonical moving roadmap**:

- [`#1 Roadmap: multi-GPU runtime evolution and promotion gates`](https://github.com/rhgo1749/Strata/issues/1)
- [`#2 Phase 1: benchmark and observability contract`](https://github.com/rhgo1749/Strata/issues/2)
- [`#3 Phase 2: session-, queue-, health-, and cache-aware scheduling`](https://github.com/rhgo1749/Strata/issues/3)

Other phase/challenger issues are linked from #1. Supporting prose docs may describe architecture or summarize decisions, but roadmap priority, research direction, and acceptance status should be updated in the Issue tree first.

This moving roadmap is **not** a paper-v1 reproducibility reference. Paper reproduction must use the exact frozen commits above.