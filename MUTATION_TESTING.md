# 變異測試報告（Mutation Testing）

覆蓋率只能說明「測試有執行到這行」，不能說明「這行寫錯時測試會失敗」。
變異測試會故意把程式改壞（把 `<` 改成 `<=`、刪掉一個裝飾器、把字串換掉……），
每改一處就跑一次測試：測試失敗 = 這個變異體被**殺死**；測試照樣全綠 = **存活**，
代表那段行為其實沒被任何斷言保護。

## 摘要

| | 補測試前（第一輪） | 補測試 + 修正後（最終） |
| --- | ---: | ---: |
| 測試案例 | 202 | 445 |
| 行覆蓋率（應用程式碼，不含測試 / migration） | 92% | 97% |
| 變異體 | 2,435 | 2,446 |
| 殺死 | 1,648 | 2,283 |
| 存活 | 787 | 163 |
| **變異分數** | **67.7%** | **93.3%** |

最終一輪多出的 11 個變異體來自修正程式問題時新增的程式碼（見文末）。
補測試後、修正前也以同一組 2,435 個變異體重跑過一次，分數為 93.3%（殺死 2,273、存活 162）。

- 原本覆蓋率看起來不低（README 標示 97%，只算應用程式碼為 92%），變異分數卻只有 67.7%：
  有 787 處「改壞了也沒有測試會發現」。
- 其中最嚴重的是**權限類**缺口：`/api/check-slug` 拿掉認證、三個網頁 view 拿掉
  `@login_required`、JWT 取 token 的端點整個沒註冊，現有測試全都不會失敗。
- 補了 243 個測試、修正 3 個程式問題後，剩下的 163 個存活者已逐一判讀，全部屬於等價變異、
  測試環境下無法區分的設定預設值、效能 / 文件 / 日誌類，或刻意不鎖死的可調參數（見〈剩餘存活者〉）。
- 過程中另外發現 **4 個程式問題**，已一併修正（見〈發現並已修正的程式問題〉）。

## 範圍

變異以下 14 個檔案中所有手寫的應用程式邏輯：

```
shortener/   analytics.py  api.py  auth.py  models.py  og_parser.py  ownership.py
             qr_utils.py  services.py  utils.py  validators.py  views.py
             templatetags/short_urls.py
ninja_shortener/  api.py  urls.py
```

不納入：`settings.py`（設定；生產環境專屬分支在測試中無法觸發）、migrations（自動產生）、
`admin.py` / `apps.py`（宣告式設定）、測試本身、模板與 Chrome 擴充套件（非 Python）。

## 方法

### 工具

