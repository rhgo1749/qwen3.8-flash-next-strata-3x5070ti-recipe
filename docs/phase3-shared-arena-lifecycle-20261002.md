# Phase 3 shared-arena lifecycle promotion — 2026-10-02

## Scope

This record covers the Strata-Lanes Phase 3 startup/lifecycle change on the existing Strata 0.1.31 independent-lane architecture. The inference model is unchanged: one ordinary Strata engine per GPU lane, one shared host expert arena, lane-local CUDA/hot-cache/KV/session state, and the promoted balanced-additive scheduler.

The change removes repeated source expert loading during sequential lane startup. Lane 0 becomes the authoritative arena population leader; later lanes attach as verified followers and skip their own source load only after the shared header reports a complete population.

## Provenance

- Strata-Lanes implementation commit: `4e333d8cd4731c8c365aeea984371f7853f27092`
- promoted Strata-Lanes main: `d7afade41f06d4486a4feb2dd59b2864122e0e2e`
- upstream Strata 0.1.31: `9259cad4cfa3543cd3b8decab5962672b968c649`
- exact promoted engine SHA-256: `28b247fd94c49420a6c698630a7883fc8d7723543996b39987cfe54edd1db8ff`
- previous 0.1.31 engine SHA-256: `afe4970c509860fe000131d20726972962b98179a04949212126c2742040dc4d`
- CUDA: 13.4, sm_120 Release
- driver: NVIDIA 615.71.09
- model: Qwen3.8-Flash-Next GSQ-RCO IQ3_S

Reference topology:

- RTX 5070 Ti 16 GB ×3, PCIe x8 / x4 / x8
- Ryzen 9 9950X3D, 128 GB DDR5
- context 262144 per lane
- resident GPU KV 32768 per lane
- CPU partitions 5 / 6 / 5 physical cores
- PCIe fractions 0.55 / 0.25 / 0.55
- vision lane 1
- shared arena payload about 46.84 GiB

## Lifecycle contract

The promoted contract is deliberately narrower than persistent cross-run caching.

1. Lane 0 marks the shared arena population incomplete before copying expert bytes.
2. Lane 0 publishes readiness only after the full expert load succeeds.
3. Later sequential lanes verify arena size, pack fingerprint, and readiness before entering follower mode.
4. Followers skip the duplicate source expert load; they still perform their own lane-local model initialization and GPU expert-cache fill.
5. The supervisor holds a non-blocking ownership lock for the arena pathname for its lifetime. A second supervisor using the same backing is refused before model load.
6. A new leader repopulates an existing compatible backing rather than trusting stale bytes as persistent cache state.
7. Supervisor-generated default tmpfs backing is removed on graceful exit. An explicit `--arena-file` remains operator-owned.

Persistent cross-run arena reuse and automatic child-process respawn are not part of this promotion.

## Matched startup A/B

The primary comparison used the same host, topology, model, context/KV settings and sequential lane bring-up.

| Arm | 3-lane ready time |
| --- | ---: |
| Previous 0.1.31 control | **42.218 s** |
| Phase 3 exact candidate | **27.133 s** |
| Reduction | **15.085 s / 35.73%** |

The control repeated the full 46.84 GiB source expert load on all three lanes. The candidate loaded the source once on lane 0; lane 1 and lane 2 logged `shared population ready; source load skipped`.

Earlier candidate repetitions were approximately 27.14 s as well, so the promoted exact-binary run is representative rather than a one-off outlier.

## Production wake

The production idle proxy includes launcher/holder work beyond direct supervisor startup. The previously recorded 0.1.31 wake was **42.042 s**. After the Phase 3 cutover, the same production wake path reported **34.031 s**, an **8.011 s / 19.05%** reduction.

Treat this as the user-facing operational measurement; the direct supervisor A/B above is the cleaner implementation comparison.

## Correctness and regression gates

- Python serving suite: **158 passed / 7 skipped**
- CUDA 13.4 sm_120 Release build: **PASS**
- CTests: **47 passed / 2 skipped / 3 external-fixture unavailable**
- `pinned_shared_test`: **PASS**
- exact candidate live smoke: **PASS**
- final production live smoke: **PASS**
- text routing: PASS
- vision routing on lane 1: PASS
- two-turn affinity: same lane, `cache_n=56`
- malformed request: HTTP 400
- disconnect cleanup: production 4 polls at 250 ms
- immediate recovery: PASS
- concurrent second supervisor on the same arena path: refused before model load
- same-backing full restart after a normal stop: PASS

The three unavailable CTests remain the known external-fixture boundary: `ple_parity`, `expert_parity`, and `pool_test`. Two IQ fixture tests skip when their generated fixture is absent.

## Decision

Promote the leader/follower shared-arena population lifecycle on Strata 0.1.31.

The result is an operational startup improvement, not a new inference architecture. It does not change steady-state scheduler semantics, expert routing, hot-cache ownership, host-KV ownership, or request/session parallelism.
