# Strata 0.1.24 promotion — 2026-09-30

This record promotes the reference GPU-per-lane serving recipe from Strata 0.1.22 to **Strata 0.1.24** and records a separate adaptive hot-expert replacement experiment.

## Versions

```text
upstream          Niko1221/Strata@3ce2523c2823687de5372be3af58534f56cbf286
fork merge        rhgo1749/Strata@82a51614517392f2c5b83af7c39ffbb7abbc783e
promoted fork     rhgo1749/Strata@3824f04003b79609a7cc6861ea5b4652a47d2ddb
engine            Strata 0.1.24
reference host    Ryzen 9 9950X3D / 128 GB DDR5 / RTX 5070 Ti 16 GB x3
PCIe              Gen5 x8 / x4 / x8
```

The integration preserves the existing production architecture: one ordinary Strata engine per GPU lane, one shared host expert arena, lane-local CUDA / hot-expert cache / KV / session state, and request-level dispatch above the engines.

The supervisor also strips inherited `gpu` and `layer_split` settings from generated lane configs so an upstream multi-GPU config cannot accidentally expand one lane back into layer-split mode.

## Validation gates

The promoted candidate passed:

- 52 server and multi-GPU tests;
- the production CUDA build;
- three-lane startup with the existing 262144-token-per-lane contract;
- IQ3_XXS and IQ3_S per-lane benchmarks;
- upstream layer-split benchmarks on the same 0.1.24 generation;
- a no-reuse ~140K-token request on all three IQ3_S lanes concurrently;
- adaptive hot-expert replacement A/B and trace instrumentation.

No retained promotion run reported CUDA OOM or lane death.

## IQ3_XXS — per-lane vs layer-split

### Independent GPU lanes

Clean warm three-request wall aggregate:

- range: **218.4–233.7 tok/s**;
- mean: **225.5 tok/s**.

15K no-reuse prompt processing across the x8 / x4 / x8 lanes:

| Lane | PP |
| --- | ---: |
| GPU0 / x8 | **2453.5 tok/s** |
| GPU1 / x4 | **2046.0 tok/s** |
| GPU2 / x8 | **2450.8 tok/s** |

### Upstream 3-GPU layer-split

- clean warm single-request decode: **93.5–99.9 tok/s**;
- 15K no-reuse PP: **1144.4 tok/s**.

The 0.1.24 QSA improvements raise long-prompt performance, but they do not change the architecture decision for the target workload: independent lanes retain the concurrent-serving / per-request-isolation advantage while layer-split remains the single-request challenger.

## IQ3_S — per-lane vs layer-split

### Independent GPU lanes

Clean warm three-request wall aggregate:

- range: **176.8–199.4 tok/s**;
- mean: **187.1 tok/s**.

15K no-reuse prompt processing:

| Lane | PP |
| --- | ---: |
| GPU0 / x8 | **2381.8 tok/s** |
| GPU1 / x4 | **1852.2 tok/s** |
| GPU2 / x8 | **2371.8 tok/s** |

A separate ~140K-token no-reuse request was served concurrently on all three IQ3_S lanes without OOM or lane death.

### Upstream 3-GPU layer-split

- clean warm single-request decode: **74.2–81.7 tok/s**;
- 15K no-reuse PP: **938.0 tok/s**.

## Adaptive hot-expert replacement A/B

Strata 0.1.24 defaults to adaptive replacement every four rounds, up to 96 swaps per adaptation (`adapt_every=4`, `adapt_swaps=96`). The static control used the same IQ3_S single-lane setup with only `--adapt-swaps 0` added.

Two retained 512-token adaptive rounds averaged **69.43 tok/s**. The corresponding static-residency control averaged **54.14 tok/s**.

```text
adaptive     69.43 tok/s
static       54.14 tok/s
relative     +28.3%
```

The decode expert-cache hit rate rose from about **61%** with static residency to **86.5–87%** in the retained adaptive rounds.

This is a same-host controlled serving A/B for this IQ3_S workload. It is not a universal +28.3% claim for every prompt, cache size, quantization, or GPU.

## `miss -> adaptive swap -> GPU resident -> later GPU hit`

Optional `STRATA_ADAPT_TRACE` instrumentation records timestamps without changing the default path when tracing is disabled. The implementation stores the first observed non-resident routing time, logs the selected replacement, publishes residency only after the asynchronous H2D copy event completes, and logs the first later GPU hit for that expert.

The retained instrumented run produced:

```text
select events       22,996
resident events     22,900
first GPU-hit obs.   6,937
```

Timing summary:

| Interval | min | median | p95 | mean | max |
| --- | ---: | ---: | ---: | ---: | ---: |
| swap copy/publish wall (`copy_us`) | 12.948 ms | **33.876 ms** | 49.751 ms | 33.044 ms | 83.533 ms |
| first miss -> residency published | 20.205 ms | **10.716 s** | 26.602 s | 11.842 s | 29.920 s |
| residency published -> first later GPU hit | **0.306 ms** | **154.249 ms** | 1.228 s | 325.423 ms | 6.742 s |
| first miss -> first later GPU hit | 57.284 ms | **3.430 s** | 18.126 s | 5.761 s | 28.650 s |

### Timing interpretation

`copy_us` is the wall interval from enqueueing a selected swap's async H2D copy until the common completion event has been observed and the new residency table is published. It is **not** the earlier free-slot CUDA memcpy microbenchmark and can include batching / event-wait effects.

`first miss -> residency` is deliberately not a raw PCIe latency. Adaptive replacement waits for routing evidence: a non-resident expert must accumulate enough decayed usage to beat a resident victim before it is selected. The interval therefore includes policy dwell time plus the swap transfer and publication.

`residency -> first later GPU hit` measures how soon the newly resident expert is actually routed again. The fastest retained observation was about **0.306 ms**; the median was about **154 ms**. Only the first later hit per traced expert is logged, so the hit count is not the total number of cache hits.

The trace therefore demonstrates the requested state transition directly: a previously non-resident expert is selected against a victim, copied into that victim's slot, published as resident after transfer completion, and later observed on the GPU-resident path.

## Production promotion

The reference server was promoted to the 0.1.24 production build after the gates above passed. The production IQ3_S config keeps adaptive replacement enabled by default (it does **not** set `--adapt-swaps 0`).

Production contract remains:

```text
public idle/wake proxy  127.0.0.1:8087
backend                 127.0.0.1:18087
private lanes           127.0.0.1:19087-19089
contexts                262144 / 262144 / 262144
resident KV             32768 / 32768 / 32768
CPU cores               5 / 6 / 5
pcie-frac               0.55 / 0.25 / 0.55
engine build            build-production-024/strata
```

## Relationship to earlier results

The 2026-09-29 scaling, shared-arena RAM, and heterogeneous-isolation measurements remain useful architecture evidence. The old free-slot admission microbenchmark also remains valid for what it measured. Its former statement that a full cache has no eviction is historical behavior, however: **Strata 0.1.24 now has adaptive replacement**, so full-cache misses can eventually cause a victim swap when the adaptive policy promotes the missing expert.

See also:

- [`systems-ablation-20260929.md`](systems-ablation-20260929.md)
- [`iq3-s-3lane-benchmark-20260929.md`](iq3-s-3lane-benchmark-20260929.md)
- [`../RESULTS.md`](../RESULTS.md)
