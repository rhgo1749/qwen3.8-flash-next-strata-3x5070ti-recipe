# Documentation index

This directory keeps the current operational and benchmark records for the GPU-per-lane Strata recipe.

## Current operational baseline

- [`strata-0.1.38-full-campaign-20261003.md`](strata-0.1.38-full-campaign-20261003.md) — current 0.1.38 full architecture-performance campaign.
- [`strata-0.1.38-promotion-20261003.md`](strata-0.1.38-promotion-20261003.md) — 0.1.38 software-sync promotion: merge provenance, compatibility gate, live smoke, and byte-matched bounded prefill A/B.
- [`strata-0.1.34-promotion-20261002.md`](strata-0.1.34-promotion-20261002.md) — retained 0.1.34 software-sync promotion.
- [`phase3-shared-arena-lifecycle-20261002.md`](phase3-shared-arena-lifecycle-20261002.md) — retained latest full live/lifecycle promotion on 0.1.31: authoritative shared-arena population, follower attach, startup A/B, production wake and correctness gate.
- [`strata-0.1.31-promotion-20261001.md`](strata-0.1.31-promotion-20261001.md) — retained 0.1.31 live upstream-sync parity promotion: implementation tests, live serving smoke, persistent scheduler parity and shared-arena structural evidence.
- [`fork-and-implementation.md`](fork-and-implementation.md) — ownership and architecture boundary between upstream Strata, Strata-Lanes and this recipe repository.

## Retained benchmark generations

- [`strata-0.1.30-promotion-20261001.md`](strata-0.1.30-promotion-20261001.md) — retained historical 0.1.30 architecture-performance matrix.
- Phase 1 / Phase 2 experiment records live under [`../bench/`](../bench/) with their retained raw evidence.

The 0.1.38 sync record is the current software compatibility gate and the 0.1.38 full-campaign record is the current architecture-performance generation. The Phase 3 lifecycle record remains versioned as 0.1.31 and the former full matrix remains retained as 0.1.30 historical evidence.

Older generations are intentionally omitted from the moving `main` branch and remain available through Git history and named snapshots.
