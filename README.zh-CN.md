# Qwen3.8-Flash-Next / Strata GPU-per-Lane 并行服务方案

[English](README.md) | [한국어](README.ko.md) | **简体中文** | [日本語](README.ja.md)

本仓库记录一种实用的多 GPU 服务结构：**每张 GPU 运行一个独立 Strata generation lane**，多个 lane 进程只在主机内存中**物理共享一份大型 expert arena**。

## 当前状态

- 实现 fork：[`rhgo1749/Strata`](https://github.com/rhgo1749/Strata)
- **当前运行用 Strata pin：** [`614b2ae`](https://github.com/rhgo1749/Strata/commit/614b2ae904bbe949144c694388b985fc6a0d20d8)
- 引擎基线：Strata **0.1.27**（upstream `a790805`）
- 参考主机当前 production quant：**Qwen3.8-Flash-Next GSQ-RCO IQ3_S**
- 冻结的 paper-v1 recipe snapshot：[`f54597a`](https://github.com/rhgo1749/qwen3.8-flash-next-strata-gpu-per-lane-recipe/commit/f54597a071e56bb0412685c46c4d604d50e26e45)，branch `paper-v1`
- 冻结的 paper-v1 Strata 实现 pin：[`6cf101d`](https://github.com/rhgo1749/Strata/commit/6cf101d5b98523cbaefc34a199faa5657c5c2719)

`main` 是论文提交后的滚动运行/开发分支。即使 `main` 继续前进，**paper-v1 的证据和复现 pin 也不会被追溯修改。** 复现论文 v1 时应使用上面的冻结 snapshot 和实现 pin。

详细保留结果见 [`RESULTS.md`](RESULTS.md)。论文之后的 x4 vision-lane 实验见 [`recipe/vision-x4-lane.md`](recipe/vision-x4-lane.md)。

## 核心结构

**一个活动请求由一个 GPU lane 处理；多个请求可在不同 GPU 上并行运行。大型 expert 权重在系统 RAM 中物理共享，而不是每个进程各复制一份。**

```mermaid
flowchart TB
    C[Clients / agents / OpenAI-compatible API] --> D[Session-aware dispatcher]
    D -->|session/request A| G0[GPU lane A]
    D -->|session/request B| G1[GPU lane B]
    D -->|session/request C| G2[GPU lane C]
    E[Shared host expert arena] --> G0
    E --> G1
    E --> G2
```

CUDA 状态、GPU hot-expert cache、GPU-resident KV、host-KV/session 状态、speculative/MTP 状态以及 generation loop 都保持 lane-local。正常 production 路径不需要强制 token-by-token 跨 GPU 同步，也不依赖 NVLink。

## 论文之后的 session-aware 调度器

最初的 multi-lane supervisor 使用 request-level free-lane/round-robin。对独立吞吐测试这没问题，但 KV/prompt cache 是 lane-local 的，因此长对话后续轮次如果被送到另一张 GPU，就可能重新支付完整或大规模 prompt prefill。

当前 `main` 使用 **session affinity + live-state-aware placement**，优先级明确如下：

1. 先只保留健康、且满足硬能力条件（例如 vision）的 lane。
2. 如果请求属于已知 session，则使用该 session 记住的 lane。若该 lane busy，**等待该 lane，而不是 spill 到其他 GPU。**
3. 完全新的 session 不会插入 busy lane。若所有候选 lane 都 busy，则等到某个 request/stream 完全结束并 release lane。
4. 在 idle lane 中，优先选择没有 live conversation state 的 lane。
5. 若所有 idle 候选都有 live state，则选择 **当前 live request state 最小的 lane**，尽量减少被覆盖的 prompt-cache locality 成本。
6. 若成本相同，则优先 **最久未使用的 live state（LRU）**；最后用 rotating cursor 解决公平性平局。

排队的新 session 使用 **compatible FIFO ticket**：更早等待且可使用该 lane 的请求优先获得刚释放的 lane，而 vision 之类有 capability 约束的请求不会阻塞自己不能使用的其他 lane。已知 session 的 continuation 在等待自己的 lane 时会对该 lane 做 reservation，因此 `notify_all()` 的唤醒竞争不会让新 session 抢走 cache-rich lane。真正的空 live state 由 `live_request_bytes == 0` 判断，而不是看是否存在 affinity key。

此策略**不硬编码 GPU 编号、GPU 型号或 PCIe 宽度**。`busy` 的生命周期是 request/stream 级，affinity 的生命周期是 session 级。同一个 engine 可以记住多个 session key，因此即使中间有别的请求使用该 engine，旧 session 仍可回到同一 engine，并重新利用 Strata 的 per-engine prompt-cache checkpoint。

production smoke 已验证 A → B → C → D → A：A/B/C 分别占用空 lane，D 选择 live state 最小的 lane，最后 A 仍回到原来的 lane。另一次 overload smoke 在 3 个 lane 都忙时再加入 4 个请求，观测到 `peak_queue_depth=4`；7 个请求全部成功后恢复到 `queue_depth=0`，所有 lane 均 idle。

该调度器属于**当前 lane-local KV 架构的 serving hardening**，并不宣称是最终最优方案。cache-aware global scheduling、migration/transfer cost、overload queueing 以及更完整的 cost model 仍属于 roadmap 工作。

## 参考主机

```text
CPU                 Ryzen 9 9950X3D, 16C/32T
RAM                 128 GB DDR5
GPU lanes           RTX 5070 Ti 16 GB ×3
PCIe                x8 / x4 / x8
contexts            262144 / 262144 / 262144
resident KV         32768 / 32768 / 32768
VRAM reserve MiB    1200 / 1200 / 1200
physical CPU cores  5 / 6 / 5
production vision   1 个选定 lane
current quant       IQ3_S
```

这些是**参考主机的实测值，不是通用默认值**。

### mixed vision/text lane 的 VRAM reserve 注意事项

从启用了 vision 的基础配置派生 text-only lane 时，可以移除 `--vision` 和 encoder 配置，但不能让 VRAM 安全余量也一起消失。在参考 RTX 5070 Ti 16 GB / IQ3_S / 262K context / resident-KV 32768 环境中，non-vision lane 回退到 700 MiB reserve 后，模型加载完成时只剩约 **93 MiB** 可用 VRAM，并实际触发了 `verify: instantiate: out of memory`。

当前 production 明确设置 `--lane-vram-reserve-mibs 1200,1200,1200`。重新测量后 GPU0/GPU1/GPU2 分别剩余 **593 / 592 / 593 MiB** VRAM；三个 lane 的并发 public 请求全部返回 HTTP 200，新一轮启动后没有出现新的 OOM、illegal-memory 或 engine-stop。1200 MiB 仍然只是**参考主机的安全值**，不是所有 GPU 的通用默认值。这个问题是 mixed-capability lane 派生时 text-only lane 丢失 reserve 所暴露出来的，并不是 vision encoder 占用了 text-only GPU 的 VRAM。

主机内存可用下面的近似规则估算：

```text
required host RAM ≈ one shared expert arena + every lane's host-KV + OS/runtime headroom
```

## 论文证据边界

已提交的 paper-v1 证据固定在 recipe snapshot `f54597a` 和 Strata `6cf101d`。其中包含 1→2→3 lane scaling、shared-vs-private arena PSS、heterogeneous isolation、workload sensitivity 与 mixed-serving 结果。论文之后进入 `main` 的 vision/scheduler 修改**不会追溯写回 paper-v1 结果**。

参见：

- [`RESULTS.md`](RESULTS.md) — 保留的 benchmark evidence
- [`docs/fork-and-implementation.md`](docs/fork-and-implementation.md) — 实现/recipe 所有权与复现边界
- [`docs/paper-v1-reproducibility.md`](docs/paper-v1-reproducibility.md) — 冻结的 v1 复现链接
- [`recipe/vision-x4-lane.md`](recipe/vision-x4-lane.md) — post-v1 vision-lane 实验

## 在其他机器上应用

1. 先让每张目标 GPU 都能独立运行正常的 single-GPU Strata。
2. 检查 VRAM、实际协商的 PCIe link、RAM 余量和 CPU topology。
3. 划分 physical CPU core，避免不同 lane 的 worker pool 重叠。
4. 从保守的 context/resident-KV 值开始，先逐 lane 验证。
5. 验证多 lane 并发、cold/no-reuse 长 prompt、streaming/cancellation、lane recovery，以及 **multi-turn session affinity**。
6. 将参考主机的 tuning 值视为测量结果，而不是可直接复制的默认值。

## 相关项目

- Upstream Strata: [`Niko1221/Strata`](https://github.com/Niko1221/Strata)
- Multi-lane 实现 fork: [`rhgo1749/Strata`](https://github.com/rhgo1749/Strata)
- ExLlamaV3 companion recipe: [`rhgo1749/qwen3.8-flash-next-exllamav3-3x5070ti-recipe`](https://github.com/rhgo1749/qwen3.8-flash-next-exllamav3-3x5070ti-recipe)

## License

本仓库的 recipe 文档和辅助材料采用 MIT License。Strata 与模型文件继续遵循各自原有许可证。