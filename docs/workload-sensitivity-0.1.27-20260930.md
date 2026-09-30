# Strata 0.1.27 workload sensitivity — 2026-09-30

This experiment is intentionally separate from the fixed-workload 1->2->3 lane scaling benchmark. Its purpose is to observe how prompt processing, decode throughput, expert locality, and speculative decoding vary across realistic request classes on the promoted 0.1.27 fork.

## Baseline

- fork HEAD: `6cf101d5b98523cbaefc34a199faa5657c5c2719`
- upstream: Strata 0.1.27 `a79080535d1b2a71a3419a0d97d8e7dca194b0f1`
- model: Qwen3.8-Flash-Next GSQ-RCO IQ3_S
- workload lane: RTX 5070 Ti GPU0, PCIe x8
- repetitions: 5 per retained workload/bucket/state
- short prompts: roughly 1.4K–1.5K tokens
- medium prompts: roughly 15K tokens
- long review: roughly 110K tokens

The publication CSV retains every repetition: [`../bench/workload-sensitivity-0.1.27-20260930.csv`](../bench/workload-sensitivity-0.1.27-20260930.csv).

## Measurement classes

Two classes were retained and must not be merged into one distribution:

1. **No-reuse PP/TTFT** — prompt reuse is zero and the run is used primarily for prompt-processing throughput and TTFT. These rows are not a perfect cold-expert-cache reset: expert-cache hit rate changes across sequential repetitions, so they should not be advertised as a pure expert-cache cold-start A/B.
2. **Warm steady-state TG** — almost the entire prompt is reused and 256 output tokens are generated. These runs are used for stable decode, cache-hit, and speculative-acceptance comparisons.

The 16-token decode attached to no-reuse PP runs is too short and too variable to be a headline TG measurement.

## No-reuse prompt processing

| Workload | Bucket | Prompt tokens | n | Mean PP | SD PP | Mean TTFT |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Fiction | short | 1,517 | 5 | **887.88 tok/s** | 19.61 | **1.73 s** |
| Coding | short | 1,446 | 5 | **895.93 tok/s** | 15.06 | **1.64 s** |
| Reasoning | short | 1,490 | 5 | **939.10 tok/s** | 5.87 | **1.61 s** |
| Fiction | medium | 14,957 | 5 | **2553.38 tok/s** | 6.68 | **5.91 s** |
| Coding | medium | 15,012 | 5 | **2542.27 tok/s** | 10.12 | **5.96 s** |
| Reasoning | medium | 15,026 | 5 | **2553.71 tok/s** | 8.89 | **5.94 s** |
| Long review | long | 109,958 | 5 | **2554.09 tok/s** | 3.89 | **43.32 s** |

### PP interpretation

The largest PP change is associated with the prompt-length regime, not content class. At matched ~15K lengths, fiction/coding/reasoning means are within about 0.5% of one another. The ~1.5K prompts operate at a lower throughput regime, while ~15K and ~110K prompts are near 2.54–2.55k tok/s on this lane.

This workload matrix does **not** isolate PCIe width: all single-lane workload runs use GPU0 x8. Therefore it cannot answer whether PP changes with x4 versus x8 independently of workload and topology.

The 110K review run is stable: mean PP 2554.09 tok/s and mean TTFT 43.32 s across five no-reuse repetitions.

## Warm steady-state decode

| Workload | Bucket | n | Mean TG | SD TG | Mean cache hit | Spec acceptance |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Fiction | short | 5 | **68.64 tok/s** | 3.46 | **90.56%** | **50.77%** |
| Fiction | medium | 5 | **67.98 tok/s** | 3.61 | **89.42%** | **56.28%** |
| Coding | short | 5 | **79.30 tok/s** | 2.35 | **86.96%** | **73.70%** |
| Coding | medium | 5 | **79.42 tok/s** | 0.89 | **86.22%** | **75.27%** |
| Reasoning | short | 5 | **76.98 tok/s** | 0.97 | **87.78%** | **72.14%** |
| Reasoning | medium | 5 | **68.06 tok/s** | 1.59 | **86.50%** | **63.66%** |
| Long review | long | 5 | **62.98 tok/s** | 0.57 | **84.14%** | **68.73%** |

## TG sensitivity

Decode throughput is workload-sensitive in this measurement generation.

- Coding is the fastest of the matched short/medium classes at about **79.3–79.4 tok/s**.
- Fiction is around **68 tok/s** in both short and medium buckets.
- Reasoning changes more with prompt/task shape: **76.98 tok/s** short and **68.06 tok/s** medium.
- The ~110K review settles at **62.98 tok/s** after prompt reuse.

These are workload-specific observations, not universal model-category constants.

## Expert locality

Fiction has the **highest cache-hit rate** in the short/medium warm runs, yet it does not have the highest TG. Coding is faster while showing a somewhat lower expert-cache hit rate.

That is direct evidence against a simplistic claim that higher expert-cache hit rate alone determines decode throughput. Cache locality matters, but the observed TG distribution also tracks differences in speculative acceptance and potentially other engine behavior.

No causal coefficient is claimed from this small matrix.

## Speculative decoding

Speculative/MTP acceptance differs materially by workload:

- fiction: roughly **51–56%**;
- coding: roughly **74–75%**;
- reasoning: roughly **64–72%**;
- long review: roughly **69%**.

The coding workload combines high speculative acceptance with the highest warm TG despite lower cache-hit rate than fiction. This makes speculative acceptance a plausible contributor to the TG difference, but the experiment does not isolate it causally because MTP was not disabled as a matched control.

## Adaptive replacement

All retained workload rows report **zero adaptive swap publications** during the measured windows. Consequently this experiment does **not** establish that adaptive replacement benefits one workload class more than another.

The repository's separate controlled adaptive-on/off experiment remains the evidence for adaptive replacement itself. Workload-specific adaptive benefit remains an open measurement question.

## Mixed three-lane support run

A separate three-lane run rotated fiction, coding, and reasoning across GPU0 x8, GPU2 x8, and GPU1 x4. Nine common-wall repetitions produced **187.15 ± 5.63 tok/s** aggregate (range **176.85–196.18**).

This supports real mixed-agent serving, but it should not be used to infer a clean x8-vs-x4 workload effect because GPU assignment, workload content, and shared host activity vary together.

## Paper-safe conclusions

1. On the reference x8 lane, no-reuse PP is much more sensitive to prompt-length regime than to fiction/coding/reasoning content at matched ~15K lengths.
2. Warm decode throughput differs materially by workload class and prompt/task shape.
3. Expert-cache hit rate alone does not explain the observed TG ordering.
4. Speculative acceptance also differs substantially by workload and is a plausible contributor to TG variance.
5. A ~110K input remains stable for no-reuse PP/TTFT and subsequent warm decode on this 0.1.27 configuration.

## Not justified by this dataset

- Causal attribution of TG differences to cache hit rate.
- Causal attribution of TG differences to speculative decoding without an MTP-off control.
- Workload-specific adaptive-replacement benefit.
- A PCIe-width effect on PP from this workload matrix.
- Generalization of these workload numbers to other prompts, models, quants, GPUs, or machines.
