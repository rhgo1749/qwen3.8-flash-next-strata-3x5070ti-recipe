# Qwen3.8-Flash-Next / Strata GPU-per-Lane Parallel Serving Recipe

**English** | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [日本語](README.ja.md)

A practical recipe for running **one independent Strata generation lane per GPU** while physically sharing one large host-RAM expert arena across lane processes.

## Current state

- Implementation fork: [`rhgo1749/Strata`](https://github.com/rhgo1749/Strata)
- **Current operational Strata pin:** [`614b2ae`](https://github.com/rhgo1749/Strata/commit/614b2ae904bbe949144c694388b985fc6a0d20d8)
- Engine baseline: Strata **0.1.27** (`a790805` upstream)
- Current production quant on the reference host: **Qwen3.8-Flash-Next GSQ-RCO IQ3_S**
- Frozen paper-v1 recipe snapshot: [`f54597a`](https://github.com/rhgo1749/qwen3.8-flash-next-strata-gpu-per-lane-recipe/commit/f54597a071e56bb0412685c46c4d604d50e26e45), branch `paper-v1`
- Frozen paper-v1 Strata implementation pin: [`6cf101d`](https://github.com/rhgo1749/Strata/commit/6cf101d5b98523cbaefc34a199faa5657c5c2719)

`main` is a moving post-paper operational branch. **Paper-v1 evidence is not rewritten when `main` advances.** For paper reproduction, use the frozen snapshot and implementation pin above.

Detailed retained measurements remain in [`RESULTS.md`](RESULTS.md). The post-v1 x4 vision-lane campaign is in [`recipe/vision-x4-lane.md`](recipe/vision-x4-lane.md).

## Core architecture

**One active request is processed by one GPU lane. Multiple requests run concurrently on different GPUs. The large expert weights in system RAM are physically shared rather than copied once per process.**

```mermaid
flowchart TB
    C[Clients / agents / OpenAI-compatible API] --> D[Session-aware dispatcher]
    D -->|session/request A| G0[GPU lane A]
    D -->|session/request B| G1[GPU lane B]
    D -->|session/request C| G2[GPU lane C]
    E[Shared host expert arena] --> G0
    E --> G1
    E --> G2
```

Lane-local state includes CUDA state, GPU hot-expert cache, GPU-resident KV, host-KV/session state, speculative/MTP state, and the generation loop. The normal production path has no mandatory token-by-token cross-GPU synchronization and does not require NVLink.

## Post-paper session-aware scheduler

The first multi-lane supervisor used request-level free-lane/round-robin scheduling. That is fine for independent throughput tests, but it can move a later turn of a long conversation to another GPU even though prompt/KV state is lane-local. On a real long session this caused a later turn to pay a full prompt re-prefill.

Current `main` therefore uses **session affinity plus live-state-aware placement**. The ordering is explicit:

1. Filter to healthy lanes that satisfy hard capabilities such as vision.
2. If the request belongs to a known session, use its remembered lane. If that lane is busy, **wait behind that lane instead of spilling to another GPU**.
3. A completely new session never enters an already-busy lane. If every eligible lane is busy, it waits until a request/stream fully releases a lane.
4. Among idle lanes, prefer a lane with no live conversation state.
5. If all idle candidates have live state, prefer the lane with the **smallest live request state** to minimize overwritten prompt-cache locality.
6. If that cost is tied, prefer the **least recently used live state**; rotating candidate order is the final fairness tie-breaker.

Queued new sessions use **compatible FIFO tickets**: an older compatible waiter gets a newly released lane first, while capability-constrained work such as vision does not block unrelated lanes. A remembered continuation waiting for its lane reserves that lane, so a `notify_all()` wake-up race cannot let a new session steal the cache-rich lane. An empty live state is defined by `live_request_bytes == 0`, not by the absence of an affinity key.

The policy is **hardware-agnostic**: it does not hard-code GPU number, GPU model, or PCIe width. `busy` is request/stream-scoped; affinity is session-scoped. Several session keys may remain mapped to the same engine so Strata can recover older per-engine prompt-cache checkpoints after intervening requests.

A production smoke after the fix exercised A → B → C → D → A: A/B/C filled separate lanes, D selected the lane with the smallest live state, and A still returned to its original lane. A separate overload smoke ran 3 active requests plus 4 queued requests, observed `peak_queue_depth=4`, and drained all 7 requests successfully back to `queue_depth=0` with all lanes idle.

This scheduler is **serving hardening for the current lane-local KV architecture, not claimed as the final optimal scheduler**. Cache-aware global scheduling, migration/transfer costs, overload queueing, and more explicit cost models remain roadmap work.

## Reference host

```text
CPU                 Ryzen 9 9950X3D, 16C/32T
RAM                 128 GB DDR5
GPU lanes           RTX 5070 Ti 16 GB ×3
PCIe                x8 / x4 / x8
contexts            262144 / 262144 / 262144
resident KV         32768 / 32768 / 32768
VRAM reserve MiB    1200 / 1200 / 1200
physical CPU cores  5 / 6 / 5
production vision   one selected lane
current quant       IQ3_S
```

These are **reference-host values, not universal defaults**.

### VRAM reserve caution for mixed vision/text lanes

When deriving text-only lanes from a vision-enabled base config, it is correct to remove `--vision` and the encoder configuration, but the VRAM safety margin must not disappear with them. On the reference RTX 5070 Ti 16 GB / IQ3_S / 262K-context / 32768 resident-KV setup, falling back to a 700 MiB reserve left only about **93 MiB** free after load and produced a real `verify: instantiate: out of memory` failure.

Production now sets `--lane-vram-reserve-mibs 1200,1200,1200`. A fresh remeasurement left **593 / 592 / 593 MiB** free on GPU0/GPU1/GPU2; three simultaneous public requests all returned HTTP 200, with no new OOM, illegal-memory, or engine-stop event after the new startup. The 1200 MiB value is a **reference-host safety value**, not a universal GPU default. The failure was exposed by mixed-capability lane derivation; it was not caused by the vision encoder consuming VRAM on the text-only GPUs.

A useful host-RAM rule is:

```text
required host RAM ≈ one shared expert arena + every lane's host-KV + OS/runtime headroom
```

## Evidence boundary

The submitted paper-v1 evidence remains pinned to recipe snapshot `f54597a` and Strata `6cf101d`. Its controlled results include 1→2→3 lane scaling, shared-vs-private arena PSS, heterogeneous isolation, workload sensitivity, and mixed-serving runs. Post-paper vision and scheduler changes on `main` are operational follow-up work and are **not retroactively inserted into paper-v1 results**.

See:

- [`RESULTS.md`](RESULTS.md) — retained benchmark evidence
- [`docs/fork-and-implementation.md`](docs/fork-and-implementation.md) — ownership and reproducibility boundary
- [`docs/paper-v1-reproducibility.md`](docs/paper-v1-reproducibility.md) — frozen v1 reproduction links
- [`recipe/vision-x4-lane.md`](recipe/vision-x4-lane.md) — post-v1 vision-lane experiment

## Adapting the recipe

1. Make one normal single-GPU Strata lane work on every GPU first.
2. Verify VRAM, negotiated PCIe links, RAM headroom, and CPU topology.
3. Partition physical CPU cores so lane worker pools do not overlap.
4. Start with conservative context/resident-KV values and validate every lane independently.
5. Validate multiple concurrent lanes, cold/no-reuse long prompts, streaming/cancellation, lane recovery, and **multi-turn session affinity**.
6. Treat hardware-specific tuning values as measurements, not portable defaults.

## Related projects

- Upstream Strata: [`Niko1221/Strata`](https://github.com/Niko1221/Strata)
- Multi-lane implementation fork: [`rhgo1749/Strata`](https://github.com/rhgo1749/Strata)
- ExLlamaV3 companion recipe: [`rhgo1749/qwen3.8-flash-next-exllamav3-3x5070ti-recipe`](https://github.com/rhgo1749/qwen3.8-flash-next-exllamav3-3x5070ti-recipe)

## License

Recipe documentation and helper material in this repository are MIT licensed. Strata and model files retain their own licenses.