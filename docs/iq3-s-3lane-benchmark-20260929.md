# IQ3_S three-lane benchmark — 2026-09-29

This note records a reference-host IQ3_S run using the same GPU-per-lane Strata architecture as the canonical IQ3_XXS recipe. It is kept as a **quality-oriented challenger profile**, not as a replacement for the IQ3_XXS production baseline.

## Host and runtime

- CPU: AMD Ryzen 9 9950X3D, 16C/32T
- RAM: 128 GB DDR5
- GPU: 3 × RTX 5070 Ti 16 GB
- PCIe: Gen5 x8 / x4 / x8
- model: Qwen3.8-Flash-Next GSQ-RCO IQ3_S
- Strata engine: 0.1.14 runtime from the multi-lane fork test checkout
- shared host expert arena: **46.84 GiB** (`50,294,988,800` bytes)
- lane contexts: `262144 / 262144 / 262144`
- aggregate host-KV guard: `786432`
- resident KV: `32768 / 32768 / 32768`
- physical CPU-core allocation: `5 / 6 / 5`
- `pcie-frac`: `0.55 / 0.25 / 0.55`
- KV mode: `int8`
- MTP/speculation: `--spec 4 --spec-min-p 0.5`

With a clean GPU state, every lane reported a **4548-slot / 8.67 GiB hot-expert cache** and about 467 MiB of VRAM free after the runtime was fully loaded.

For reference, the canonical IQ3_XXS recipe uses an approximately **39.97 GiB** shared expert arena. IQ3_S therefore increased the shared arena by about **17%** on this host.

## Measurement hygiene

The first IQ3_S bring-up was intentionally discarded from the comparative dataset because two idle-holder containers were still resident on GPU1. Together they consumed roughly 0.5 GiB of VRAM on that card, which reduced lane 1's hot-expert cache from the clean 4548 slots to 4283 slots.

Both idle holders were stopped, all three IQ3_S lanes were restarted from a clean GPU state, and only the measurements below are retained as the clean IQ3_S dataset. The idle holders were restored after the benchmark.

## Controlled concurrent short decode

Three identical requests were issued concurrently through the public three-lane proxy with `temperature=0` and `max_tokens=512`.

| Lane | Prompt | Prompt read | TG | MTP/spec accepted | Hot-cache hit | CPU pool |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| GPU0 | 89 tokens | 799 ms / 111.4 tok/s | **60.5 tok/s** | 246 / 364 (67.6%) | 86.07% | 10.46 ms/token |
| GPU1 | 89 tokens | 1,196 ms / 74.4 tok/s | **63.8 tok/s** | 252 / 328 (76.8%) | 80.94% | 12.70 ms/token |
| GPU2 | 89 tokens | 805 ms / 110.6 tok/s | **59.1 tok/s** | 238 / 336 (70.8%) | 85.18% | 10.73 ms/token |

Engine-reported TG lane-sum:

```text
60.5 + 63.8 + 59.1 = 183.4 tok/s
```

**183.4 tok/s is a lane-sum, not wall-clock aggregate throughput.**

The canonical IQ3_XXS second-undervolt reference is 237.3 tok/s lane-sum from a different short-probe dataset. Comparing those two runs gives an indicative IQ3_S decode penalty of about **23%**, but this is not a strict same-prompt, same-generation-length A/B and must not be presented as a controlled quantization delta.

## Concurrent ~30K no-reuse prefill

Three unique approximately 30K-token prompts were launched concurrently. All reported zero prompt reuse.

| Lane | Prompt tokens | Read time | PP | Following TG |
| --- | ---: | ---: | ---: | ---: |
| GPU0 | 30,079 | 19,359 ms | **1,553.7 tok/s** | 53.7 tok/s |
| GPU1 | 30,079 | 22,719 ms | **1,323.9 tok/s** | 52.7 tok/s |
| GPU2 | 30,079 | 19,468 ms | **1,545.1 tok/s** | 52.1 tok/s |

The two x8 lanes averaged about **1,549 tok/s**, while the x4 middle lane was about **14.6% slower** at 1,323.9 tok/s. On this larger quant, the asymmetric PCIe lane is therefore a visible prefill bottleneck and is a useful target for a future `pcie-frac` sweep.

The three per-lane PP rates must not be presented as a clean wall-clock aggregate. They are engine-reported lane rates from overlapping concurrent requests.

## Power samples during the concurrent ~30K run

`nvidia-smi` samples were collected while the three requests were active:

| GPU | Mean sampled board power | Max sampled board power | Mean sampled SM clock |
| --- | ---: | ---: | ---: |
| GPU0 | 97.8 W | 128.9 W | 2222 MHz |
| GPU1 | 107.8 W | 129.2 W | 2221 MHz |
| GPU2 | 114.7 W | 145.5 W | 2218 MHz |

These are board-power samples, not wall-power measurements and not a normalized efficiency A/B.

## Interpretation

The clean run establishes that IQ3_S is viable on the same 3 × 16 GB GPU / 128 GB host with 262K context configured on every lane. The main observed trade-off is lower short-decode throughput together with a larger shared expert arena and a smaller hot-expert tier. Long-prompt prefill remained strong on the x8 lanes, while the x4 lane showed a larger topology penalty.

For this repository, IQ3_XXS remains the canonical performance profile. IQ3_S is retained as the higher-quality challenger profile until a controlled same-prompt quality/performance A/B shows that the quality gain is worth the decode cost for the intended agent workload.
