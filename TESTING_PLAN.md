# Django Ninja Shortener - Pytest 測試計畫

本文件為 `django-ninja-shortener` 專案規劃的自動化測試策略。使用 `Pytest` 及 `pytest-django` 確保應用程式的穩定性、可靠性與可維護性。

## 1. 測試環境與設定

- **測試框架:** `pytest`, `pytest-django`, `pytest-cov`
- **測試資料庫:** PostgreSQL（Docker 環境）或 SQLite（本地環境）
- **測試工具:**
  - Django Ninja `TestClient` 用於 API 測試
  - Django `Client` 用於視圖測試
- **Fixtures 管理:** `shortener/tests/conftest.py` 集中管理共用 fixtures

## 2. 測試統計

| 項目 | 數值 |
|------|------|
| 測試案例總數 | 423 |
| 測試覆蓋率 | 99%（`pytest --cov=.`；只算應用程式碼為 97%） |
| 變異分數 | 93.3%（見 [MUTATION_TESTING.md](MUTATION_TESTING.md)） |
| 測試檔案數 | 18 |

## 3. 測試分類與範疇

### Ⅰ. 單元測試 (Unit Tests)

專注於測試單一元件（模型、函式）的正確性。

#### `shortener/tests/test_models.py`

| 測試案例 | 目標 |
|----------|------|
| `test_link_model_creation` | 驗證 Link 模型創建 |
| `test_short_code_uniqueness` | 驗證 short_code 唯一性約束 |
| `test_link_model_string_representation_*` | 驗證 __str__ 方法 |
| `test_link_is_expired_*` | 驗證過期機制（is_expired property） |

#### `shortener/tests/test_models_preview.py`

| 測試案例 | 目標 |
|----------|------|
| `test_create_preview` | 驗證 LinkPreview 模型創建 |
| `test_one_to_one_relationship` | 驗證 OneToOne 關聯 |
| `test_has_preview_data_*` | 驗證預覽資料判斷 |
| `test_cascade_delete` | 驗證級聯刪除 |
| `test_fetch_status_choices` | 驗證抓取狀態選項 |

#### `shortener/tests/test_utils.py`

| 測試案例 | 目標 |
|----------|------|
| `test_generate_short_code_from_id_format` | 驗證短碼格式（8 字元以上） |
| `test_generate_short_code_from_id_deterministic` | 驗證相同 ID 產生相同短碼 |
| `test_generate_short_code_from_id_unique` | 驗證不同 ID 產生不同短碼 |
| `test_decode_short_code_roundtrip` | 驗證編碼/解碼往返 |
| `test_decode_short_code_invalid` | 驗證無效短碼解碼返回 None |

#### `shortener/tests/test_og_parser.py`

| 測試類別 | 測試案例 |
|----------|----------|
| `TestURLSecurityValidation` | URL 安全驗證（http/https 允許、localhost/私有 IP 阻擋、file/ftp 協議阻擋） |
| `TestFetchOGData` | OG 資料抓取（成功、超時、解析錯誤、SSRF 阻擋、內容截斷、重定向到私有 IP 阻擋） |
| `TestOGDataClass` | OGData dataclass 驗證（is_empty 判斷） |

#### `shortener/tests/test_url_validation.py`

| 測試類別 | 測試案例 |
|----------|----------|
| `TestValidateUrlScheme` | URL 協議驗證（http/https 允許、javascript/data/ftp/file/vbscript 拒絕） |
| `TestShortenUrlViewXssProtection` | XSS 防護整合測試 |

### Ⅱ. 整合與 API 測試 (Integration & API Tests)

專注於測試 API 端點的行為，使用 JWT 認證。

#### `shortener/tests/test_api.py`

| 測試案例 | 目標 |
|----------|------|
| `test_authenticated_user_can_create_link` | JWT 認證用戶可建立短網址 |
| `test_unauthenticated_user_cannot_create_link` | 未認證用戶無法建立短網址 |
| `test_create_link_with_invalid_url` | 無效 URL 返回驗證錯誤 |
| `test_create_link_with_expires_at` | 支援過期時間設定 |
| `test_create_link_without_expires_at` | 無過期時間則為永久 |
| `test_user_link_limit_*` | 連結數量限制（1000 個） |
| `test_delete_link_api_*` | 連結刪除 API（成功、權限拒絕、不存在、未認證） |

#### `shortener/tests/test_api_preview.py`

| 測試類別 | 測試案例 |
|----------|----------|
| `TestShortenWithPreview` | 建立短網址時自動抓取 OG 預覽（成功、失敗時仍創建連結） |
| `TestRefreshPreview` | 手動刷新 OG 預覽（擁有者可刷新、非擁有者被拒絕） |
| `TestGetLinkDetail` | 取得連結詳情（擁有者可查看、非擁有者被拒絕、不存在返回 404） |

#### `shortener/tests/test_qr_api.py`

| 測試案例 | 目標 |
|----------|------|
| `test_get_qr_code_default_size` | 預設尺寸（256px） |
| `test_get_qr_code_custom_size` | 自訂尺寸（128/256/512px） |
| `test_get_qr_code_invalid_size` | 無效尺寸返回 400 |
| `test_get_qr_code_custom_colors` | 自訂顏色（十六進位格式） |
| `test_get_qr_code_invalid_color_format` | 無效顏色格式返回 400 |
| `test_get_qr_code_expired_link` | 過期連結返回 410 |
| `test_get_qr_code_not_found` | 不存在連結返回 404 |

