# Canonical GPU tuning and PP/TG dataset — 2026-09-29

This record documents the **canonical public performance state** for the measured 3 × RTX 5070 Ti Strata reference host.

Earlier pre-second-undervolt throughput figures are intentionally not part of the promoted recipe. Public performance claims for this repository should use the measurements in this document and preserve the distinction between lane-local rates, lane-sum, and wall-clock aggregate throughput.

## Runtime configuration

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

## Canonical GPU tuning state

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

Workload-dependent board-power samples were roughly **90–150 W/GPU**, but this dataset does not provide a clean normalized power-efficiency claim.

## Environment-neutral measurement procedure

### 1. Drain unrelated traffic

Before benchmarking:

1. pause or disable the workload dispatcher used on your system;
2. wait for already in-flight client/tool loops to finish;
3. verify the serving layer reports zero active requests, if such a status endpoint exists;
4. confirm the target GPUs are idle.

Do not copy a specific process-manager command, localhost port or service name from another deployment. The requirement is simply **no unrelated model traffic during the timed interval**.

One wall-timed attempt in this dataset was discarded because pre-existing work overlapped the benchmark.

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

## Canonical warm TG result

| Lane | Prompt reuse | Generated | TG | MTP/spec drafts accepted |
| --- | --- | ---: | ---: | ---: |
| GPU0 | 72 reused + 5 read | 256 | **78.8 tok/s** | 126 / 166 (**75.9%**) |
| GPU1 | 69 reused + 5 read | 256 | **78.4 tok/s** | 129 / 157 (**82.2%**) |
| GPU2 | 73 reused + 5 read | 256 | **80.1 tok/s** | 141 / 177 (**79.7%**) |

Lane-sum:

```text
78.8 + 78.4 + 80.1 = 237.3 tok/s
```

This is a **lane-sum of engine-reported decode rates**, not a clean wall-clock aggregate. Do not publish it as an aggregate wall throughput result.

## Canonical no-reuse PP spot checks

Each row below had zero reused prompt tokens. They are independent lane observations, not one synchronized three-lane cold-prefill run, and therefore must not be summed.

| Lane | Prompt | Reused | Read time | PP | Following TG |
| --- | ---: | ---: | ---: | ---: | ---: |
| GPU0 | 45,519 | 0 | 29,756 ms | **1,529.7 tok/s** | 56.4 tok/s |
| GPU1 | 45,812 | 0 | 32,226 ms | **1,421.6 tok/s** | 50.1 tok/s |
| GPU2 | 64,972 | 0 | 42,275 ms | **1,536.9 tok/s** | 57.2 tok/s |

Mean PP of these three independent spot checks is about **1,496 tok/s/lane**.

## Interpretation

- the promoted 2300 MHz / 875 mV plateau is the recipe's canonical GPU tuning state;
- warm lane-local TG was **78.4–80.1 tok/s** in the highlighted fixed-output round;
- the corresponding engine-reported **lane-sum was 237.3 tok/s**, not a wall aggregate;
- no-reuse PP remained around **1.42–1.54k tok/s/lane**, with a mean of about **1.496k tok/s/lane** across the three independent spot checks;
- speculative acceptance in the highlighted warm round was about **76–82%**;
- expert-cache state, CPU expert work, PCIe behavior, prompt reuse and speculative acceptance remain important confounders.

## Reporting rule

When citing this dataset publicly:

```text
Warm TG / lane: 78.8 / 78.4 / 80.1 tok/s
Lane-sum:       237.3 tok/s  (NOT wall aggregate)
No-reuse PP:    1,529.7 / 1,421.6 / 1,536.9 tok/s
Mean PP:        ~1,496 tok/s/lane
```

Do not mix these values with earlier pre-second-undervolt throughput figures. A future clean synchronized wall-timed run should be added as a new canonical dataset rather than retroactively combining measurement generations.
