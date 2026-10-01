# Strata 0.1.30 promotion — 2026-10-01

## Promoted measurement generation

- fork/runtime commit: `dcdd46ff37b1baf5172a96389fbdc0c7b51a7dbc`
- upstream Strata v0.1.30: `30ec18ec7094550fcc594fd948220d511d80464e`
- binary SHA-256: `cc4236096662b1786a7730316002cbd38850f7451b517102fe4fec89eadf0147`
- CUDA: 13.4.92, sm_120 Release build
- NVIDIA driver: 615.71.09
- model: Qwen3.8-Flash-Next GSQ-RCO IQ3_S
- host: Ryzen 9 9950X3D, 128 GB DDR5, RTX 5070 Ti ×3 + RTX 5060 Ti ×1

Upstream 0.1.30 contains the shared expert arena primitive from Strata PR #129. The lane runtime now composes upstream's native `--shared-expert-arena` path; the old fork-owned mmap interception wrapper is gone. Lane configs force `--conversation-cache-mib 0` until the supervisor can model parked-conversation locality.

Implementation validation: full serving suite 125 passed / 5 skipped; server+multi-GPU subset 96 passed; CUDA build passed; 38/41 registered CTests passed, with the remaining three unavailable only because external model/pack fixtures were absent.

## 1 → 2 → 3 lane scaling

Fixed reasoning prompt `429fe691f25560a1`, 1469 prompt tokens, 512 completion tokens, temperature 0, seed 1234, 262144 context/lane, 32768 resident KV/lane, clean warm reuse. Aggregate TG is total output tokens divided by one common wall interval.

| Lanes | Aggregate TG mean ± SD | Range | Speedup | Parallel efficiency |
| ---: | ---: | ---: | ---: | ---: |
| 1 | **70.804 ± 1.546 tok/s** | 69.413–73.251 | 1.000× | 100.0% |
| 2 | **132.760 ± 3.129 tok/s** | 128.680–137.449 | **1.875×** | **93.8%** |
| 3 | **189.486 ± 3.205 tok/s** | 186.137–193.713 | **2.676×** | **89.2%** |

No retained scaling repetition was discarded.

## Shared expert arena PSS

Two fully loaded engines, GPU0+GPU2, IQ3_S, 32768 context and 8192 resident KV per engine.

| Arena mode | Two-engine PSS |
| --- | ---: |
| Private | **98.924864 GiB** |
| Shared | **52.083863 GiB** |
| Saved | **46.841001 GiB / 47.35%** |

The shared file was 50,294,992,896 bytes (4096-byte header + arena), inode 16. Each engine mapped the same 49,116,200 KiB payload with `Shared_Dirty=49,116,200 KiB` and `Private_Dirty=0`.

## Heterogeneous isolation

RTX 5070 Ti x8 fast lane vs the same lane concurrently with RTX 5060 Ti x4. Retained data are 8 solo and 8 concurrent conditions. To avoid client-tool timeout overlap, the original ABBA×4 sequence was executed as four short ABBA chunks; each chunk had non-retained warmups before its retained ABBA block.

| Measurement | Mean ± SD |
| --- | ---: |
| RTX 5070 Ti solo lane-local TG | **71.563 ± 1.760 tok/s** |
| RTX 5070 Ti concurrent lane-local TG | **71.163 ± 1.456 tok/s** |
| RTX 5060 Ti concurrent lane-local TG | **57.575 ± 1.527 tok/s** |
| Common-wall concurrent aggregate | **113.898 ± 2.985 tok/s** |

The fast-lane mean differs by only **0.56%**, smaller than ordinary run-to-run dispersion in this set. The safe conclusion is that this measured pair shows no material pacing of the fast lane.

## Mixed three-lane serving

Fiction/coding/reasoning were rotated across GPU0 x8 / GPU2 x8 / GPU1 x4, three rotations × three retained repetitions.

- common-wall aggregate: **184.669 ± 5.966 tok/s**, n=9, range 176.771–194.852
- fiction lane-local TG: **62.689 ± 2.372 tok/s**
- coding lane-local TG: **69.922 ± 2.717 tok/s**
- reasoning lane-local TG: **65.944 ± 1.874 tok/s**