先試了 [mutmut](https://github.com/boxed/mutmut) 3.8，但它會跳過「帶裝飾器的函式」與
「模組 / 類別層的程式碼」。在這個專案，這等於跳過：

- 所有 `@router.*` API 端點（含 `auth=`、`throttle=` 設定）與 `@login_required` view
- pydantic `@field_validator`、Model 的 `@property`
- Schema / Model 欄位定義、模組常數

第一輪 2,435 個變異體中有 1,366 個（56%）位於 mutmut 不會變異的區域；第一輪 787 個存活者有 468 個落在這裡，
上述權限類缺口全在其中。因此改用自建的
[`scripts/mutation/mutation_test.py`](scripts/mutation/mutation_test.py)：沿用 mutmut 3.8 的變異運算子，
但變異整個檔案，並加上四種對 Django 專案特別重要的運算子。

| 運算子 | 例子 | 來源 |
| --- | --- | --- |
| number | `MAX_URL_LENGTH = 2000` → `2001` | mutmut |
| string | `'home'` → `'XXhomeXX'` / 大小寫互換 | mutmut |
| name | `True` ↔ `False` | mutmut |
| swap_op | `<` → `<=`、`and` → `or`、`+` → `-` | mutmut |
| keywords | `in` ↔ `not in`、`is` ↔ `is not` | mutmut |
| assignment | `x = expr` → `x = None` | mutmut |
| arg_removal | `f(a, b)` → `f(None, b)` / `f(b)` | mutmut |
| if_exp | `a if c else b` → 強制走其中一邊 | mutmut |
| remove_unary_ops / augmented_assignment / string 方法互換 | `not x` → `x`、`+=` → `=`、`lower` ↔ `upper` | mutmut |
| **decorator_remove** | 拿掉 `@login_required`、`@field_validator(...)` | 新增 |
| **stmt_delete** | 刪掉 `link.delete()`、`enqueue_preview_fetch(link)` | 新增 |
| **if_negate** | `if error:` → `if not (error):` | 新增 |
| **return_none** | `return redirect(...)` → `return None` | 新增 |

不變異：import、型別註記、docstring、`logger.*` 呼叫（同 PIT 預設避開 logging 的做法）、
`len()` / `isinstance()`（同 mutmut）。

### 執行

- 12 個平行 worker，各自一份專案副本與獨立的 Postgres 測試庫（`--reuse-db`）。
- 先以 `--cov-context=test` 記錄每一行被哪些測試執行到。函式主體內的變異只跑相關測試；
  模組 / 類別層的變異（import 時就生效）跑全套。
- 只跑部分測試就存活的變異體，最後**一律用全套測試複驗**。三輪分別複驗了 341、99、100 個，
  結果全部仍然存活 —— 測試挑選沒有造成任何假存活。
- 測試改用 MD5 密碼雜湊加速（`create_user` 是原本測試時間的大宗），不影響被測邏輯。
- 補測試前後各跑一輪；兩者在未改動原始碼的部分使用相同的變異體（逐一比對內容相同），分數可直接比較。

重跑方式見 [scripts/mutation/README.md](scripts/mutation/README.md)。

## 結果

### 各檔案

| 檔案 | 變異體（第一輪 → 最終） | 補測試前 | 最終 |
| --- | ---: | ---: | ---: |
| `shortener/views.py` | 556 → 558 | 67.4% | **93.5%** |
| `shortener/api.py` | 443 | 82.8% | **91.6%** |
| `shortener/og_parser.py` | 379 → 381 | 54.9% | **87.1%** |
| `shortener/analytics.py` | 321 | 67.6% | **96.9%** |
| `shortener/models.py` | 291 | 48.1% | **99.7%** |
| `ninja_shortener/urls.py` | 171 | 76.0% | **94.2%** |
| `shortener/services.py` | 88 | 83.0% | **95.5%** |
| `shortener/validators.py` | 48 → 55 | 68.8% | **96.4%** |
| `shortener/qr_utils.py` | 37 | 45.9% | **81.1%** |
| `shortener/ownership.py` | 36 | 91.7% | **97.2%** |
| `shortener/auth.py` | 30 | 90.0% | **93.3%** |
| `shortener/utils.py` | 12 | 91.7% | **91.7%** |
| `ninja_shortener/api.py` | 12 | 66.7% | **75.0%** |
| `shortener/templatetags/short_urls.py` | 11 | 81.8% | **100.0%** |
| **合計** | **2,435 → 2,446** | **67.7%** | **93.3%** |

### 各運算子

| 運算子 | 變異體（第一輪 → 最終） | 補測試前 | 最終 |
| --- | ---: | ---: | ---: |
| arg_removal | 972 → 978 | 68.4% | **92.9%** |
| string | 715 → 716 | 62.7% | **94.4%** |
| assignment | 214 → 215 | 90.7% | **97.7%** |
| number | 99 | 32.3% | **81.8%** |
| return_none | 97 | 79.4% | **99.0%** |
| if_negate | 68 | 92.6% | **97.1%** |
| swap_op | 67 → 68 | 67.2% | **89.7%** |
| name | 51 | 33.3% | **92.2%** |
| stmt_delete | 47 → 48 | 68.1% | **97.9%** |
| if_exp | 36 | 50.0% | **69.4%** |
| keywords | 28 | 96.4% | **100.0%** |
| decorator_remove | 27 | 70.4% | **85.2%** |
| remove_unary_ops | 8 → 9 | 100.0% | **100.0%** |
| symmetric_string_methods_swap | 4 | 75.0% | **100.0%** |
| augmented_assignment | 2 | 0.0% | **50.0%** |

## 第一輪找到的測試缺口與補強

以下依嚴重程度排列。每一項都附上「存活的代表變異體」與對應補上的測試。

### 1. 權限與認證（最嚴重）

| 存活的變異體 | 代表的風險 | 補上的測試 |
| --- | --- | --- |
| `/check-slug/{slug}` 的 `auth=ApiKeyOrJWTAuth()` → `auth=None` | 匿名者可列舉所有已使用的 slug | `test_api.py::test_authenticated_endpoints_reject_anonymous`（6 個需登入端點逐一驗證 401） |
| `refresh_preview_view`、`create_api_key_view`、`delete_api_key_view` 拿掉 `@login_required` | 匿名請求直接進入 view（建立 / 撤銷金鑰會 500） | `test_views.py::test_login_required_views_redirect_anonymous`（8 個需登入頁面） |
| `api.register_controllers(NinjaJWTDefaultController)` 被刪除 | `/api/token/pair` 消失，JWT 客戶端全部失效 | `test_urls.py::test_jwt_token_pair_flow` |
| `@field_validator('custom_slug')` 被移除 | API 可用保留字（`admin`）或非法格式當 slug | `test_api.py::test_shorten_invalid_custom_slug_returns_422` |
| `@field_validator('dark', 'light')` → 只驗 `dark` | `light` 參數不驗證 | `test_qr_api.py::test_get_qr_code_invalid_light_color` |
| 拿掉 `/shorten`、`/refresh-preview` 等端點的 `throttle=[...]` | 只有 `GET /links/{code}` 驗過限流 | `test_throttling.py::test_every_authenticated_endpoint_is_throttled` 等 |
| `AnonRateThrottle(None)` | 速率退回套件預設，`DJANGO_*_THROTTLE_RATE` 設定失效 | `test_throttling.py::test_throttle_rates_follow_settings` |

### 2. 整條路徑沒有測試

覆蓋率報告其實已經指出，變異測試把它們量化成「這裡有幾十個錯誤不會被發現」：

- **網頁表單**的過期時間、自訂 slug、slug 撞名、短碼生成失敗（`views.py` 約 60 個存活者）
- **`refresh_preview_view`** 整個 view（22 個）
- API Key 頁面的 GET 分支、名稱預設 / 截斷、prefix
- `og_parser` 的錯誤處理：缺 `Location`、超過重定向次數、相對路徑重定向、連線錯誤、未預期例外、
  缺主機名、無法解析的 URL、連接埠
- `validate_custom_slug` 沒有任何直接的單元測試（長度上限、連續連字號等訊息）

### 3. 測試「引用被測常數」形成套套邏輯

`test_day_bucketing_uses_display_timezone` 用 `DISPLAY_TIMEZONE` 計算期望值，
所以把常數改成 `None` 時，期望值跟著變，測試永遠通過。同類情況還有 `MAX_URL_LENGTH`
（邊界測試用 `MAX_URL_LENGTH + 前綴`）、`USER_AGENT`。

補強：`test_day_bucketing_independent_of_time_zone_setting` 寫死「UTC 1/10 20:00 = 台北 1/11」，
並把 `TIME_ZONE` 改成 UTC 驗證統計不受全域設定影響（正是程式碼註解宣稱的設計意圖）；
`TestUrlLengthBoundary` 寫死 2000 / 2001。

### 4. 只有一筆資料的測試

`get_object_or_404(Link, short_code=short_code)` 把查詢條件拿掉，在「資料庫只有一筆連結」的測試裡
照樣取到同一筆。轉址、QR Code、擁有權檢查、撤銷 API Key 都有這個問題。
補強：多筆資料時要取到 / 刪到正確那一筆（`test_redirect_view_targets_requested_link`、
`test_delete_link_deletes_only_target`、`test_delete_api_key_only_target` 等）。

### 5. Model 欄位與 migration 不同步

測試資料庫由 migration 建立，Model 上的 `max_length`、`null`、`unique`、`db_index`、
`related_name`、索引……改了也不影響任何測試：`models.py` 第一輪有 151 個存活者，
其中 147 個是欄位 / `Meta` 定義。新增 `test_migrations.py`（`makemigrations --check`）後這 147 個**全部殺死**，
`models.py` 最終只剩 1 個等價變異。

### 6. 對外網址契約

網頁測試多用 `reverse()`、API 測試多用 Ninja `TestClient`（直接呼叫 api 物件、不經 `urls.py`），
所以把 `path('api/', ...)` 改成別的路徑也不會失敗 —— 但 Chrome 擴充套件寫死了 `/api/shorten`。
新增 `test_urls.py` 釘住所有路徑。

### 7. 其他

- **裝置分類**：`_MOBILE_OS_FAMILIES` 等清單的每一項都沒有對應測試 → 以 ua-parser 實測的 UA 建立對照表。
- **N+1 查詢**：拿掉 `select_related('preview')` 不影響結果 → 驗證查詢數不隨連結數增加。
- **QR Code**：`buffer.seek(0)` 被刪掉會回傳空 body、自訂顏色沒套用都測不出來 → 檢查 PNG 標頭與調色盤。
- **OG 抓取**：`_read_capped_body` 串接 chunk 時夾雜分隔字元、超過上限後仍繼續讀取 → 精確比對內容與讀取次數。
- **錯誤訊息**：原本多用 `'上限' in msg` 比對，改為精確比對（訊息是使用者看得到的行為）。

## 剩餘存活者

最終仍有 163 個存活者，已逐一判讀並分類如下（完整清單與 diff 由工具產生的 `report.md` 提供）：

| 類別 | 數量 | 說明 / 例子 |
| --- | ---: | --- |
| 等價變異（逐條判讀） | 67 | 程式行為完全相同，不可能被任何測試殺死。例：`Paginator.get_page(None)` 與 `get_page(1)` 相同；segno 不分大小寫解析色碼；`_safe_get_from_metadata` 對空 list 取 `[0]` 拋出的例外會被 except 接住 |
| 測試環境下等價：settings 已定義，getattr 預設值不會被用到 | 36 | `getattr(settings, 'USER_MAX_LINKS', 1000)` 的 `1000` 改成別的值：settings 已定義此值，預設值只在設定缺漏時才會用到。其中限流速率的設定鍵名若打錯，會退回與 settings 預設相同的值，只有在用環境變數改過速率時才看得出差別；限流器在 import 時就建立，測試無法於執行期替換設定來區分 |
| API 文件 / 回應 schema（OpenAPI 呈現，行為等價） | 15 | `Router(tags=...)`、`response=Schema` 只影響 OpenAPI 文件與序列化方式，回應內容相同；pydantic 會自動把 `@field_validator` 包成 classmethod |
| 開發環境專用（DEBUG static、__reload__、未使用的 urls_namespace） | 13 | `if settings.DEBUG:` 的靜態檔路由、`django_browser_reload` 路徑、程式中沒有用到的 `urls_namespace` |
| metadata_parser 參數（對合法 HTML 結果相同） | 10 | `search_head_only`、`support_malformed`、`strategy`、`url` 對格式正確的 HTML 結果相同（`search_head_only` 的註解也說明是效能考量） |
| 效能（select_related / queryset 只影響查詢次數） | 8 | `select_related('preview')` 拿掉後結果相同、只是多查詢。列表與 dashboard 已用「查詢數不隨筆數增加」測試保護，單筆查詢（詳情頁、API Key 認證）多一次查詢屬可接受 |
| 只影響日誌或內部旗標（truncated、chunk_size） | 7 | `_read_capped_body` 的 `truncated` 旗標只決定是否寫 log；`chunk_size` 只影響分塊大小 |
| 可調參數（測試刻意引用常數，改值屬設定調整而非錯誤） | 6 | `MAX_REDIRECTS`、`MAX_RESPONSE_BYTES`、`DASHBOARD_ITEMS_PER_PAGE`、`Sqids(min_length=8)`。測試引用常數本身，改值時測試跟著調整——這是刻意的，避免測試變成鎖死設定值的「變更偵測器」 |
| 防禦縱深：is_global 兜底後，個別 IP 條件互相涵蓋 | 1 | 修正 SSRF 時加上的 `or not ip.is_global` 會擋下所有非公網位址，於是 `is_private`、`is_reserved` 等個別條件被改壞時仍會由它兜底（反之亦然）。這正是多層檢查的用意，不是測試缺口 |

**結論：剩餘存活者中沒有代表真實測試缺口的項目。**

## 發現並已修正的程式問題

變異測試本身只檢驗測試品質；以下四個問題是補測試、盤點時實測確認的程式錯誤，已一併修正
（第 1–3 項：commit `修正：未登入導向 404、SSRF 漏擋 CGNAT 位址、網頁表單接受格式錯誤網址`；
第 4 項：commit `修正：重新抓取預覽改為只接受 POST，納入 CSRF 保護`）。
每項都有對應測試，並確認「把修正還原時測試會失敗」。

### 1. 未登入時導向不存在的登入頁（404）

`settings.py` 沒有設定 `LOGIN_URL`，`@login_required` 會導向 Django 預設的 `/accounts/login/`，
但專案的登入頁在 `/login/`：

```
修正前：GET /dashboard/ → 302 /accounts/login/?next=/dashboard/ → 404
修正後：GET /dashboard/ → 302 /login/?next=/dashboard/           → 登入頁，登入後回到 /dashboard/
```

- 修正：`settings.py` 加上 `LOGIN_URL = 'login'`。
- 測試：既有四處把 `/accounts/login/` 寫成預期值的斷言改為專案登入頁；新增
  `test_login_redirect_lands_on_login_page_and_returns`（導向的頁面真的存在，且登入後回到原頁面）。

### 2. SSRF 防護沒擋 `100.64.0.0/10`

`_is_ip_blocked` 原本檢查 `is_private / is_loopback / is_link_local / is_reserved / is_multicast / is_unspecified`，
但 CGNAT 共享位址 `100.64.0.0/10` 在 Python 的 `ipaddress` 中以上皆非，因此被放行 ——
阿里雲的 metadata 服務就在 `100.100.100.200`。

- 修正：在既有條件後加上 `or not ip.is_global`（不是公網位址就擋）。不能只用 `not ip.is_global`
  取代既有條件：multicast（例如 `224.0.0.1`）的 `is_global` 是 True，仍需要 `is_multicast` 那一條。
- 測試：`TestIsIpBlocked` 加入 `100.64.0.1`、`100.100.100.200` 與其 IPv4-mapped 形式；
  新增 `test_blocks_public_hostname_resolving_to_cgnat_metadata`。

### 3. 網頁表單接受格式錯誤的網址

API 以 pydantic `HttpUrl` 驗證，網頁表單卻只檢查協議，`http://`、`http://exa mple.com`
都能建立短網址（`Link.objects.create` 不會執行 Model 欄位的驗證器）。

- 修正：`validators.py` 新增 `validate_url_format`（Django `URLValidator`，只允許 http / https），
  網頁表單在協議檢查之後套用；錯誤訊息為「請輸入有效的網址」。協議錯誤仍先由原本的驗證回報
  （訊息會指出是哪個協議）。
- 測試：`test_shorten_url_rejects_malformed_url`、`test_shorten_url_accepts_valid_url_forms`
  （含連接埠、IDN 網域、大寫協議），以及 `TestValidateUrlFormat`。

### 4. 重新抓取預覽可由 GET 觸發（CSRF）

dashboard 上的「重新抓取 / 抓取預覽」原本是 `<a href="/links/<code>/refresh/">` 連結，
view 不檢查 HTTP 方法就把預覽重設為 pending 並排入背景抓取。Django 的 CSRF 保護只檢查
POST 等會改變狀態的方法，因此其他網站只要放一張
`<img src="https://<站台>/links/<code>/refresh/">`，登入中的擁有者瀏覽該頁時就會在不知情下觸發。
短碼本來就是公開分享的，攻擊者不難取得。影響有限（只能重抓擁有者自己的連結），
但「有副作用的操作走 GET」本身就是錯的，同專案的刪除連結、建立 / 撤銷 API Key 都已只接受 POST。

```
修正前：GET  /links/<code>/refresh/（他站 <img> 也能觸發） → 預覽重設、排入背景抓取
修正後：GET  /links/<code>/refresh/                      → 302 /dashboard/，不做任何事
        POST /links/<code>/refresh/（未帶 CSRF token）    → 403
```

- 修正：view 只接受 POST，GET 一律導回 dashboard；`_preview_card.html` 的三處連結改為帶
  `{% csrf_token %}` 的 POST 表單（輪詢端點以 `render_to_string(..., request=request)` 產生卡片，
  回傳的 HTML 裡 token 同樣有效）。API 端的 `POST /api/links/{code}/refresh-preview` 以 header 帶
  JWT / API Key 認證、不靠 cookie，不受 CSRF 影響，維持不變。
- 測試：`test_refresh_preview_view_get_does_nothing`（GET 不排入抓取、預覽狀態不變）、
  `test_refresh_preview_view_requires_csrf_token`（`enforce_csrf_checks=True`，未帶 token 回 403），
  以及 `test_refresh_control_is_post_form_with_csrf`（失敗、成功無資料、尚無預覽三種卡片都是帶 token 的
  POST 表單，不再有 GET 連結）；原本以 GET 呼叫的測試改用 POST。

### 附註：裝置分類的已知限制

UA 含 `Mobile` 的 Android 平板（例如 Galaxy Tab `SM-T530`、Kindle Fire HDX）會被歸為手機。
這是 UA 啟發式判斷的先天限制，記錄於此供參考。
