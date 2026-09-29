# Qwen3.8-Flash-Next / Strata GPU-per-Lane 並列サービング・レシピ

[English](README.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | **日本語**

このリポジトリは、**GPU 1枚につき独立した Strata generation lane を1つ**動かし、大きな host-RAM expert arena は lane 間で物理的に1コピーだけ共有するサービング方式をまとめたものです。

実測リファレンスは **RTX 5070 Ti 16 GB ×3** です。IQ3_XXS は performance-oriented な比較基準として維持し、現在のリファレンス・ホストの実運用モデルは **Qwen3.8-Flash-Next GSQ-RCO IQ3_S** です。

実装: [`rhgo1749/Strata`](https://github.com/rhgo1749/Strata)  
**現在の promoted implementation pin:** [`9dda206`](https://github.com/rhgo1749/Strata/commit/9dda206874387b20cac20837a1452f115a8f9f93)  
**現在の promoted engine:** Strata **0.1.22**

## 基本アイデア

- 1つのリクエストは1つの GPU lane が処理する。
- 複数リクエストは別々の GPU lane で同時に処理できる。
- 大きな host expert arena は物理 RAM 上で1コピーだけ共有する。
- CUDA state、hot-expert cache、KV、session state は lane-local のままにする。
- 通常の decode path では GPU 間の token-by-token 同期を必須にしない。

そのため、遅い GPU は割り当てられたリクエストだけを遅くし、他の lane の token rate を直接引き下げません。反対に、リクエストが1つしかない場合は他の GPU lane が idle になることがあります。

## リファレンス・ホスト

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

これらはリファレンス・ホスト固有の実測値であり、別マシンの既定値ではありません。

基本的な sizing ルールは次の通りです。

> 使用する各 GPU がまず single-GPU Strata lane を単独で正常に動かせること。そのうえで、全 lane を同時に動かすための RAM / CPU / PCIe 余裕をホスト側に確保すること。

host RAM は概ね次のように見積もります。

```text
必要 host RAM ≈
    shared expert arena 1つ
  + 全 lane の host-KV
  + OS / server / filesystem-cache の余裕
```

expert arena を GPU 枚数分掛ける必要はありません。この fork の重要な点の1つが、その大きな arena を物理 RAM 上で共有することです。

## 現在の promoted performance — Strata 0.1.22

現在の recipe baseline は fork commit `9dda206`、engine 0.1.22 です。既存の3-lane起動契約はそのまま互換で、migration flag は不要でした。

### IQ3_XXS performance reference

- clean warm 3-request wall aggregate: **226.5–227.9 tok/s**
- midpoint: 約 **227.2 tok/s**
- 15,064-token no-reuse single-lane PP spot check: **2,492.2 tok/s**

旧 **237.3 tok/s** は engine-reported lane-sum として有効な履歴値ですが、clean wall-clock aggregate ではありません。

### IQ3_S current deployment benchmark

Strata 0.1.22 の IQ3_S runtime は **46.84 GiB** の shared expert arena と、lane ごとに **4524 slots / 8.63 GiB** の hot-expert cache を使用します。

2つの backend session で保持した4つの warm round は:

```text
183.9 / 190.8 / 196.8 / 209.7 tok/s wall aggregate
```

したがって **現在の IQ3_S warm range は 183.9–209.7 tok/s、4 round 平均は 195.3 tok/s** です。

Concurrent no-reuse prompt processing:

| Measurement | GPU0 x8 | GPU1 x4 | GPU2 x8 |
| --- | ---: | ---: | ---: |
| 15,048-token PP | **2,325.6** | **1,806.5** | **2,293.0 tok/s** |
| 30,024-token PP | **2,352.1** | **1,812.9** | **2,348.3 tok/s** |

30K run の x8 lane 平均は **2,350.2 tok/s**、中央の x4 lane は約 **22.9%** 遅くなりました。保持した long-prompt request はすべて **0 reused** で、CUDA OOM、API failure、lane death はありませんでした。

旧 IQ3_S ~30K dataset は **1,553.7 / 1,323.9 / 1,545.1 tok/s** でした。今回の 0.1.22 はその履歴 benchmark generation より約 **+51.4% / +36.9% / +52.0%** 高い値ですが、prompt content と runtime generation が完全に同一の strict A/B ではありません。

詳細: [`docs/iq3-s-3lane-benchmark-20260929.md`](docs/iq3-s-3lane-benchmark-20260929.md)

## Layer-split challenger

同じ `9dda206` binary で upstream Strata の 3-GPU layer-split も 262K で動作します。

- short single-request decode: **80.6 tok/s**
- 15,064-token no-reuse PP: **1,142.3 tok/s**

IQ3_XXS の同じ 15K PP probe では request-per-lane path が約 **2.18×** の PP を示し、layer-split は single-request decode で優位でした。

したがって architecture decision は変わりません。**concurrent-agent serving の production baseline は independent request lanes**、layer-split は single-request-oriented workload 向け challenger として残します。

## Full-window validation

3本の実ソフトウェアレビュー prompt を、全 lane 262K context で同時実行しました。

- 141,578 input / 992 output tokens
- 144,875 input / 1,295 output tokens
- 144,777 input / 871 output tokens

3本とも context overflow、CUDA OOM、API failure、lane death なしで完了しました。これは **262K ×3 capacity / client compatibility** の証拠であり、throughput headline とは分けて扱います。

## 別の PC に適用する場合

使用予定の各 GPU でまず single-GPU Strata を安定動作させ、その後 GPU ごとの VRAM、実際の PCIe link、CPU/RAM 資源に合わせて lane 数を決めます。CPU core、context、resident KV、PCIe 関連値はリファレンス値をコピーせず、対象ホスト上で再測定してください。

## 詳細ドキュメント

- [`RESULTS.md`](RESULTS.md) — current / historical reference-host results
- [`docs/strata-0.1.22-promotion-20260929.md`](docs/strata-0.1.22-promotion-20260929.md) — current 0.1.22 promotion
- [`docs/iq3-s-3lane-benchmark-20260929.md`](docs/iq3-s-3lane-benchmark-20260929.md) — current IQ3_S benchmark
- [`docs/reference-host-validation-20260929.md`](docs/reference-host-validation-20260929.md) — 262K ×3 full-window validation
- [`docs/fork-and-implementation.md`](docs/fork-and-implementation.md) — implementation / recipe ownership boundary

## 関連プロジェクト

- Upstream Strata: [`Niko1221/Strata`](https://github.com/Niko1221/Strata)
- Multi-lane implementation fork: [`rhgo1749/Strata`](https://github.com/rhgo1749/Strata)
- ExLlamaV3 companion recipe: [`rhgo1749/qwen3.8-flash-next-exllamav3-3x5070ti-recipe`](https://github.com/rhgo1749/qwen3.8-flash-next-exllamav3-3x5070ti-recipe)

## License

このリポジトリの recipe 文書と helper material は MIT License です。Strata とモデルファイルにはそれぞれ元のライセンスが適用されます。
