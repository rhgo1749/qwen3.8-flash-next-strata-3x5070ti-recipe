# Second undervolt PP/TG experiment — 2026-09-29

This record documents the second GPU undervolt pass on the measured 3 × RTX 5070 Ti Strata reference host.

The useful result is **no observed throughput regression at the 2300 MHz undervolt plateau**. A warm lane-local round reached 78.8 / 78.4 / 80.1 tok/s, or **237.3 tok/s lane-sum**. That value is not presented as proof that undervolting itself caused a speedup because the wall-timed interval was not clean enough for a strict stock-vs-undervolt A/B.

## Runtime held constant

- model: Qwen3.8-Flash-Next Strata IQ3_XXS
- GPUs: 3 × RTX 5070 Ti 16 GiB
- lane contexts: `262144,262144,262144`
- total static host-KV guard: `786432`
- resident KV: `32768,32768,32768`
- physical CPU cores: `5,6,5`
- per-lane `pcie-frac`: `0.55,0.25,0.55`
- MTP enabled
- speculative verify setting: `--spec 4`
- speculative minimum probability: `--spec-min-p 0.5`
- suffix/prompt-lookup drafter left at its normal default

For the short throughput probe, requests used `temperature=0` and `max_tokens=256` to reduce sampling variance.

## GPU tuning state

The same V/F policy was applied to all three cards:

```text
core V/F policy
  >= 875 mV : 2300 MHz plateau
  <  875 mV : curve points above 2300 MHz clamped to 2300 MHz

VRAM offset : +2500
power limit : 250 W cap, unchanged
```

The 250 W value is a limit, not measured workload draw.

Observed loaded graphics clocks during Strata traffic were roughly **2257–2302 MHz**. The observed memory clock was **15051 MHz** in `nvidia-smi`.

Workload-dependent board-power samples were roughly **90–150 W/GPU**, but this experiment did not provide a clean enough power A/B to publish a normalized power-efficiency claim.

## Environment-neutral measurement procedure

### 1. Drain unrelated traffic

Before benchmarking:

1. pause or disable the workload dispatcher used on your system;
2. wait for already in-flight client/tool loops to finish;
3. verify the serving layer reports zero active requests, if such a status endpoint exists;
4. confirm the target GPUs are idle.

Do not copy a specific process-manager command, localhost port or service name from another deployment. The requirement is simply **no unrelated model traffic during the timed interval**.

One wall-timed attempt in this experiment was discarded because pre-existing work overlapped the benchmark.

### 2. Verify the applied clock state

```bash
nvidia-smi \
  --query-gpu=index,power.draw,power.limit,clocks.current.graphics,clocks.current.memory,temperature.gpu,utilization.gpu \
  --format=csv
```

Sample the same fields periodically over the benchmark interval rather than relying on one instantaneous reading.

### 3. Use fixed lane endpoints

Send one request directly to each lane endpoint so request-to-lane assignment is deterministic:

```text
lane 0 -> <lane-0-endpoint>
lane 1 -> <lane-1-endpoint>
lane 2 -> <lane-2-endpoint>
```

Warm the prompt/cache state first, then issue the three fixed requests together.

Read TG from each lane's own Strata engine summary, including speculative acceptance:

```text
... generated in ... ms (... tok/s), drafts accepted A of B
```

## Warm TG result

| Lane | Prompt reuse | Generated | TG | MTP/spec drafts accepted |
| --- | --- | ---: | ---: | ---: |
| GPU0 | 72 reused + 5 read | 256 | **78.8 tok/s** | 126 / 166 (**75.9%**) |
| GPU1 | 69 reused + 5 read | 256 | **78.4 tok/s** | 129 / 157 (**82.2%**) |
| GPU2 | 73 reused + 5 read | 256 | **80.1 tok/s** | 141 / 177 (**79.7%**) |

Lane-sum:

```text
78.8 + 78.4 + 80.1 = 237.3 tok/s
```

This is a **lane-sum of engine-reported decode rates**, not a clean wall aggregate.

For reference, the earlier controlled warm result was 216.1 tok/s wall aggregate, with a best observed round of 221.1 tok/s. The later lane-local result therefore supports the narrower conclusion that the 2300 MHz plateau did not create an obvious decode regression.

## Post-undervolt PP spot checks

Each row below had zero reused prompt tokens. They are useful no-reuse sanity checks, but they were not one synchronized three-lane cold-prefill run and therefore must not be summed.

| Lane | Prompt | Reused | Read time | PP | Following TG |
| --- | ---: | ---: | ---: | ---: | ---: |
| GPU0 | 45,519 | 0 | 29,756 ms | **1,529.7 tok/s** | 56.4 tok/s |
| GPU1 | 45,812 | 0 | 32,226 ms | **1,421.6 tok/s** | 50.1 tok/s |
| GPU2 | 64,972 | 0 | 42,275 ms | **1,536.9 tok/s** | 57.2 tok/s |

Mean PP of these three independent spot checks is about **1,496 tok/s/lane**.

## Interpretation

- the 2300 MHz / 875 mV plateau did not visibly starve the measured Strata decode path;
- warm lane-local TG remained in the high-70s to ~80 tok/s when speculative acceptance was healthy;
- no-reuse PP remained around 1.4–1.54k tok/s/lane in the measured post-undervolt workload;
- speculative acceptance in the highlighted warm round was about 76–82%;
- expert-cache state, CPU expert work, PCIe behavior, prompt reuse and speculative acceptance remain important confounders.

## Cleaner future power A/B

For a defensible efficiency comparison, repeat the same fixed request set with only the V/F curve changed:

1. baseline V/F curve;
2. 875 mV / 2300 MHz plateau;
3. identical warmup;
4. identical concurrent decode requests;
5. identical cold-prefill prompts;
6. record PP/TG, speculative acceptance, average/peak GPU power, temperature, actual clock and wall power over the same interval.

Until such an A/B is available, this document makes no percentage power-savings claim.