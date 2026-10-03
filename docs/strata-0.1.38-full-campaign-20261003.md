# Strata 0.1.38 full benchmark promotion — 2026-10-03

## Provenance

```text
Strata-Lanes       8ea68eaab3ee93f1c820f5103d64ca251cfe52b6
upstream Strata    99f3dbd0b21d1401b3769e0c0d963913607f380b (v0.1.38)
model/quant         Qwen3.8-Flash-Next GSQ-RCO IQ3_S
host                Ryzen 9 9950X3D / 128 GB DDR5
primary GPUs        RTX 5070 Ti 16 GB x3 (x8/x8/x4 ordering in the campaign harness)
heterogeneous peer  RTX 5060 Ti 16 GB x4
driver/CUDA         615.71.09 / CUDA 13.4
```

This campaign promotes **0.1.38 as the current full measurement generation** while retaining 0.1.30 as historical evidence. One cross-version limitation matters: the old 0.1.30 fixed-prompt bytes were not retained, only hashes/derived rows. The 0.1.38 prompts are fixed and matched *within this campaign*, but workload-level 0.1.30↔0.1.38 comparisons are contract-matched rather than byte-identical. The separately documented 0.1.31→0.1.38 bounded prefill A/B remains the byte-matched cross-version check.

## Independent-lane scaling

| Active lanes | Common-wall aggregate TG | Speedup | Efficiency |
| ---: | ---: | ---: | ---: |
| 1 | **67.45 ± 2.20 tok/s** | 1.000× | 100.0% |
| 2 | **129.41 ± 2.95 tok/s** | **1.919×** | **95.9%** |
| 3 | **173.26 ± 6.67 tok/s** | **2.569×** | **85.6%** |

Corrected mixed fiction/coding/reasoning serving, with two warmups after every rotation and three retained reps per rotation, measured **178.86 ± 3.33 tok/s** across nine runs.

## Prefill and workload sensitivity

Cold no-reuse PP is the clearest 0.1.38 movement. The three ~15K workload classes cluster tightly around 2.80k tok/s:

| Workload | Bucket | Cold PP | Warm decode TG |
| --- | --- | ---: | ---: |
| fiction | short | **865.1 ± 19.2** | 69.1 ± 1.5 |
| coding | short | **866.8 ± 5.1** | 66.5 ± 5.7 |
| reasoning | short | **870.0 ± 3.8** | 69.1 ± 1.5 |
| fiction | medium | **2800.4 ± 15.1** | 63.2 ± 2.0 |
| coding | medium | **2795.4 ± 17.2** | 69.8 ± 3.6 |
| reasoning | medium | **2804.7 ± 13.5** | 63.7 ± 4.7 |
| long_review | long | **2628.2 ± 5.3** | 67.4 ± 2.1 |


The campaign direction agrees with the earlier byte-matched 0.1.31→0.1.38 A/B (+9.5% at ~15K, +7.3% at ~30K). Because the 0.1.30 prompt bytes are unavailable, do not turn the contract-matched 0.1.30↔0.1.38 differences into exact percentage claims.

## Oversubscription

The corrected M=3 arm was rerun after an explicit synchronized warmup and through the direct multigpu backend so lane and exact queue headers were retained.

| Simultaneous requests | Aggregate TG | Queue p50 | Queue p95 | E2E p95 |
| ---: | ---: | ---: | ---: | ---: |
| 3 | **173.55 ± 3.34** | 2.9 ms | 8.8 ms | 9.08 s |
| 4 | **130.88 ± 1.12** | 4.9 ms | 8197.6 ms | 15.71 s |
| 6 | **183.98 ± 2.97** | 4012.3 ms | 8638.7 ms | 16.65 s |
| 9 | **183.38 ± 3.90** | 8231.2 ms | 16828.7 ms | 25.26 s |


The partial-second-wave M=4 trough and M=6/M=9 recovery remain visible: three lanes stay busy across later waves, while queue tail grows with wave count.

## Heterogeneous isolation

The first standalone-GPU3 attempt was discarded because CPU affinity was not partitioned. The retained ABBA run uses explicit disjoint CPU sets for the RTX 5070 Ti and RTX 5060 Ti engines.

| Measurement | TG |
| --- | ---: |
| RTX 5070 Ti solo | **68.90 ± 1.74** |
| RTX 5070 Ti concurrent | **68.75 ± 1.10** |
| RTX 5060 Ti concurrent | **55.65 ± 1.25** |
| Common-wall aggregate | **110.08 ± 2.44** |

Raw fast-lane delta is **-0.22%**. Speculative acceptance is 0.646 solo vs 0.656 concurrent. A linear adjustment for acceptance estimates the concurrent arm at **-0.74%** relative to the solo mean; the arm coefficient 95% interval is **[-1.26, 0.23] tok/s**, crossing zero. This run therefore does **not** establish a material fast-lane slowdown.

## Shared expert arena PSS

The historical 0.1.30 memory snapshot used 32K context and 8192 resident KV per engine, so 0.1.38 was remeasured under that exact memory contract before cross-version interpretation.

| Context / resident KV | Private two-engine PSS | Shared two-engine PSS | Saved |
| --- | ---: | ---: | ---: |
| 32K / 8192 (matched historical contract) | **95.67 GiB** | **52.11 GiB** | **43.56 GiB / 45.5%** |
| 262K / 32768 (production contract) | **95.93 GiB** | **58.04 GiB** | **37.89 GiB / 39.5%** |

For the matched 32K case, each shared process maps the same **49,116,204 KiB** arena with `Shared_Dirty=49,116,204 KiB` and `Private_Dirty=0 KiB`. The 0.1.30 matched shared PSS was 52.084 GiB; 0.1.38 is 52.111 GiB, so the physical sharing primitive remains structurally intact.

## Independent lanes vs three-GPU layer split

Within the fixed 0.1.38 campaign prompt:

| Workload region | Independent lanes | Three-GPU layer split |
| --- | ---: | ---: |
| One warm request | **67.45 tok/s** | **101.90 ± 1.39 tok/s** |
| Three simultaneous requests | **173.26 tok/s** | **102.84 ± 0.70 tok/s** |

Layer split is about **51.1%** faster for the single warm request, while three independent lanes provide about **68.5%** more aggregate throughput for three simultaneous requests because the ordinary layer-split server serializes requests through FIFO.

Three-GPU layer-split cold PP measured **1033.1 ± 14.8 tok/s**. The historical 0.1.30 contract measured 807.1 ± 11.8 tok/s, but the prompt bytes differ, so the apparent ~28% cross-version increase is treated only as corroborating direction. The byte-matched single-lane A/B is the stronger version-level evidence for prefill improvement.

## Promotion interpretation

0.1.38 keeps the central Lanes result intact: independent request-level lanes scale well for concurrent work, while layer split remains complementary for a single request. The shared expert arena still removes roughly one expert-arena copy from host PSS. The most repeatable version-level change is faster prompt processing; decode throughput and heterogeneous isolation do not show a comparably clear structural change in this campaign.

Raw retained evidence and the machine-readable summary live under [`bench/raw/0.1.38-20261003/`](../bench/raw/0.1.38-20261003/).
