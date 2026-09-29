# Qwen3.8-Flash-Next / Strata GPU-per-Lane 並列サービング・レシピ

[English](README.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | **日本語**

このリポジトリは、**GPU 1枚につき独立した Strata generation lane を1つ**動かし、大きな host-RAM expert arena は lane 間で物理的に1コピーだけ共有するサービング方式をまとめたものです。

実測リファレンスは **RTX 5070 Ti 16 GB ×3 + Qwen3.8-Flash-Next IQ3_XXS** です。ただし設計自体は3枚構成や特定 GPU に限定されません。

実装: [`rhgo1749/Strata`](https://github.com/rhgo1749/Strata)  
整理済みリファレンス実装 commit: [`844d6206`](https://github.com/rhgo1749/Strata/commit/844d62064b4327f80eae0f2980ccbd83b04fbe9a)

## 基本アイデア

- 1つのリクエストは1つの GPU lane が処理する。
- 複数リクエストは別々の GPU lane で同時に処理できる。
- 大きな host expert arena は物理 RAM 上で共有する。
- CUDA state、hot-expert cache、KV、session state は lane-local のままにする。
- 通常の decode path では GPU 間の token-by-token 同期を必須にしない。

そのため、遅い GPU は割り当てられたリクエストだけを遅くし、他の lane の token rate を直接引き下げません。反対に、リクエストが1つしかない場合は他の GPU lane が idle になることがあります。

## 推奨ハードウェアの目安

この実装は特定の3 GPU構成にハードコードされていません。基本ルールは次の通りです。

> **使用する各 GPU がまず single-GPU Strata lane を単独で正常に動かせること。そのうえで、全 lane を同時に動かすための RAM / CPU / PCIe 余裕をホスト側に確保すること。**

| 項目 | 実用的な開始点 | multi-lane 推奨 | 検証済みリファレンス |
| --- | --- | --- | --- |
| OS | Linux | 現行 64-bit Linux | Ubuntu Linux |
| GPU 数 | NVIDIA GPU 2枚 | 2–4枚 | 3枚 |
| GPUごとの VRAM | 選択した single-GPU Strata 設定を収容できること。upstream の対応モデルは 12 GB から | hot-expert cache / resident KV の余裕を考え **16 GB+ / GPU** を推奨 | RTX 5070 Ti 16 GB ×3 |
| System RAM | shared expert arena 1つ + 全 lane の host-KV + OS/runtime の余裕 | 実際の quant/context から算出。本 3-lane IQ3_XXS 262K ×3 recipe では **128 GB を検証済み推奨値**として使用 | 128 GB |
| CPU | 現在の auto partition は lane あたり最低 2 physical cores を要求 | 余裕があれば **active lane あたり 4–6 physical cores** から開始 | Ryzen 9 9950X3D 16C/32T、5 / 6 / 5 |
| PCIe | 各 GPU に安定した実用リンク | 可能なら広いリンクを優先し、非対称 topology は実測で調整 | Gen5 x8 / x4 / x8 |
| Storage | SSD | NVMe SSD | NVMe |
| NVLink | 不要 | 不要 | なし |
| PSU / 冷却 | CPU + 全 GPU の同時負荷を支えられること | 通常の電力・温度マージンを確保 | ホスト依存 |

これらは**汎用の最低要件ではなくガイドライン**です。小さい quant、少ない lane、短い context なら RAM を減らせる可能性があり、逆に lane/context/model が大きくなれば必要量も増えます。

RAM は次のように考えると分かりやすいです。

```text
必要 host RAM ≈
    shared expert arena 1つ
  + lane 0 host-KV
  + lane 1 host-KV
  + ...
  + OS / server / filesystem-cache の余裕
```

expert arena を GPU 枚数分掛ける必要はありません。この fork のポイントの1つが、その大きな arena を物理 RAM 上で共有することです。

より詳しい sizing / bring-up ガイドは実装 fork の [`docs/multigpu-hardware-guide.md`](https://github.com/rhgo1749/Strata/blob/main/docs/multigpu-hardware-guide.md) を参照してください。

## リファレンス・ホスト

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

これらはリファレンス・ホスト固有の実測値であり、別マシンの既定値ではありません。

## 正式な性能データ

この recipe の公開性能データは**2回目の undervolt 状態**を正本とします。それ以前の pre-second-undervolt throughput は代表値として使用しません。

- warm lane-local TG: **78.8 / 78.4 / 80.1 tok/s**;
- lane-sum TG: **237.3 tok/s**;
- no-reuse PP spot check: **1,529.7 / 1,421.6 / 1,536.9 tok/s**;
- 3つの独立 PP 観測の平均: 約 **1,496 tok/s/lane**;
- 約 **141K–145K token** の full-window request を3本同時に処理し、context overflow / CUDA OOM / lane death なしで完了。

> **237.3 tok/s は各 lane の engine-reported TG を合計した lane-sum であり、clean wall-clock aggregate ではありません。**

PP 3件も同期した1回の prefill ではなく独立した spot check なので、aggregate PP として合算しません。141K–145K ×3 の試験は **262K ×3 capacity / client compatibility** の検証として扱い、正式な throughput benchmark とは分けます。

詳細な測定結果: [`RESULTS.md`](RESULTS.md)  
2回目の undervolt dataset: [`docs/undervolt-v2-20260929.md`](docs/undervolt-v2-20260929.md)  
リファレンス・ホスト検証: [`docs/reference-host-validation-20260929.md`](docs/reference-host-validation-20260929.md)  
実装と recipe の役割分担: [`docs/fork-and-implementation.md`](docs/fork-and-implementation.md)

## 別の PC に適用する場合

使用予定の各 GPU でまず single-GPU Strata を安定動作させ、その後 GPU ごとの VRAM、実際の PCIe link、CPU/RAM 資源に合わせて lane 数を決めます。CPU core、context、resident KV、PCIe 関連値はリファレンス値をコピーせず、対象ホスト上で再測定してください。

## リポジトリの役割

`rhgo1749/Strata` は汎用実装、テスト、architecture/roadmap を保持します。具体的なハードウェア構成、ホスト固有 tuning、benchmark 記録はこの recipe リポジトリが保持します。

## 関連プロジェクト

- Upstream Strata: [`Niko1221/Strata`](https://github.com/Niko1221/Strata)
- Multi-lane implementation fork: [`rhgo1749/Strata`](https://github.com/rhgo1749/Strata)
- ExLlamaV3 companion recipe: [`rhgo1749/qwen3.8-flash-next-exllamav3-3x5070ti-recipe`](https://github.com/rhgo1749/qwen3.8-flash-next-exllamav3-3x5070ti-recipe)

## License

このリポジトリの recipe 文書と helper material は MIT License です。Strata とモデルファイルにはそれぞれ元のライセンスが適用されます。
