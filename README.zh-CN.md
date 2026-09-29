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
```

这些数值只属于参考主机，不是其他机器的默认值。

## 如何理解性能数字

本仓库会把不同测量条件分开，不把最大的数字直接当作统一结果。

- **controlled clean short-warm aggregate：** **216.1 tok/s**，clean wall-time 的最佳结果为 **221.1 tok/s**。
- **长上下文真实工作负载 aggregate TG：** 约 **175–190 tok/s**。
- **第二次 undervolt 后的 lane-local TG：** **78.8 / 78.4 / 80.1 tok/s**，合计 **237.3 tok/s lane-sum**。
- **第二次 undervolt 后的 no-reuse PP spot check：** **1,529.7 / 1,421.6 / 1,536.9 tok/s**，平均约 **1,496 tok/s/lane**。

> **第二次 undervolt 后观察到 237.3 tok/s lane-sum，但 clean wall-timed warm aggregate 的最佳结果仍是 221.1 tok/s。**

237.3 不是 clean aggregate，因此不应写成“aggregate throughput 从 221.1 提升到了 237.3 tok/s”。这些测量的 workload、timing、cache state 和 speculative acceptance 并不相同。

详细测量结果：[`RESULTS.md`](RESULTS.md)  
第二次 undervolt 数据：[`docs/undervolt-v2-20260929.md`](docs/undervolt-v2-20260929.md)  
完整参考主机验证：[`docs/reference-host-validation-20260929.md`](docs/reference-host-validation-20260929.md)  
实现关系：[`docs/fork-and-implementation.md`](docs/fork-and-implementation.md)

## 迁移到其他机器

先让普通 single-GPU Strata 配置稳定工作，再根据每张 GPU 的 VRAM、PCIe link、CPU/RAM 资源决定 lane 数量。CPU core、context、resident KV 和 PCIe 相关参数应在目标主机上重新测量，而不是直接复制参考值。

## 仓库职责

`rhgo1749/Strata` 保留通用实现、测试和架构/roadmap。具体硬件、主机调优和 benchmark 记录保存在本 recipe 仓库。

## 相关项目

- Upstream Strata: [`Niko1221/Strata`](https://github.com/Niko1221/Strata)
- Multi-lane implementation fork: [`rhgo1749/Strata`](https://github.com/rhgo1749/Strata)
- ExLlamaV3 companion recipe: [`rhgo1749/qwen3.8-flash-next-exllamav3-3x5070ti-recipe`](https://github.com/rhgo1749/qwen3.8-flash-next-exllamav3-3x5070ti-recipe)

## License

本仓库中的 recipe 文档和 helper material 使用 MIT License。Strata 和模型文件保留各自许可。