Rotation prevents workload class from being permanently confounded with one physical GPU.

## Workload sensitivity

Five retained repetitions per workload/state. No-reuse PP/TTFT is separated from warm decode TG.

| Workload | No-reuse PP | TTFT | Warm TG |
| --- | ---: | ---: | ---: |
| Fiction short | **853.83 tok/s** | **1.807 s** | **67.88 tok/s** |
| Fiction medium | **2581.13 tok/s** | **5.856 s** | **68.20 tok/s** |
| Coding short | **831.60 tok/s** | **1.767 s** | **76.38 tok/s** |
| Coding medium | **2590.13 tok/s** | **5.851 s** | **78.36 tok/s** |
| Reasoning short | **850.67 tok/s** | **1.781 s** | **73.78 tok/s** |
| Reasoning medium | **2583.89 tok/s** | **5.877 s** | **66.44 tok/s** |
| Long review (~110K) | **2581.56 tok/s** | **42.875 s** | **62.10 tok/s** |

These cache/speculation observations are descriptive, not causal.

## Three-lane oversubscription

The supervisor's server-side lease trace is the source of truth for queue wait. The run retained 92 requests total, all `finish_reason=length`, all on the promoted fork/binary. Repetition counts were chosen so each request-count bucket had at least 20 retained requests for p95 reporting.

| Requests | Runs | Aggregate TG | Queue p50 / p95 | E2E p50 / p95 |
| ---: | ---: | ---: | ---: | ---: |
| 3 | 7 | **190.35 tok/s** | 5.1 / 8.2 ms | 7.96 / 8.28 s |
| 4 | 5 | **140.33 tok/s** | 6.6 / 7433.7 ms | 7.96 / 14.62 s |
| 6 | 4 | **192.39 tok/s** | 11.3 / 8300.6 ms | 8.30 / 16.54 s |
| 9 | 3 | **195.41 tok/s** | 7704.4 / 15744.7 ms | 15.59 / 23.60 s |

The 4-request aggregate is lower because one request forms a second wave while only three occupy the first wave; 6 and 9 requests keep all three lanes occupied for two and three full waves. Jain service-throughput fairness remained ~0.997–0.999 across buckets.

## Matched independent lanes ↔ three-GPU layer split

Both arms use 0.1.30 IQ3_S, the fixed reasoning prompt, 262K context, 32K resident KV, temperature 0, seed 1234 and conversation parking disabled.

Layer split uses GPU order 0,2,1. It intentionally leaves `--pcie-frac` unset so 0.1.30 probes each stage independently: 28.9 GB/s → 0.55, 28.9 GB/s → 0.55, 14.5 GB/s → 0.31. Auto placement chose **K=18,33** and estimated ~98.8% routed-mass cache coverage.

| Region | Independent lanes | 3-GPU layer split |
| --- | ---: | ---: |
| One warm request, 512-token TG | **70.804 ± 1.546 tok/s** | **102.976 ± 1.527 tok/s** |
| Three simultaneous requests, common-wall aggregate | **189.486 ± 3.205 tok/s** | **102.588 ± 1.629 tok/s** |
| Short reasoning no-reuse PP | **850.67 tok/s** | **807.11 tok/s** |
| Short reasoning TTFT | **1.781 s** | **1.867 s** |

For this host, layer split is **45.4% faster for one warm decode request**. With three simultaneous equal requests, independent lanes deliver **84.7% more aggregate throughput** because the ordinary layer-split server serializes model generation rather than continuously batching requests. In the clean five-batch serial test, each 512-token request itself decoded at ~103.6 tok/s, but total batch completion was ~14.6–15.2 s versus ~7.8–8.3 s per request in the independent three-lane run.

This is a workload-region result, not an overall winner score.

## Promotion decision

The required Gate 0 implementation/provenance checks and Gate 1 headline matrix are complete on one 0.1.30 generation. Gate 2 oversubscription and Gate 3 layer-split A/B are also complete. Strata 0.1.30 at `dcdd46f` is therefore the promoted measurement generation for this recipe. Historical 0.1.27 and earlier results remain in the repository for comparison but are no longer the current baseline.
