# Strata 0.1.34 software-sync promotion — 2026-10-02

## Scope

Strata 0.1.34 is promoted as the current **software baseline** for the GPU-per-lane recipe after a bounded upstream-sync compatibility gate.

This promotion does not claim a fresh performance result. The independent request/session-lane architecture is unchanged, the latest full live three-lane lifecycle evidence remains the 0.1.31 Phase 3 campaign, and the complete architecture-performance matrix remains the retained 0.1.30 generation.

## Provenance

- promoted Strata-Lanes main: `4b5b47d6e50250b71c52fe4fe7d33593684dce91`
- clean upstream integration merge: `a96b2cd7d9c4a505c4bdb5cb9c2a87ade5f32684`
- upstream Strata 0.1.34: `1678de333d0e0711bc414ad992b640e1a37dd814`
- CUDA: 13.4.92, sm_120 Release
- NVIDIA driver: 615.71.09
- built `strata` SHA-256: `8d34efb9161b64a68029feffa780d24e7f5b27dbcad3d96b3508231924d3fc87`

## Merge result

The upstream sync preserves the independent GPU-per-lane supervisor and Phase 3 shared-arena leader/follower lifecycle while absorbing upstream 0.1.32-0.1.34 changes.

The three textual conflicts were resolved deliberately:

- `AGENTS.md`: retain upstream Strata working/install guidance and the fork's decision-provenance policy;
- `src/program/generate.cpp`: keep the fork's `--shared-expert-arena-follower` and upstream's explicit resident-CPU mode semantics;
- `tools/mtp_fetch.py`: take upstream 0.1.34, whose HTTP range validation and pinned SHA-256 verification supersede the fork's narrower partial-download repair.

Upstream changes to layer-split/prefill, low-RAM/KV behavior, server cancellation, AMD/setup/MCP paths and MTP integrity are therefore inherited without replacing the request-level lane architecture.

## Compatibility gate

- Lanes-specific Python suite: **58 passed**
- full Python serving suite: **204 passed / 7 skipped**
- CUDA 13.4.92 sm_120 Release configure/build: **PASS**, 237/237 build steps completed
- registered CTests: **48 passed / 2 skipped / 3 external-fixture unavailable**
- generated IQ fixture tests skipped when their fixture was absent
- external model/pack tests unavailable as before: `ple_parity`, `expert_parity`, `pool_test`
- no new fixture-independent failure

## Measurement boundary

No long model-backed three-lane benchmark campaign was rerun for this bounded maintenance sync.

Therefore:

- 0.1.34 is the current software/compatibility baseline;
- 0.1.31 remains the latest full live serving and Phase 3 startup/lifecycle evidence;
- 0.1.30 remains the full architecture-performance generation, including 1→2→3 scaling and matched layer-split A/B;
- none of those older measured numbers are relabeled as 0.1.34 results.

The newer upstream layer-split/prefill implementation should be treated as a stronger future single-request challenger when the matched A/B is next refreshed; it does not by itself change the roadmap or the serving baseline.

## Decision

Promote Strata 0.1.34 as the current software baseline and keep the independent-lane architecture unchanged.

Continue to use the existing Phase 1/2 serving-control and Phase 3 lifecycle gates as regression controls. Reopen later architecture challengers only when their measured trigger fires.
