# Shorty 瀏覽器擴充套件（Chrome / Manifest V3）

一鍵縮短當前分頁網址並自動複製，對應 ROADMAP 第四層的 popup-only MVP。

## 功能

- 縮短當前分頁網址，結果自動複製到剪貼簿
- 輸入任意網址生成短網址（可自訂 slug）
- 顯示最近 5 筆連結與點擊數，可一鍵複製

## 安裝（開發模式）

1. 開啟 `chrome://extensions/`，右上角開啟「開發人員模式」
2. 點「載入未封裝項目」，選擇本目錄（`extension/`）
3. 登入短網址網站，至導覽列「API Keys」頁面建立一把金鑰
4. 在擴充套件的設定頁填入伺服器網址與 API Key，按「儲存並測試連線」
   （localhost / 127.0.0.1 已預授權免確認；其他網域會跳出網站存取權限請求，需允許）

## 技術備註

- 認證走長效 API Key（`Authorization: Bearer sk_...`），不用處理 JWT 過期換發
- API 呼叫來自擴充套件頁面，搭配 host permission 即不受 CORS 限制，後端無需設定 CORS
- 相容其他 Chromium 系瀏覽器（Edge / Brave 等）
