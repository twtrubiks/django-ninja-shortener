// Shorty 設定頁：儲存伺服器網址與 API Key
// 儲存前向使用者要求該網域的 host permission（MV3 之下有權限的
// cross-origin fetch 不受 CORS 限制，後端無需另設 CORS）

const $ = (id) => document.getElementById(id);

function showStatus(message, type) {
  const el = $('status');
  el.textContent = message;
  el.className = type;
}

function normalizeBaseUrl(raw) {
  const url = new URL(raw); // 格式錯誤時丟 TypeError
  if (!/^https?:$/.test(url.protocol)) {
    throw new TypeError('僅支援 http / https 網址');
  }
  return url;
}

async function save() {
  const btn = $('save');
  btn.disabled = true;
  try {
    let url;
    try {
      url = normalizeBaseUrl($('base-url').value.trim());
    } catch (e) {
      showStatus('伺服器網址格式不正確，請輸入完整網址（含 https://）', 'error');
      return;
    }
    const baseUrl = url.origin; // fetch 用，保留 port、去掉路徑與結尾斜線

    // 欄位留空時沿用已儲存的金鑰（只改伺服器網址不必重貼）
    const stored = await chrome.storage.local.get(['apiKey']);
    const apiKey = $('api-key').value.trim() || stored.apiKey || '';
    if (!apiKey.startsWith('sk_')) {
      showStatus('API Key 格式不正確（應以 sk_ 開頭）', 'error');
      return;
    }

    // 權限 pattern 不含 port：不含 port 的 match pattern 本就涵蓋該主機
    // 所有 port，且含 port 的請求在 Chrome 可能不顯示提示直接回絕
    const originPattern = `${url.protocol}//${url.hostname}/*`;

    // 已授權（如 manifest 預授權的 localhost）就不再打擾使用者
    let granted = await chrome.permissions.contains({ origins: [originPattern] });
    if (!granted) {
      try {
        granted = await chrome.permissions.request({ origins: [originPattern] });
      } catch (e) {
        showStatus(`權限請求失敗：${e.message}`, 'error');
        return;
      }
    }
    if (!granted) {
      showStatus('未授予網站存取權限，擴充套件將無法連線到伺服器', 'error');
      return;
    }

    // 測試連線：打一次列表端點驗證網址與金鑰
    let res;
    try {
      res = await fetch(`${baseUrl}/api/links?page=1&page_size=1`, {
        headers: { Authorization: `Bearer ${apiKey}` },
      });
    } catch (e) {
      showStatus('無法連線到伺服器，請確認網址正確且服務運作中', 'error');
      return;
    }
    if (res.status === 401) {
      showStatus('API Key 無效或已被撤銷，請至網站「API Keys」頁面確認', 'error');
      return;
    }
    if (!res.ok) {
      showStatus(`伺服器回應異常（HTTP ${res.status}）`, 'error');
      return;
    }

    await chrome.storage.local.set({ baseUrl, apiKey });

    // 同步畫面狀態：清空輸入框、更新「已儲存金鑰」提示
    $('api-key').value = '';
    const hint = $('key-hint');
    hint.textContent = `已儲存金鑰：${apiKey.slice(0, 8)}…（重新填入可更換）`;
    hint.classList.remove('hidden');

    showStatus('連線成功，設定已儲存！', 'success');
  } finally {
    btn.disabled = false;
  }
}

async function init() {
  const { baseUrl, apiKey } = await chrome.storage.local.get(['baseUrl', 'apiKey']);
  if (baseUrl) $('base-url').value = baseUrl;
  if (apiKey) {
    const hint = $('key-hint');
    hint.textContent = `已儲存金鑰：${apiKey.slice(0, 8)}…（重新填入可更換）`;
    hint.classList.remove('hidden');
  }
  $('save').addEventListener('click', save);
}

document.addEventListener('DOMContentLoaded', init);
