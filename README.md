# Django Ninja Shortener - 類 Bitly 短網址服務

[English Version](README_en.md)

Django、Django Ninja 和 Tailwind CSS 打造的現代化短網址服務，其設計靈感來自於 Bitly。

使用者可以註冊登入後，將網址縮短，可追蹤每個短網址的點擊次數。

本專案使用 [Cline](https://github.com/twtrubiks/mcp-vscode-cline?tab=readme-ov-file#cline) 協助完成, 可參考 [.clinerules/01_doc.md](.clinerules/01_doc.md)

## 畫面截圖

短網址頁面 (沒註冊也可以使用)

![alt tag](https://cdn.imgpile.com/f/qPDKjsy_xl.png)

如果註冊可以追蹤點擊

![alt tag](https://cdn.imgpile.com/f/4R3cy01_xl.png)

## ✨ 功能亮點

* **使用者認證**：支援使用者註冊、登入、登出。
* **建立短網址**：登入後的使用者可以為長網址產生一個獨一無二的短網址。
* **短網址重定向**：點擊短網址會將使用者重新導向至原始的長網址。
* **點擊次數追蹤**：系統會自動計算每個短網址被點擊的次數。
* **個人儀表板**：使用者可以查看自己建立的所有短網址及其點擊統計。
* **RESTful API**：提供 API 端點以程式化方式建立短網址。
* **Docker 支援**：提供 Dockerfile 和 Docker Compose 設定，簡化開發與部署流程。

## 🛠️ 技術棧

* **後端框架**：[Django](https://github.com/twtrubiks/django-tutorial)
* **API 框架**：[Django Ninja](https://github.com/twtrubiks/django_ninja_tutorial)
* **前端樣式**：[Tailwind CSS](https://tailwindcss.com/) (透過 `django-tailwind` 整合)
* **資料庫**：
  * 開發環境：SQLite (預設)
  * 生產環境：可輕鬆替換為 PostgreSQL (已在 `settings.py` 中預留設定)
* **短網址代碼**：使用 [Sqids](https://sqids.org/) 從資料庫 ID 生成（零碰撞設計）
* **測試**：[Pytest](https://github.com/twtrubiks/django_pytest_tutorial)
* **容器化**：[Docker](https://github.com/twtrubiks/docker-tutorial)

## 🚀 快速啟動 (使用 Docker, 建議用這個)

這是最推薦的啟動方式，可以確保開發環境的一致性。

**啟動步驟：**

1. **啟動服務：**

    使用 Docker Compose 一鍵啟動所有服務。

    ```bash
    docker compose up --build
    ```

    這個指令會建立 Docker 映像檔、安裝依賴、執行資料庫遷移，並啟動開發伺服器。

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
├── ninja_shortener/      # Django 專案設定
│   ├── settings.py
│   └── urls.py
├── shortener/            # 核心短網址應用
│   ├── models.py         # 資料庫模型 (Link)
│   ├── api.py            # Django Ninja API 端點
│   ├── views.py          # 頁面視圖與重定向邏輯
│   └── utils.py          # 短代碼生成工具
└── theme/                # Django 主題與模板
    ├── templates/        # HTML 模板
    └── static_src/       # Tailwind CSS 原始檔
```

## 💡 未來展望

* **切換至 PostgreSQL**：為生產環境準備更穩健的資料庫。(已完成)
* **詳細的分析儀表板**：提供更多點擊數據，如時間、來源、地理位置等。
* **自訂短網址**：允許使用者自訂短網址的代碼。
* **QR Code 產生**：為每個短網址產生對應的 QR Code。
* **非同步任務**：使用 Celery 處理耗時任務，如數據分析。

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
