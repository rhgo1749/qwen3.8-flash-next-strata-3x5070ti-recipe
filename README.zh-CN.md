# Qwen3.8-Flash-Next / Strata GPU-per-Lane 并行服务配方

[English](README.md) | [한국어](README.ko.md) | **简体中文** | [日本語](README.ja.md)

这个仓库记录一种 Strata 多 GPU 服务方式：**每张 GPU 运行一个独立 generation lane**，同时多个 lane 共享系统内存中的大型 expert arena。

实测参考配置为 **RTX 5070 Ti 16 GB ×3**。IQ3_XXS 保留为 performance-oriented 对照配置，而当前参考主机实际部署的是 **Qwen3.8-Flash-Next GSQ-RCO IQ3_S**。

实现仓库：[`rhgo1749/Strata`](https://github.com/rhgo1749/Strata)  
**当前 promoted implementation pin：** [`9dda206`](https://github.com/rhgo1749/Strata/commit/9dda206874387b20cac20837a1452f115a8f9f93)  
**当前 promoted engine：** Strata **0.1.22**

## 核心结构

- 一个请求由一个 GPU lane 处理。
- 多个请求可由不同 GPU lane 并发执行。
- 大型 host expert arena 只保留一份物理 RAM 副本。
- CUDA state、hot-expert cache、KV 和 session state 保持 lane-local。
- 正常 decode 路径不要求 GPU 之间逐 token 同步。

因此较慢的 GPU 只影响分配给它的请求，不会成为所有 GPU 的逐 token 同步瓶颈。代价是单个请求通常只使用一个 GPU lane。

## 参考主机

```text
CPU                 Ryzen 9 9950X3D, 16C/32T
RAM                 128 GB DDR5
GPUs                RTX 5070 Ti 16 GB ×3
PCIe                Gen5 x8 / x4 / x8
contexts            262144 / 262144 / 262144
host-KV guard       786432
resident KV         32768 / 32768 / 32768
CPU cores           5 / 6 / 5
pcie-frac           0.55 / 0.25 / 0.55
GPU V/F plateau     2300 MHz @ >=875 mV
VRAM offset         +2500
```

这些数值属于参考主机，不是其他机器的默认值。

基本 sizing 原则：

> 每一张被选中的 GPU 都应先能独立运行一个可用的 single-GPU Strata lane；主机再提供足够的 RAM、CPU 和 PCIe 资源让所有 lane 同时工作。

host RAM 可粗略理解为：

```text
所需 host RAM ≈
    1 份 shared expert arena
  + 所有 lane 的 host-KV
  + OS / server / filesystem-cache 余量
```

不要把 expert arena 按 GPU 数量相乘；本 fork 的关键之一就是让这部分在物理 RAM 中共享。

## 当前 promoted performance — Strata 0.1.22

当前 recipe baseline 为 fork commit `9dda206`、engine 0.1.22。原有 3-lane 启动方式保持兼容，不需要新的 migration flag。

### IQ3_XXS performance reference

- clean warm 三请求 wall aggregate：**226.5–227.9 tok/s**
- midpoint：约 **227.2 tok/s**
- 15,064-token no-reuse single-lane PP spot check：**2,492.2 tok/s**

旧 **237.3 tok/s** 仍是有效的历史 engine-reported lane-sum，但不是 clean wall-clock aggregate。

### IQ3_S current deployment benchmark

Strata 0.1.22 下，IQ3_S 使用 **46.84 GiB** shared expert arena，以及每 lane **4524 slots / 8.63 GiB** hot-expert cache。

两个 backend session 中保留的四个 warm round 为：

```text
183.9 / 190.8 / 196.8 / 209.7 tok/s wall aggregate
```

因此 **当前 IQ3_S warm 范围为 183.9–209.7 tok/s，四轮平均 195.3 tok/s**。

Concurrent no-reuse prompt processing：

| Measurement | GPU0 x8 | GPU1 x4 | GPU2 x8 |
| --- | ---: | ---: | ---: |
| 15,048-token PP | **2,325.6** | **1,806.5** | **2,293.0 tok/s** |
| 30,024-token PP | **2,352.1** | **1,812.9** | **2,348.3 tok/s** |

30K run 中，两条 x8 lane 平均 **2,350.2 tok/s**，中间 x4 lane 约慢 **22.9%**。保留的长 prompt 请求均为 **0 reused**，且没有 CUDA OOM、API failure 或 lane death。

旧 IQ3_S ~30K dataset 为 **1,553.7 / 1,323.9 / 1,545.1 tok/s**。当前 0.1.22 数值相对该历史 benchmark generation 约高 **+51.4% / +36.9% / +52.0%**，但 prompt content 与 runtime generation 并非完全相同，因此这不是 strict same-prompt A/B。

详细记录：[`docs/iq3-s-3lane-benchmark-20260929.md`](docs/iq3-s-3lane-benchmark-20260929.md)

## Layer-split challenger

同一个 `9dda206` binary 也保留 upstream Strata 的 3-GPU layer-split 路径，并可在 262K 启动。

- short single-request decode：**80.6 tok/s**
- 15,064-token no-reuse PP：**1,142.3 tok/s**

在 IQ3_XXS 的同一 15K PP probe 中，request-per-lane path 的 PP 约为 layer-split 的 **2.18×**；layer-split 仍保持 single-request decode 优势。

因此架构结论不变：**面向并发 agent serving 的 production baseline 是 independent request lanes**；layer-split 保留为 single-request-oriented workload 的 challenger。

## Full-window validation

三个真实 software-review prompt 在所有 lane 均配置 262K context 的情况下并发完成：

- 141,578 input / 992 output tokens
- 144,875 input / 1,295 output tokens
- 144,777 input / 871 output tokens

三者均无 context overflow、CUDA OOM、API failure 或 lane death。该结果作为 **262K ×3 capacity / client compatibility** 证据保留，不作为 throughput headline。

## 迁移到其他机器

先在准备使用的每张 GPU 上分别确认 single-GPU Strata 正常工作，再根据各卡 VRAM、实际 PCIe link 和 CPU/RAM 资源决定 lane 数量。CPU core、context、resident KV 和 PCIe 参数应在目标主机上重新测量，而不是直接复制参考值。

## 详细文档

- [`RESULTS.md`](RESULTS.md) — current / historical reference-host results
- [`docs/strata-0.1.22-promotion-20260929.md`](docs/strata-0.1.22-promotion-20260929.md) — current 0.1.22 promotion
- [`docs/iq3-s-3lane-benchmark-20260929.md`](docs/iq3-s-3lane-benchmark-20260929.md) — current IQ3_S benchmark
- [`docs/reference-host-validation-20260929.md`](docs/reference-host-validation-20260929.md) — 262K ×3 full-window validation
- [`docs/fork-and-implementation.md`](docs/fork-and-implementation.md) — implementation / recipe ownership boundary

## 相关项目

- Upstream Strata: [`Niko1221/Strata`](https://github.com/Niko1221/Strata)
- Multi-lane implementation fork: [`rhgo1749/Strata`](https://github.com/rhgo1749/Strata)
- ExLlamaV3 companion recipe: [`rhgo1749/qwen3.8-flash-next-exllamav3-3x5070ti-recipe`](https://github.com/rhgo1749/qwen3.8-flash-next-exllamav3-3x5070ti-recipe)

## License

本仓库中的 recipe 文档和 helper material 使用 MIT License。Strata 和模型文件保留各自许可。
