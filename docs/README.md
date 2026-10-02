# Documentation index

This directory keeps the current operational and benchmark records for the GPU-per-lane Strata recipe.

## Current operational baseline

- [`phase3-shared-arena-lifecycle-20261002.md`](phase3-shared-arena-lifecycle-20261002.md) — current 0.1.31 Phase 3 lifecycle promotion: one authoritative shared-arena population, follower attach, startup A/B, production wake and correctness gate.
- [`strata-0.1.31-promotion-20261001.md`](strata-0.1.31-promotion-20261001.md) — initial 0.1.31 upstream-sync parity promotion: implementation tests, live serving smoke, persistent scheduler parity and shared-arena structural evidence.
- [`fork-and-implementation.md`](fork-and-implementation.md) — ownership and architecture boundary between upstream Strata, Strata-Lanes and this recipe repository.

## Retained benchmark generation

- [`strata-0.1.30-promotion-20261001.md`](strata-0.1.30-promotion-20261001.md) — complete 0.1.30 architecture-performance matrix.
- Phase 1 / Phase 2 experiment records live under [`../bench/`](../bench/) with their retained raw evidence.

The Phase 3 record is the current operational lifecycle gate on top of the 0.1.31 parity baseline. The broader architecture-performance matrix remains versioned as 0.1.30.

Older generations are intentionally omitted from the moving `main` branch and remain available through Git history and named snapshots.
