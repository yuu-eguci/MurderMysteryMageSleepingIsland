MurderMysteryMageSleepingIsland
===

[![CI](https://github.com/yuu-eguci/MurderMysteryMageSleepingIsland/actions/workflows/ci.yml/badge.svg)](https://github.com/yuu-eguci/MurderMysteryMageSleepingIsland/actions/workflows/ci.yml)

マーダーミステリー「魔法使いの眠る島」で、1ターン目終了時のドローンの状態 (HP・場所・アイテム) から、各プレイヤーの正体の候補 (誰が BLACK か) を求めるソルバーだよ。

- Python: 3.12 / 3.13 / 3.14 (標準ライブラリのみ)
- Lint: flake8
- Test: pytest (全 19,200 ケースの網羅チェックを含む)
- Docker: 非対応 (標準ライブラリだけで動くオフラインツールなので不要)

## パッと実行してみたい

Repository のルートで実行してね。

```bash
python3 -m mage_island_solver examples/sample.json
python3 -m mage_island_solver examples/sample.json --json
```

入力はゲームごとの観測結果を並べた JSON だよ。

```json
{
  "games": [
    {
      "seats": ["PYTHON", "TASK", "MONITOR", "DB"],
      "hp": -1,
      "location": "RED",
      "items": ["RED", "PURPLE"]
    }
  ]
}
```

| キー | 内容 |
| --- | --- |
| `seats` | コードを入力した順のプレイヤー名 (4人、全ゲームで同じメンバー) |
| `hp` | 1ターン目終了時のドローンの HP (整数。負の値もそのまま) |
| `location` | `INITIAL` / `RED` / `BLUE` / `GREEN` / `PURPLE` |
| `items` | ドローンの所持アイテム (`RED` / `BLUE` / `GREEN` / `PURPLE`、順不同) |

終了コード:

| コード | 意味 |
| --- | --- |
| 0 | 全ゲームと矛盾しない割り当てがある |
| 1 | 矛盾 (一致するケースがない。入力ミスか、モデルが実際のルールと違う) |
| 2 | 入力エラー |

## 注意

- 公式ルールブックとは照合していない。
- モデルの仮定は [docs/RULES.md](docs/RULES.md) にまとめている。
- 1ターン目だけが対象だよ。
- 在庫切れの挙動は仮定。
- この仮定に依存するケースが答えに含まれると、警告が出る。

## 開発

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements-dev.txt
.venv/bin/python -m flake8 .
.venv/bin/python -m pytest
```

開発用の依存は `requirements-dev.in` に書き、ハッシュつきの `requirements-dev.txt` を pip-tools で生成する。

```bash
pip-compile --generate-hashes --strip-extras --no-emit-index-url --output-file requirements-dev.txt requirements-dev.in
```
