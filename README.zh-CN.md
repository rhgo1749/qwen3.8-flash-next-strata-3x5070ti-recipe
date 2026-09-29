# Qwen3.8-Flash-Next / Strata GPU-per-Lane 并行服务配方

[English](README.md) | [한국어](README.ko.md) | **简体中文** | [日本語](README.ja.md)

这个仓库记录一种 Strata 多 GPU 服务方式：**每张 GPU 运行一个独立 generation lane**，同时多个 lane 共享系统内存中的大型 expert arena。

实测参考配置为 **RTX 5070 Ti 16 GB ×3 + Qwen3.8-Flash-Next IQ3_XXS**，但架构本身并不限定为三张 GPU 或某个特定型号。

实现仓库：[`rhgo1749/Strata`](https://github.com/rhgo1749/Strata)  
整理后的参考实现提交：[`844d6206`](https://github.com/rhgo1749/Strata/commit/844d62064b4327f80eae0f2980ccbd83b04fbe9a)

## 核心结构

- 一个请求由一个 GPU lane 处理。
- 多个请求可由不同 GPU lane 并发执行。
- 大型 host expert arena 只保留一份物理 RAM 副本。
- CUDA state、hot-expert cache、KV 和 session state 保持 lane-local。
- 正常 decode 路径不要求 GPU 之间逐 token 同步。

因此较慢的 GPU 只影响分配给它的请求，不会像紧耦合并行那样成为所有 GPU 的同步瓶颈。代价是单个请求通常只使用一个 GPU lane。

## 硬件建议

这套实现不是为某一台三卡主机硬编码的。最重要的原则是：

> **每一张被选中的 GPU 都应先能独立运行一个可用的 single-GPU Strata lane；主机再提供足够的 RAM、CPU 和 PCIe 资源让所有 lane 同时工作。**

| 项目 | 实用起点 | 多 lane 建议 | 已验证参考主机 |
| --- | --- | --- | --- |
| OS | Linux | 当前 64-bit Linux | Ubuntu Linux |
| GPU 数量 | 2 张 NVIDIA GPU | 2–4 张 | 3 张 |
| 每卡 VRAM | 足够容纳所选 single-GPU Strata 配置；upstream 支持的模型从 12 GB 起 | 为 hot-expert cache / resident KV 留余量时建议 **16 GB+ / GPU** | RTX 5070 Ti 16 GB ×3 |
| 系统 RAM | 1 份 shared expert arena + 所有 lane 的 host-KV + OS/runtime 余量 | 按实际 quant/context 计算；**本 3-lane IQ3_XXS 262K ×3 配方已验证并推荐 128 GB** | 128 GB |
| CPU | 当前自动分区至少需要每 lane 2 个 physical cores | 可用时建议从 **每个 active lane 4–6 个 physical cores** 起步 | Ryzen 9 9950X3D 16C/32T，5 / 6 / 5 |
| PCIe | 每张 GPU 都有稳定可用的链路 | 能更宽则更好；不对称拓扑应按实测调参 | Gen5 x8 / x4 / x8 |
| Storage | SSD | NVMe SSD | NVMe |
| NVLink | 不需要 | 不需要 | 无 |
| PSU / 散热 | 能承受 CPU + 所有 GPU 同时负载 | 为多 GPU 同时工作保留正常电气和散热余量 | 依主机而定 |

这些只是**建议，不是通用最低规格**。更小的 quant、更少的 lane 或更短的 context 可以降低 RAM 需求；更多 lane、更长 context 或更大的模型则可能需要更多资源。

RAM 可以用下面的方式理解：

```text
所需 host RAM ≈
    1 份 shared expert arena
  + lane 0 host-KV
  + lane 1 host-KV
  + ...
  + OS / server / filesystem-cache 余量
```

不要把 expert arena 按 GPU 数量相乘；本 fork 的关键之一就是让这部分在物理 RAM 中共享。

更完整的 sizing 和 bring-up 清单见实现仓库的 [`docs/multigpu-hardware-guide.md`](https://github.com/rhgo1749/Strata/blob/main/docs/multigpu-hardware-guide.md)。

## 参考主机

```text
CPU                 Ryzen 9 9950X3D
RAM                 128 GB DDR5
GPUs                RTX 5070 Ti 16 GB ×3
PCIe                Gen5 x8 / x4 / x8
model               Qwen3.8-Flash-Next IQ3_XXS
contexts            262144 / 262144 / 262144
resident KV         32768 / 32768 / 32768
CPU cores           5 / 6 / 5
pcie-frac           0.55 / 0.25 / 0.55
shared expert arena ~39.97 GiB
GPU V/F plateau     2300 MHz @ >=875 mV
VRAM offset         +2500
```

这些数值只属于参考主机，不是其他机器的默认值。

## 正式性能数据

本 recipe 的公开性能基准以**第二次 undervolt 状态**为准；更早的 pre-second-undervolt throughput 不再作为主结果。

- warm lane-local TG：**78.8 / 78.4 / 80.1 tok/s**；
- lane-sum TG：**237.3 tok/s**；
- no-reuse PP spot check：**1,529.7 / 1,421.6 / 1,536.9 tok/s**；
- 三次独立 PP 观测的平均值约 **1,496 tok/s/lane**；
- 约 **141K–145K token** 的三个 full-window 请求可并发完成，无 context overflow、CUDA OOM 或 lane death。

> **237.3 tok/s 是各 lane 的 engine-reported TG 之和，也就是 lane-sum，不是 clean wall-clock aggregate。**

三次 PP 也是独立 spot check，不应直接相加成 aggregate PP。141K–145K ×3 的测试保留为 **262K ×3 capacity / client compatibility** 证据，而不是正式 throughput benchmark。

详细数据：[`RESULTS.md`](RESULTS.md)  
第二次 undervolt 数据：[`docs/undervolt-v2-20260929.md`](docs/undervolt-v2-20260929.md)  
完整参考主机验证：[`docs/reference-host-validation-20260929.md`](docs/reference-host-validation-20260929.md)  
实现关系：[`docs/fork-and-implementation.md`](docs/fork-and-implementation.md)

## 迁移到其他机器

先在准备使用的每张 GPU 上分别确认 single-GPU Strata 正常工作，再根据各卡 VRAM、实际 PCIe link 和 CPU/RAM 资源决定 lane 数量。CPU core、context、resident KV 和 PCIe 参数应在目标主机上重新测量，而不是直接复制参考值。

## 仓库职责

`rhgo1749/Strata` 保留通用实现、测试和架构/roadmap。具体硬件、主机调优和 benchmark 记录保存在本 recipe 仓库。

## 相关项目

- Upstream Strata: [`Niko1221/Strata`](https://github.com/Niko1221/Strata)
- Multi-lane implementation fork: [`rhgo1749/Strata`](https://github.com/rhgo1749/Strata)
- ExLlamaV3 companion recipe: [`rhgo1749/qwen3.8-flash-next-exllamav3-3x5070ti-recipe`](https://github.com/rhgo1749/qwen3.8-flash-next-exllamav3-3x5070ti-recipe)

## License

本仓库中的 recipe 文档和 helper material 使用 MIT License。Strata 和模型文件保留各自许可。
