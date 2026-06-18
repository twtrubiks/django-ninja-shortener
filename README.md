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
* **安全防護**：SSRF 防護、URL 協議驗證、CSRF 保護、TOCTOU 競態條件防護。
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
* **測試**：[Pytest](https://github.com/twtrubiks/django_pytest_tutorial)（118 個測試案例，94% 覆蓋率）
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

* Python 3.12
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
├── docker-compose.yml
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
│   ├── og_parser.py          # Open Graph 資料抓取（含 SSRF 防護）
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
* **快取層**：使用 Redis 快取熱門連結和 OG 預覽資料。
* **API 速率限制**：實作 rate limiting 防止濫用。

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
