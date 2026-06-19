# Django Ninja Shortener - 類 Bitly 短網址服務

[English Version](README_en.md)

Django、Django Ninja 和 Tailwind CSS 打造的現代化短網址服務，其設計靈感來自於 Bitly。

使用者可以註冊登入後，將網址縮短，可追蹤每個短網址的點擊次數。

~~本專案使用 [Cline](https://github.com/twtrubiks/mcp-vscode-cline?tab=readme-ov-file#cline) 協助完成, 可參考 [.clinerules/01_doc.md](.clinerules/01_doc.md)~~ 目前改用 [Claude Code](https://docs.anthropic.com/en/docs/claude-code) 開發

## 畫面截圖

短網址頁面 (沒註冊也可以使用)

![alt tag](https://cdn.imgpile.com/f/qPDKjsy_xl.png)

如果註冊可以有更多功能, 像是 點擊次數, 設定過期日期, 自定義網址, QRCODE

![alt tag](https://cdn.imgpile.com/f/0oOzE2J_xl.png)

![alt tag](https://cdn.imgpile.com/f/NdaNWkE_xl.png)

## ✨ 功能亮點

* **使用者認證**：支援使用者註冊、登入、登出，使用 JWT 進行 API 認證。
* **建立短網址**：支援匿名用戶建立短網址，登入用戶享有更多功能。
* **自訂短網址 Slug**：登入用戶可自訂短網址後綴（3-50 字元），支援格式驗證與保留字過濾。
* **短網址過期機制**：可設定短網址過期時間（1 小時、1 天、7 天、30 天或永久）。
* **短網址重定向**：點擊短網址會將使用者重新導向至原始的長網址，使用原子性更新防止競態條件。
* **點擊次數追蹤**：系統會自動計算每個短網址被點擊的次數。
* **Open Graph 預覽**：以 Django-Q 背景**非同步**抓取目標網頁的 OG 資料（標題、描述、圖片），建立短網址不被目標網站拖慢；儀表板顯示骨架載入並自動輪詢更新，亦支援手動重新抓取。
* **QR Code 生成**：為每個短網址生成 QR Code，支援多種尺寸（128/256/512px）和自訂顏色。
* **個人儀表板**：分頁顯示用戶的所有短網址及其統計資料，支援連結刪除功能。
* **連結數量限制**：每位登入用戶最多可建立 1000 個連結。
* **RESTful API**：完整的 API 端點，使用 JWT 認證。
* **安全防護**：SSRF 防護（解析實際 IP 後以 `ipaddress` 物件化檢查，涵蓋十進位 / hex / octal / IPv6-mapped 等編碼繞過，並對每個重定向目標重新驗證；DNS rebinding 列為已知限制）、OG 抓取回應大小上限（串流讀取並對解壓後位元組設限，防解壓縮炸彈 / 超大 body 撐爆背景 worker）、URL 協議驗證、CSRF 保護、TOCTOU 競態條件防護、生產環境 HTTPS 強化（`DEBUG=False` 時自動啟用 HSTS、HTTPS 轉址與 `Secure` cookie）、API 流量限制（throttling，防濫用 / DoS）。
* **設定環境變數化**：`SECRET_KEY`、`DEBUG`、`ALLOWED_HOSTS`、資料庫帳密皆可由環境變數注入；生產環境（`DEBUG=False`）若仍沿用內建預設金鑰會直接拒絕啟動。詳見下方〈環境變數與生產環境設定〉一節。
* **Docker 支援**：提供 Dockerfile 和 Docker Compose 設定，簡化開發與部署流程。

## 🛠️ 技術棧

* **後端框架**：[Django](https://github.com/twtrubiks/django-tutorial)
* **API 框架**：[Django Ninja](https://github.com/twtrubiks/django_ninja_tutorial)
* **前端樣式**：[Tailwind CSS](https://tailwindcss.com/) (透過 `django-tailwind` 整合)
* **資料庫**：
  * 預設：PostgreSQL（透過 Docker Compose）
  * 備用：SQLite（已在 `settings.py` 中預留設定）
* **短網址代碼**：使用 [Sqids](https://sqids.org/) 從資料庫 ID 生成（零碰撞設計）
* **QR Code**：使用 [Segno](https://segno.readthedocs.io/) 生成 QR Code
* **OG 解析**：使用 [metadata_parser](https://github.com/jvanasco/metadata_parser) 解析 Open Graph 資料
* **非同步任務**：使用 [Django-Q2](https://django-q2.readthedocs.io/) 背景處理 OG 抓取（以 PostgreSQL ORM 作為 broker，免額外的 Redis）
* **測試**：[Pytest](https://github.com/twtrubiks/django_pytest_tutorial)（147 個測試案例，96% 覆蓋率）
* **容器化**：[Docker](https://github.com/twtrubiks/docker-tutorial)

## 🚀 快速啟動 (使用 Docker, 建議用這個)

這是最推薦的啟動方式，可以確保開發環境的一致性。

**啟動步驟：**

1. **啟動服務：**

    使用 Docker Compose 一鍵啟動所有服務。

    ```bash
    docker compose up --build
    ```

    這個指令會建立 Docker 映像檔、安裝依賴、執行資料庫遷移，並啟動所有服務：Django 開發伺服器、PostgreSQL、Tailwind 編譯，以及 `qcluster`（Django-Q 背景 worker，負責非同步抓取 OG 預覽）。

2. **建立超級使用者 (可選)：**

    若要存取 Django Admin，請在另一個終端機視窗執行：

    ```bash
    docker compose exec django-ninja python manage.py createsuperuser
    ```

3. **訪問應用程式：**

    * **網站首頁**：[http://localhost:8000](http://localhost:8000)

    * **API 文件 (Swagger UI)**：[http://localhost:8000/api/docs](http://localhost:8000/api/docs)

## 🔧 本地開發 (不使用 Docker)

如果你偏好在本地直接設定環境。

**先決條件：**

* Python 3.13
* Node.js and npm (用於 Tailwind CSS)

**設定步驟：**

1. **建立並啟用虛擬環境：**

    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
    ```

2. **安裝 Python 依賴：**

    ```bash
    pip install -r requirements.txt
    ```

3. **安裝並設定 Tailwind CSS：**

    `django-tailwind` 會處理大部分設定。

    ```bash
    python manage.py tailwind install
    ```

    可參考 [https://django-tailwind.readthedocs.io/en/latest/installation.html](https://django-tailwind.readthedocs.io/en/latest/installation.html)

4. **執行資料庫遷移：**

    ```bash
    python manage.py migrate
    ```

5. **建立超級使用者 (可選)：**

    ```bash
    python manage.py createsuperuser
    ```

6. **啟動開發伺服器：**

    你需要同時啟動 Django 伺服器和 Tailwind CSS 的編譯程序。

    ```bash
    python manage.py runserver
    ```

    在另一個終端機視窗中：

    ```bash
    python manage.py tailwind start
    ```

    再開一個終端機視窗，啟動 Django-Q 背景 worker（負責非同步抓取 OG 預覽）：

    ```bash
    python manage.py qcluster
    ```

    > 若未啟動 worker，OG 預覽會一直停留在「處理中」（pending）狀態。

7. **訪問應用程式：**

    * **網站首頁**：[http://localhost:8000](http://localhost:8000)

    * **API 文件 (Swagger UI)**：[http://localhost:8000/api/docs](http://localhost:8000/api/docs)

## 🔐 環境變數與生產環境設定

機敏設定不再寫死在 `settings.py`，改由環境變數注入。專案根目錄提供 `.env.example` 作為範本，**未設定任何環境變數時會沿用與開發一致的預設值**（因此 Docker 與本地都能直接跑起來；`docker compose` 會自動讀取根目錄的 `.env`）。

```bash
cp .env.example .env   # 之後依環境調整 .env 內容
```

| 環境變數 | 用途 | 預設值 |
| --- | --- | --- |
| `DJANGO_SECRET_KEY` | Django 金鑰，同時用於 JWT 簽章 | 內建 insecure 開發金鑰 |
| `DJANGO_DEBUG` | 是否開啟 Debug 模式 | `True` |
| `DJANGO_ALLOWED_HOSTS` | 允許的主機名（逗號分隔） | `*` |
| `DJANGO_SECURE_SSL_REDIRECT` | （`DEBUG=False` 時）HTTP 自動轉址 HTTPS | `True` |
| `DJANGO_SECURE_HSTS_SECONDS` | （`DEBUG=False` 時）HSTS 有效秒數 | `31536000` |
| `DJANGO_TRUST_PROXY_SSL_HEADER` | （`DEBUG=False` 時）信任反向代理 `X-Forwarded-Proto` 辨識 HTTPS | `False` |
| `DJANGO_ANON_THROTTLE_RATE` | 公開 API 端點流量上限（按 IP，格式「次數/週期」） | `30/min` |
| `DJANGO_USER_THROTTLE_RATE` | 已認證 API 端點流量上限（按使用者） | `60/min` |
| `SITE_ADDRESS` | （`docker-compose.prod.yml`）Caddy 對外位址，設網域即啟用自動 HTTPS | `:80` |
| `WEB_CONCURRENCY` | （`docker-compose.prod.yml`）gunicorn worker 數量 | `3` |
| `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` | 資料庫名稱 / 帳號 / 密碼 | `postgres` / `myuser` / `password123` |
| `POSTGRES_HOST` / `POSTGRES_PORT` | 資料庫位址 / 連接埠 | `django-postgres` / `5432` |

**上生產環境前務必：**

* 將 `DJANGO_SECRET_KEY` 換成隨機長字串（可用 `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"` 生成）。此金鑰同時是 JWT 簽章金鑰，外洩等同可偽造任意使用者的 token。
* 設定 `DJANGO_DEBUG=False`。為避免誤用，當 `DEBUG=False` 卻仍沿用內建預設金鑰時，應用程式會直接拒絕啟動。
* 將 `DJANGO_ALLOWED_HOSTS` 設為實際網域（例如 `example.com,www.example.com`）。
* 使用強資料庫密碼，且不要將實際的 `.env` 提交進版控（`.gitignore` 已忽略 `.env`，僅保留 `.env.example`）。
* **HTTPS 站台**：維持 `DJANGO_DEBUG=False` 即會自動啟用 HSTS、`SECURE_SSL_REDIRECT`、以及 session / CSRF 的 `Secure` cookie。若 TLS 由 nginx / Cloudflare 終結，依情況調整 `DJANGO_SECURE_SSL_REDIRECT` 與 `DJANGO_TRUST_PROXY_SSL_HEADER`。最後以 `python manage.py check --deploy` 驗收。

## 🚢 生產環境部署 (gunicorn + Caddy)

開發用的 `docker compose up` 採 `runserver`（含熱重載），方便開發但**不適合上線**。正式部署請改用 `docker-compose.prod.yml`，它以生產級組態啟動：

* **gunicorn**（WSGI）取代 `runserver`。
* **Caddy** 作為前層：自動 HTTPS（Let's Encrypt）、反向代理至 gunicorn、並直接服務靜態檔。
* `migrate` / `createcachetable` / `collectstatic` 由專屬的**一次性 `migrate` 服務**集中執行一次；web / qcluster 以 `depends_on: service_completed_successfully` 等它跑完才啟動，從結構上避免多容器開機各自 `migrate` 的並發競態。
* 靜態檔以 `ManifestStaticFilesStorage` 產生帶內容雜湊的檔名（cache busting），交由 Caddy 長期快取。
* Tailwind CSS 於映像建置階段預先 build，生產映像自帶靜態資產。

啟動步驟：

```bash
cp .env.example .env
# 編輯 .env，務必設定（不可沿用開發預設值）：
#   DJANGO_SECRET_KEY=<隨機長字串>
#   DJANGO_DEBUG=False
#   DJANGO_ALLOWED_HOSTS=example.com,www.example.com
#   SITE_ADDRESS=example.com        # Caddy 自動申請 / 續期 TLS（需 80/443 對外、DNS 指向本機）
#   POSTGRES_PASSWORD=<強密碼>

docker compose -p ninja-prod -f docker-compose.prod.yml up -d --build
```

* **`-p ninja-prod` 是專案名稱**（`--project-name`），會當前綴套在容器 / 網路 / 資料卷上（如 `ninja-prod_db-data`）。不帶 `-p` 時專案名預設為**目錄名**，會與開發用 `docker compose up` 共用同一個 `db-data` 資料卷而互相污染（例如 Postgres 密碼以先啟動者為準，導致另一套認證失敗）。用 `-p ninja-prod` 讓生產與開發資料卷**完全分家**。
  * ⚠️ 用了 `-p ninja-prod` 後，**之後每一條 prod 指令都要帶**（`down` / `logs` / `ps` / `exec` …），否則會操作到另一個專案。
* **本機冒煙測試**（不申請憑證）：保留 `SITE_ADDRESS=:80`，以純 HTTP 連 `http://localhost`。
* `WEB_CONCURRENCY` 調整 gunicorn worker 數（建議 `2 * CPU + 1`）。
* TLS 由 Caddy 終結後以 HTTP 回源，故生產預設 `DJANGO_SECURE_SSL_REDIRECT=False`（http→https 轉址交給 Caddy，避免迴圈）、`DJANGO_TRUST_PROXY_SSL_HEADER=True`（信任 Caddy 帶上的 `X-Forwarded-Proto`）。
* 驗收：`docker compose -p ninja-prod -f docker-compose.prod.yml exec web python manage.py check --deploy`。
* 若想改用 nginx 等其他前層，或讓 Django 自行服務靜態檔（無前層），可改以 WhiteNoise 服務 `/static/`。

## 🧪 運行測試

本專案使用 `pytest` 進行測試，並計算測試覆蓋率。

測試的 Plan 可參考 [TESTING_PLAN.md](TESTING_PLAN.md)

* **使用 Docker 運行測試：**

    ```bash
    docker compose --profile testing up
    ```

    測試報告會生成在 `htmlcov/index.html` 中。

* **在本地運行測試：**

    ```bash
    # 確保已安裝開發依賴
    pytest --cov=. --cov-report=html
    ```

![alt tag](https://cdn.imgpile.com/f/UZnApNQ_xl.png)

## 📄 API 端點

API 提供了程式化的方式來與短網址服務互動。所有 API 端點都在 `/api/` 路徑下。

> 所有 API 端點皆套用流量限制（throttling）：公開的 QR 端點按來源 IP、已認證端點按使用者計數，超出上限回應 `429 Too Many Requests`。速率可由 `DJANGO_ANON_THROTTLE_RATE` / `DJANGO_USER_THROTTLE_RATE` 調整。

建議直接到 **API 文件 (Swagger UI)**：[http://localhost:8000/api/docs](http://localhost:8000/api/docs)

![alt tag](https://cdn.imgpile.com/f/Foa4p5C_md.png)

使用 [Ninja JWT](https://github.com/twtrubiks/django_ninja_tutorial/tree/main?tab=readme-ov-file#ninja-jwt), 先呼叫 `/api/token/pair` 依照密號密碼, 取得你的 token

![alt tag](https://cdn.imgpile.com/f/84ABFA4_xl.png)

然後把 token 貼到右上角, 就可以呼叫 api 了

![alt tag](https://cdn.imgpile.com/f/aCbUddW_md.png)

## 📂 專案結構

```cmd
ninja_shortener/
├── Dockerfile
├── docker-compose.yml        # 開發用（runserver + 熱重載）
├── docker-compose.prod.yml   # 生產用（gunicorn + Caddy）
├── Caddyfile                 # Caddy 前層設定（自動 HTTPS / 反向代理 / 靜態檔）
├── entrypoint.sh             # 開機：migrate（+ 生產時 collectstatic）
├── manage.py
├── requirements.txt
├── pytest.ini                # Pytest 設定
├── ninja_shortener/          # Django 專案設定
│   ├── settings.py           # Django 設定（JWT、資料庫、應用註冊）
│   ├── urls.py               # URL 路由配置
│   └── api.py                # API 整合點（NinjaExtraAPI）
├── shortener/                # 核心短網址應用
│   ├── models.py             # 資料庫模型（Link、LinkPreview）
│   ├── api.py                # Django Ninja API 端點
│   ├── views.py              # 頁面視圖、重定向、預覽狀態端點
│   ├── services.py           # 共用業務邏輯（建立連結、OG 抓取與背景任務）
│   ├── utils.py              # 短碼生成工具（Sqids）
│   ├── validators.py         # 驗證器（URL、自訂 slug）
│   ├── og_parser.py          # Open Graph 資料抓取（含 SSRF 防護、回應大小上限）
│   ├── qr_utils.py           # QR Code 生成工具
│   └── tests/                # 測試套件
│       ├── conftest.py       # pytest fixtures 集中管理
│       ├── test_api.py       # API 端點測試
│       ├── test_models.py    # 資料模型測試
│       ├── test_views.py     # 視圖測試
│       └── ...               # 其他測試檔案
└── theme/                    # Django 主題與模板
    ├── templates/            # HTML 模板
    │   ├── home.html         # 首頁（短網址建立）
    │   ├── dashboard.html    # 儀表板（用戶連結管理、OG 預覽輪詢）
    │   ├── partials/         # 共用局部模板（OG 預覽卡片）
    │   └── expired.html      # 過期連結頁面
    └── static_src/           # Tailwind CSS 原始檔
```

## 💡 未來展望

* **切換至 PostgreSQL**：為生產環境準備更穩健的資料庫。✅ 已完成
* **詳細的分析儀表板**：提供更多點擊數據，如時間、來源、地理位置等。
* **自訂短網址**：允許使用者自訂短網址的代碼。✅ 已完成
* **QR Code 產生**：為每個短網址產生對應的 QR Code。✅ 已完成
* **OG 抓取異步化**：將 Open Graph 資料抓取改為異步處理（Django-Q2，以 PostgreSQL 為 broker），避免阻塞 API 請求。✅ 已完成
* **API 速率限制**：以 django-ninja 內建 throttling 防止濫用，公開端點按 IP、已認證端點按使用者；計數預設存於 DatabaseCache（免額外服務），速率可由環境變數調整。✅ 已完成
* **生產環境部署**：以 gunicorn 取代 runserver、Caddy 前層（自動 HTTPS + 反向代理 + 服務靜態檔）、移除開機 `makemigrations`、`DEBUG=False` 時自動 `collectstatic`；見 `docker-compose.prod.yml`。✅ 已完成
* **快取層**：將 throttling 計數與熱門連結 / OG 預覽資料改用 Redis 快取，獲得更佳效能與多程序間一致性。

## Donation

文章都是我自己研究內化後原創，如果有幫助到您，也想鼓勵我的話，歡迎請我喝一杯咖啡 :laughing:

綠界科技ECPAY ( 不需註冊會員 )

![alt tag](https://payment.ecpay.com.tw/Upload/QRCode/201906/QRCode_672351b8-5ab3-42dd-9c7c-c24c3e6a10a0.png)

[贊助者付款](http://bit.ly/2F7Jrha)

歐付寶 ( 需註冊會員 )

![alt tag](https://i.imgur.com/LRct9xa.png)

[贊助者付款](https://payment.opay.tw/Broadcaster/Donate/9E47FDEF85ABE383A0F5FC6A218606F8)

## 贊助名單

[贊助名單](https://github.com/twtrubiks/Thank-you-for-donate)

## License

MIT license
