# Fork relationship and implementation

This document separates the upstream engine, the implementation fork, and the host-specific recipe.

## Repository roles

```text
Niko1221/Strata
  upstream engine
  - single-engine serving
  - native layer split
  - expert/runtime/kernel work
  - upstream-native shared expert arena
          |
          v
rhgo1749/Strata-Lanes
  serving implementation fork
  - upstream engine syncs
  - independent GPU-per-lane supervisor
  - session affinity
  - capability-aware routing
  - balanced-additive new-session placement
  - observability and serving-control tests
          |
          v
rhgo1749/qwen3.8-flash-next-strata-gpu-per-lane-recipe
  reference-host recipe and evidence
  - launch examples
  - hardware-specific CPU/PCIe/KV tuning
  - retained benchmark records
  - promotion/parity records
```

The moving recipe `main` tracks the current operational baseline and the immediately preceding benchmark generation rather than carrying every historical experiment forward.

## Current operational state

```text
Strata-Lanes main      d7afade41f06d4486a4feb2dd59b2864122e0e2e
upstream Strata        9259cad4cfa3543cd3b8decab5962672b968c649
engine baseline        Strata 0.1.31
production scheduler   balanced-additive-new-prefill-retained-state-proxy-v1
rollback scheduler     safe-affinity-live-state-v1
```

The production execution unit remains one independent Strata engine lane per GPU. CUDA state, GPU hot-expert cache, resident KV, host-KV/session state and the generation loop stay lane-local.

## Shared expert arena

The host expert backing is one upstream-native shared arena used by multiple lane processes. The primitive originated in this fork's upstream PR #129 and was incorporated into Strata 0.1.30; current 0.1.31 keeps that path and its Linux whole-arena pinning behavior.

Each lane keeps its own CUDA registration and GPU-side cache while mapping the same physical host expert pages. Phase 3 makes population single-writer per supervisor generation: lane 0 fills the arena and publishes readiness, later lanes verify and attach as followers without repeating the source expert load.

## Multi-GPU supervisor

Implementation file:

```text
serve/multigpu_server.py
```

The supervisor:

1. starts one ordinary Strata engine per GPU;
2. shares one host expert arena across those lane processes;
3. partitions CPU worker pools;
4. enforces one active generation per lane;
5. keeps known sessions on their remembered lane;
6. uses capability filtering and compatible FIFO queueing;
7. uses balanced-additive placement for new sessions;
8. excludes lanes whose child engine is no longer healthy;
9. owns the shared-arena pathname for the supervisor lifetime so another supervisor cannot repopulate it concurrently.

The normal parallelism unit is therefore a **request/session**, not a token, tensor, layer, or expert.

## Coexistence with upstream multi-GPU execution

The fork preserves upstream Strata's native multi-GPU paths.

- **independent lanes:** several requests run concurrently on separate engine lanes;
- **layer split:** one request uses multiple GPUs as one model pipeline;
- other upstream execution primitives can be evaluated as lane-internal challengers without changing the serving layer by default.

These execution modes target different workload regions and should be compared under matched measurements rather than treated as interchangeable.

## Reference-host tuning

The reference host uses three RTX 5070 Ti lanes with asymmetric PCIe topology, explicit CPU partitions, 262144 context per lane, 32768 resident KV per lane, and explicit per-lane VRAM reserve.

These are measured host values, not portable defaults.

## Roadmap authority

The canonical moving roadmap is the GitHub Issue tree in `rhgo1749/Strata-Lanes`. Phase 1, Phase 2, and the current Phase 3 shared-arena lifecycle gate are complete on the 0.1.31 baseline. Later architecture challengers remain conditional on measured triggers.
