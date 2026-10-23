# 變異測試工具

`mutation_test.py` 會對應用程式碼注入小錯誤（變異體），再跑測試看能不能抓到。
被測試抓到 = 殺死；測試照樣全綠 = 存活，代表那段行為沒有被測試真正驗證。
結果與分析見根目錄的 [MUTATION_TESTING.md](../../MUTATION_TESTING.md)。

## 為何不直接用 mutmut

mutmut 3 會跳過「帶裝飾器的函式」以及模組 / 類別層的程式碼。在這個專案等於跳過：

- 所有 `@router.*` API 端點與其 `auth=` / `throttle=` 設定
- 所有 `@login_required` view
- pydantic `@field_validator`、Model 的 `@property`
- Schema / Model 欄位定義、模組常數（`MAX_URL_LENGTH`、`SLUG_PATTERN`…）

本工具沿用 mutmut 3.8 的節點運算子，但變異整個檔案，並另外加上
`decorator_remove`（移除裝飾器）、`stmt_delete`（刪除呼叫語句）、
`if_negate`（條件反轉）、`return_none` 四種運算子。

## 執行

需要 Postgres（與跑測試相同的連線環境變數）：

```bash
pip install mutmut==3.8.0          # 只用到它的變異運算子
POSTGRES_HOST=localhost python scripts/mutation/mutation_test.py run --workers 8
```

Docker：

```bash
docker compose exec django-ninja pip install mutmut==3.8.0
docker compose exec django-ninja python scripts/mutation/mutation_test.py run --workers 4
```

常用參數：

| 參數 | 說明 |
| --- | --- |
| `--workers N` | 平行 worker 數（每個 worker 一份專案副本 + 一個測試庫 `test_mut_w{i}`） |
| `--files a.py b.py` | 只變異指定檔案（例如改了某支檔案後快速檢查） |
| `--out DIR` | 輸出目錄（預設為新的暫存目錄） |
| `--keep` | 保留 worker 副本與測試庫，方便除錯 |

輸出目錄內有 `report.md`（分數表 + 每個存活變異體的 diff）、`results.jsonl`、`verify.jsonl`。
`python scripts/mutation/mutation_test.py report --out DIR` 可由既有結果重新產生報告。

全部約 2,400 個變異體；本專案在 12 個 worker（實際約 4 核心算力）的環境下約 26 分鐘。

## 運作方式

1. 以 libcst 解析目標檔案，對每個可變異的節點各產生一份完整的變異後原始碼。
2. 每個 worker 先跑一次全套測試（建立自己的測試庫並確認全綠）；w0 同時用
   `--cov-context=test` 記錄「每一行被哪些測試執行到」。
3. 變異體寫入某個 worker 的副本後執行 `pytest -x`：
   - 函式主體內的變異 → 只跑有執行到該行的測試
   - 模組 / 類別層的變異（import 時就生效）→ 跑全套
4. 只跑部分測試就存活的變異體，最後再用全套測試複驗一次，排除挑選誤差。
5. 測試改用 MD5 密碼雜湊（`mutation_settings.py`），create_user 從約 0.2 秒降到幾乎為零。