### Ⅲ. 視圖測試 (View Tests)

專注於模擬使用者從瀏覽器發出的請求，使用 Django Session 認證。

#### `shortener/tests/test_views.py`

| 測試類別 | 測試案例 |
|----------|----------|
| 首頁 | `test_home_view`、`test_home_view_with_session_data` |
| 儀表板 | `test_dashboard_view_*`（認證、未認證） |
| 重定向 | `test_redirect_view_*`（有效、無效、過期） |
| 建立短網址 | `test_shorten_url_*`（GET、POST 認證/未認證、空 URL） |
| 註冊 | `test_register_view_*`（GET、POST 成功/失敗） |
| 分頁 | `test_dashboard_pagination_*`（第一頁、第二頁、無效頁碼、超出範圍） |
| 連結限制 | `test_user_link_limit_*`（達到上限、未達上限）、`test_anonymous_user_no_link_limit` |
| 連結刪除 | `test_delete_link_*`（成功、權限拒絕、不存在、未認證、GET 請求重定向） |

#### `theme/tests/test_ui_flows.py`

| 測試案例 | 目標 |
|----------|------|
| `test_login_logout_flow` | 登入登出流程 |
| `test_dashboard_shows_only_user_links` | 儀表板只顯示當前用戶的連結 |

## 4. Fixtures 架構 (`conftest.py`)

### 基礎 Fixtures
- `client` - Django TestClient
- `db` - 資料庫存取（pytest-django 自動提供）

### 用戶 Fixtures
- `test_user` - 通用測試用戶
- `authenticated_user` - Django Session 認證用戶
- `other_user` - 另一個用戶（權限測試）

### 認證 Fixtures
- `authenticated_client` - Session 認證客戶端（視圖測試）
- `ninja_authenticated_client` - JWT 認證客戶端（API 測試）

### 設定 Fixtures
- `small_link_limit` - 小型連結限制（測試用，設為 3）
- `reset_ninja_registry` - 自動清理 Ninja 註冊表

## 5. 測試檔案結構

```cmd
ninja_shortener/
├── pytest.ini                        # Pytest 設定
├── shortener/
│   └── tests/
│       ├── __init__.py
│       ├── conftest.py               # 共用 Fixtures
│       ├── test_api.py               # API 端點測試（含認證要求、自訂 slug 驗證）
│       ├── test_api_keys.py          # API Key 認證與管理頁
│       ├── test_api_list.py          # 連結列表 API（分頁、N+1 查詢）
│       ├── test_api_preview.py       # OG 預覽 API 測試
│       ├── test_async_preview.py     # 背景 OG 抓取與輪詢端點
│       ├── test_click_analytics.py   # 點擊事件記錄與統計
│       ├── test_migrations.py        # Model 與 migration 一致性
│       ├── test_models.py            # Link / ClickEvent / ApiKey 模型測試
│       ├── test_models_preview.py    # LinkPreview 模型測試
│       ├── test_og_parser.py         # OG 解析器、SSRF 防護、重定向
│       ├── test_qr_api.py            # QR Code API 與產生器
│       ├── test_services.py          # Service 層（建立連結、預覽寫入）
│       ├── test_throttling.py        # 流量限制
│       ├── test_url_validation.py    # URL / slug 驗證
│       ├── test_urls.py              # 對外網址契約
│       ├── test_utils.py             # 工具函數測試
│       └── test_views.py             # 視圖測試（含登入保護、表單各分支）
└── theme/
    └── tests/
        ├── __init__.py
        └── test_ui_flows.py          # UI 流程測試
```

## 6. 如何執行測試

### 使用 Docker（推薦）

```bash
docker compose --profile testing up
```

或在運行中的容器內執行：

```bash
docker compose exec django-ninja pytest --cov=. -v
```

### 本地執行

```bash
# 執行所有測試
pytest --cov=.

# 執行特定測試檔案
pytest shortener/tests/test_api.py -v

# 執行特定測試案例
pytest shortener/tests/test_api.py::test_authenticated_user_can_create_link -v

# 生成 HTML 覆蓋率報告
pytest --cov=. --cov-report=html
```

測試報告會生成在 `htmlcov/index.html` 中。

## 7. 安全測試覆蓋

| 安全項目 | 測試位置 |
|----------|----------|
| SSRF 防護 | `test_og_parser.py::TestURLSecurityValidation`、`TestFetchOGData` |
| URL 協議驗證（XSS 防護） | `test_url_validation.py` |
| 權限檢查 | `test_api.py::test_delete_link_api_permission_denied`、`test_views.py::test_delete_link_permission_denied` |
| JWT 認證 | `test_api.py::test_unauthenticated_user_cannot_create_link` |
| 連結數量限制 | `test_api.py::test_user_link_limit_*`、`test_views.py::test_user_link_limit_*` |
| 登入保護 | `test_views.py::test_login_required_views_redirect_anonymous` |
| API 認證要求 | `test_api.py::test_authenticated_endpoints_reject_anonymous` |

## 8. 變異測試

除了覆蓋率，另以變異測試檢驗測試是否真的「抓得到錯」：對應用程式碼注入 2,435 個小錯誤，
看測試能殺死多少。結果、補強內容與剩餘存活者的分析見 [MUTATION_TESTING.md](MUTATION_TESTING.md)，
工具與重跑方式見 [scripts/mutation/README.md](scripts/mutation/README.md)。
