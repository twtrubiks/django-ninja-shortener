# Django Ninja Shortener - Pytest 測試計畫

本文件旨在為 `django-ninja-shortener` 專案規劃一套完整的自動化測試策略。我們將使用 `Pytest` 及其生態系 (特別是 `pytest-django`) 來確保應用程式的穩定性、可靠性與可維護性。

## 1. 測試環境與設定

- **測試框架:** `pytest`, `pytest-django`
- **測試資料庫:** 為了隔離與速度，測試將在一個獨立的記憶體中 (in-memory) 的 SQLite 資料庫或一個獨立的測試 PostgreSQL 資料庫上運行。這可以在 `settings.py` 中進行配置。
- **測試工具:** Django Ninja 提供了 `TestClient` (`from ninja.testing import TestClient`)，專門用於測試 Ninja API 端點，比 Django 原生的 `Client` 更方便。

## 2. 測試分類與範疇

將測試分為三個主要類別：

### Ⅰ. 單元測試 (Unit Tests)

專注於測試單一元件（模型、函式）的正確性，不涉及外部依賴（如資料庫、API）。

- **`shortener/tests/test_models.py`**
  - `test_link_model_creation`:
    - **目標:** 驗證 `Link` 模型是否能成功創建。
    - **步驟:** 創建一個 `User` 和一個 `Link` 實例，其 `original_url`, `short_code`, `owner` 等欄位值是否正確。
  - `test_short_code_uniqueness`:
    - **目標:** 驗證 `short_code` 欄位的唯一性約束 (`unique=True`) 是否生效。
    - **步驟:** 嘗試創建兩個具有相同 `short_code` 的 `Link` 實例，預期第二次創建時會拋出 `IntegrityError`。
  - `test_link_model_string_representation`:
    - **目標:** 驗證 `Link` 模型的 `__str__` 方法是否返回預期的格式。
    - **步驟:** 創建 `Link` 實例，`str(link_instance)` 的結果。

- **`shortener/tests/test_utils.py`** (假設短代碼生成邏輯被抽離到 `utils.py`)
  - `test_short_code_generator_format`:
    - **目標:** 驗證生成的短代碼格式、長度是否符合預期。
    - **步驟:** 調用生成函數，使用正則表達式或長度判斷來驗證結果。

### Ⅱ. 整合與 API 測試 (Integration & API Tests)

專注於測試不同元件協同工作的正確性，特別是 API 端點的行為。

- **`shortener/tests/test_api.py`**
  - **`POST /api/shorten` (建立短網址)**
    - `test_authenticated_user_can_create_link`:
      - **目標:** 已登入的使用者可以成功建立短網址。
      - **步驟:**
        1. 創建並認證一個使用者。
        2. 使用 `TestClient` 發送一個帶有 `original_url` 的 POST 請求到 `/api/shorten`。
        3. TTP 狀態碼為 `200` 或 `201`。
        4. 資料庫中已創建對應的 `Link` 記錄。
        5. 回應的 JSON 內容符合預期。
    - `test_unauthenticated_user_cannot_create_link`:
      - **目標:** 未登入的使用者無法建立短網址。
      - **步驟:**
        1. 不進行認證，直接使用 `TestClient` 發送 POST 請求。
        2. HTTP 狀態碼為 `401` (Unauthorized) 或 `403` (Forbidden)。
    - `test_create_link_with_invalid_url`:
      - **目標:** 提交無效的 URL 時，應返回驗證錯誤。
      - **步驟:**
        1. 認證一個使用者。
        2. 發送一個 `original_url` 為無效格式 (例如 "not-a-url") 的 POST 請求。
        3. HTTP 狀態碼為 `422` (Unprocessable Entity)。

### Ⅲ. 端對端與視圖測試 (E2E & View Tests)

專注於模擬使用者從瀏覽器發出的請求，測試完整的請求-回應週期，包括重定向和頁面渲染。

- **`shortener/tests/test_views.py`**
  - **`GET /{short_code}` (重定向邏輯)**
    - `test_valid_short_code_redirects_and_increments_click_count`:
      - **目標:** 存取有效的短網址會重定向到原始網址，並增加點擊次數。
      - **步驟:**
        1. 在資料庫中預先創建一個 `Link` 實例，`click_count` 為 0。
        2. 使用 Django 的 `Client` 存取 `/{short_code}`。
        3. HTTP 狀態碼為 `302` (Found)。
        4. 回應的 `Location` 標頭是正確的 `original_url`。
        5. 從資料庫中重新獲取該 `Link` 實例，其 `click_count` 已變為 1。
    - `test_invalid_short_code_returns_404`:
      - **目標:** 存取不存在的短代碼應返回 404 錯誤。
      - **步驟:**
        1. 使用 Django 的 `Client` 存取一個隨機且不存在的 short code。
        2. HTTP 狀態碼為 `404` (Not Found)。

- **`theme/tests/test_ui_flows.py`**
  - **使用者認證流程**
    - `test_login_logout_flow`:
      - **目標:** 測試使用者登入和登出功能。
      - **步驟:**
        1. 創建使用者。
        2. POST 請求到登入頁面，登入成功 (例如，重定向到儀表板)。
        3. GET 請求到登出 URL，登出成功 (例如，重定向到首頁)。
  - **儀表板 (`/dashboard`)**
    - `test_dashboard_shows_only_user_links`:
      - **目標:** 儀表板只應顯示當前登入使用者的短網址。
      - **步驟:**
        1. 創建兩個使用者 (User A, User B)。
        2. 為 User A 和 User B 分別創建幾個 `Link` 實例。
        3. 以 User A 的身份登入並存取儀表板。
        4. 回應的 HTML 內容中包含 User A 的連結，且不包含 User B 的連結。

## 3. 建議的測試檔案結構

為了保持組織性，建議將所有測試相關檔案放在各個 app 的 `tests` 目錄下。

```cmd
ninja_shortener/
├── shortener/
│   ├── migrations/
│   ├── templates/
│   ├── __init__.py
│   ├── api.py
│   ├── models.py
│   ├── views.py
│   └── tests/
│       ├── __init__.py
│       ├── test_api.py
│       ├── test_models.py
│       └── test_views.py
└── theme/
    ├── ...
    └── tests/
        ├── __init__.py
        └── test_ui_flows.py
```

## 4. 如何執行測試

在專案根目錄下（包含 `manage.py` 的地方），執行以下命令：

```bash
pytest -s
```

Pytest 會自動發現並執行所有 `test_*.py` 或 `*_test.py` 檔案中的測試函式。
