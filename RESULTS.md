# Results

This repository owns the reference-host measurements for the GPU-per-lane Strata recipe. The implementation fork intentionally keeps only generic runtime and roadmap contracts.

## Reference implementation

- CPU: AMD Ryzen 9 9950X3D, 16C/32T
- RAM: 128 GB DDR5
- GPU: 3 × RTX 5070 Ti 16 GB
- PCIe: Gen5 x8 / x4 / x8
- model: Qwen3.8-Flash-Next, Strata IQ3_XXS
- sanitized implementation pin: [`rhgo1749/Strata@844d6206`](https://github.com/rhgo1749/Strata/commit/844d62064b4327f80eae0f2980ccbd83b04fbe9a)

## Canonical three-lane policy

```text
lane contexts       262144 / 262144 / 262144
host-KV guard       786432 tokens
resident KV         32768 / 32768 / 32768
physical CPU cores  5 / 6 / 5
pcie-frac           0.55 / 0.25 / 0.55
shared expert arena ~39.97 GiB
core V/F plateau    2300 MHz @ >=875 mV
VRAM offset         +2500
power limit         250 W cap per GPU
```

The GPU tuning state above is the **canonical public measurement state** for this recipe. Earlier pre-second-undervolt throughput figures are intentionally not used as promoted results.

## Canonical performance measurements

### Warm lane-local decode

Fixed short probes used `temperature=0` and `max_tokens=256`.

| Lane | Prompt reuse | TG | MTP/spec accepted |
| --- | --- | ---: | ---: |
| GPU0 | 72 reused + 5 read | **78.8 tok/s** | 126 / 166 (**75.9%**) |
| GPU1 | 69 reused + 5 read | **78.4 tok/s** | 129 / 157 (**82.2%**) |
| GPU2 | 73 reused + 5 read | **80.1 tok/s** | 141 / 177 (**79.7%**) |

Lane-sum:

```text
78.8 + 78.4 + 80.1 = 237.3 tok/s
```

**237.3 tok/s is a lane-sum of engine-reported TG, not a clean wall-clock aggregate.** It should be labeled as such in public comparisons.

### No-reuse prompt-processing spot checks

These are independent lane observations with zero reused prompt tokens. They were not one synchronized three-lane prefill and therefore must not be summed into an aggregate PP number.

| Lane | Prompt tokens | Read time | PP | Following TG |
| --- | ---: | ---: | ---: | ---: |
| GPU0 | 45,519 | 29,756 ms | **1,529.7 tok/s** | 56.4 tok/s |
| GPU1 | 45,812 | 32,226 ms | **1,421.6 tok/s** | 50.1 tok/s |
| GPU2 | 64,972 | 42,275 ms | **1,536.9 tok/s** | 57.2 tok/s |

Mean PP across the three independent spot checks is about **1,496 tok/s/lane**.

## Full-window concurrency validation

Separately from the canonical performance dataset, the runtime was capacity-validated with three independent real software-review prompts running concurrently:

| Client | Input tokens | Output tokens | Finish |
| --- | ---: | ---: | --- |
| A | 141,578 | 992 | `stop` |
| B | 144,875 | 1,295 | `stop` |
| C | 144,777 | 871 | `stop` |

All three inputs exceeded the former 131,072-token per-lane limit. No context-overflow error, CUDA OOM, API failure, or lane death occurred.

This run is retained as **262K ×3 capacity and client-compatibility evidence**, not as the canonical throughput benchmark.

## Resident-KV boundary

Testing a larger GPU-resident KV window showed that giving KV more VRAM can displace the hot-expert tier. The promoted reference host therefore keeps **32K resident KV on each lane** rather than maximizing resident KV in isolation.

## Reporting rule

For this repository:

- the 2300 MHz / 875 mV tuning state above is the canonical performance state;
- `237.3 tok/s` must be described as **lane-sum**, not wall aggregate;
- independent PP spot checks must not be summed unless their prefill intervals are known to overlap;
- full-window validation is reported separately from short warm performance.

## More detail

- [`docs/undervolt-v2-20260929.md`](docs/undervolt-v2-20260929.md) — canonical GPU tuning and PP/TG dataset
- [`docs/reference-host-validation-20260929.md`](docs/reference-host-validation-20260929.md) — sanitized full-window and serving validation
- [`bench/README.md`](bench/README.md) — measurement/reporting rules
- [`docs/multigpu-shared-runtime.md`](https://github.com/rhgo1749/Strata/blob/main/docs/multigpu-shared-runtime.md) — generic implementation contract
- [`docs/multigpu-roadmap.md`](https://github.com/rhgo1749/Strata/blob/main/docs/multigpu-roadmap.md) — generic implementation roadmap
