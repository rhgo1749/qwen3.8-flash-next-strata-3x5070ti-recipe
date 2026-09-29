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
```

これらはリファレンス・ホスト固有の実測値であり、別マシンの既定値ではありません。

## 性能値の読み方

異なる測定条件の数値を1つのランキングとして混ぜないようにしています。

- **controlled clean short-warm aggregate:** **216.1 tok/s**、clean wall-time の best は **221.1 tok/s**。
- **long-context real-workload aggregate TG:** 約 **175–190 tok/s**。
- **2回目の undervolt 後の lane-local TG:** **78.8 / 78.4 / 80.1 tok/s**、合計 **237.3 tok/s lane-sum**。
- **2回目の undervolt 後の no-reuse PP spot check:** **1,529.7 / 1,421.6 / 1,536.9 tok/s**、平均約 **1,496 tok/s/lane**。

> **2回目の undervolt 後に 237.3 tok/s lane-sum を観測しましたが、clean wall-timed warm aggregate の best は 221.1 tok/s のままです。**

237.3 は clean aggregate ではありません。そのため「aggregate throughput が 221.1 から 237.3 tok/s に向上した」とは記載しません。workload、timing、cache state、speculative acceptance が異なるためです。

詳細な測定結果: [`RESULTS.md`](RESULTS.md)  
2回目の undervolt dataset: [`docs/undervolt-v2-20260929.md`](docs/undervolt-v2-20260929.md)  
リファレンス・ホスト検証: [`docs/reference-host-validation-20260929.md`](docs/reference-host-validation-20260929.md)  
実装と recipe の役割分担: [`docs/fork-and-implementation.md`](docs/fork-and-implementation.md)

## 別の PC に適用する場合

まず通常の single-GPU Strata 設定を安定動作させ、その後 GPU ごとの VRAM、PCIe link、CPU/RAM 資源に合わせて lane 数を決めます。CPU core、context、resident KV、PCIe 関連値はリファレンス値をコピーせず、対象ホスト上で再測定してください。

## リポジトリの役割

`rhgo1749/Strata` は汎用実装、テスト、architecture/roadmap を保持します。具体的なハードウェア構成、ホスト固有 tuning、benchmark 記録はこの recipe リポジトリが保持します。

## 関連プロジェクト

- Upstream Strata: [`Niko1221/Strata`](https://github.com/Niko1221/Strata)
- Multi-lane implementation fork: [`rhgo1749/Strata`](https://github.com/rhgo1749/Strata)
- ExLlamaV3 companion recipe: [`rhgo1749/qwen3.8-flash-next-exllamav3-3x5070ti-recipe`](https://github.com/rhgo1749/qwen3.8-flash-next-exllamav3-3x5070ti-recipe)

## License

このリポジトリの recipe 文書と helper material は MIT License です。Strata とモデルファイルにはそれぞれ元のライセンスが適用されます。
