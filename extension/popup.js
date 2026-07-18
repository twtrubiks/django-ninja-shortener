// Shorty popup：縮短當前分頁 / 任意網址，顯示最近連結
// 認證走長效 API Key（設定頁貼一次即可），API 見 shortener/api.py

const state = { baseUrl: '', apiKey: '' };

const $ = (id) => document.getElementById(id);

// ---------- API ----------

class ApiError extends Error {
  constructor(status, detail) {
    super(detail || `HTTP ${status}`);
    this.status = status;
    this.detail = detail;
  }
}

async function api(path, options = {}) {
  let res;
  try {
    res = await fetch(state.baseUrl + path, {
      ...options,
      headers: {
        Authorization: `Bearer ${state.apiKey}`,
        ...(options.body ? { 'Content-Type': 'application/json' } : {}),
      },
    });
  } catch (e) {
    throw new ApiError(0, '無法連線到伺服器，請檢查設定頁的網址與網站權限');
  }

  if (!res.ok) {
    let detail = '';
    try {
      detail = (await res.json()).detail || '';
    } catch (e) { /* 非 JSON 回應 */ }
    throw new ApiError(res.status, detail);
  }
  return res.json();
}

function friendlyError(err) {
  if (err.status === 401) return 'API Key 無效或已被撤銷，請至設定頁更新';
  if (err.status === 422) return validationMessage(err.detail);
  if (err.status === 429) return '操作過於頻繁，請稍後再試';
  return err.detail || err.message || '發生未知錯誤';
}

// ninja 的 422 detail 為陣列：[{loc: [..., '欄位名'], msg: 'Value error, 訊息'}]
// 後端自訂驗證的訊息是中文（可直接顯示）；英文的是 pydantic 內建，改用通用訊息
function validationMessage(detail) {
  const first = Array.isArray(detail) && detail.length ? detail[0] : null;
  if (!first) return '輸入格式不正確';

  const field = Array.isArray(first.loc) ? first.loc[first.loc.length - 1] : '';
  const msg = (first.msg || '').replace(/^Value error,\s*/, '');
  const isReadable = /[^\x00-\x7f]/.test(msg);

  if (field === 'custom_slug') return isReadable ? `自訂 slug：${msg}` : '自訂 slug 格式不正確';
  if (field === 'original_url') return isReadable ? msg : '網址格式不正確';
  return isReadable ? msg : '輸入格式不正確';
}

// ---------- UI helpers ----------

function showStatus(message, type) {
  const el = $('status');
  el.textContent = message;
  el.className = type;
}

function clearStatus() {
  $('status').textContent = '';
  $('status').className = 'hidden';
}

async function showResult(shortUrl, { autoCopy }) {
  const link = $('result-link');
  link.textContent = shortUrl;
  link.href = shortUrl;
  $('result').classList.remove('hidden');

  if (autoCopy) {
    try {
      await navigator.clipboard.writeText(shortUrl);
      showStatus('已建立並複製到剪貼簿！', 'success');
    } catch (e) {
      showStatus('已建立，但自動複製失敗，請手動複製', 'error');
    }
  }
}

function shortUrlFor(code) {
  return `${state.baseUrl}/${code}`;
}

async function withBusy(button, fn) {
  button.disabled = true;
  clearStatus();
  try {
    await fn();
  } catch (err) {
    showStatus(friendlyError(err), 'error');
  } finally {
    button.disabled = false;
  }
}

// ---------- 功能 ----------

async function shorten(originalUrl, customSlug) {
  const payload = { original_url: originalUrl };
  if (customSlug) payload.custom_slug = customSlug;

  const data = await api('/api/shorten', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
  await showResult(shortUrlFor(data.short_code), { autoCopy: true });
  await loadRecent();
}

async function getCurrentTabUrl() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return tab && tab.url ? tab.url : '';
}

async function loadRecent() {
  const list = $('recent-list');
  const data = await api('/api/links?page=1&page_size=5');

  list.textContent = '';
  $('recent-empty').classList.toggle('hidden', data.items.length > 0);

  for (const item of data.items) {
    const li = document.createElement('li');

    const info = document.createElement('div');
    info.className = 'recent-info';

    const shortLink = document.createElement('a');
    shortLink.className = 'recent-short';
    shortLink.textContent = `/${item.short_code}`;
    shortLink.href = shortUrlFor(item.short_code);
    shortLink.target = '_blank';
    shortLink.rel = 'noopener';

    const original = document.createElement('div');
    original.className = 'recent-original';
    original.textContent = item.original_url;
    original.title = item.original_url;

    info.append(shortLink);
    if (item.expires_at && new Date(item.expires_at) <= new Date()) {
      const expired = document.createElement('span');
      expired.className = 'expired-badge';
      expired.textContent = '已過期';
      info.append(expired);
    }
    info.append(original);

    const clicks = document.createElement('span');
    clicks.className = 'recent-clicks';
    clicks.textContent = `${item.click_count} 次`;

    const copyBtn = document.createElement('button');
    copyBtn.className = 'copy-btn';
    copyBtn.textContent = '複製';
    copyBtn.addEventListener('click', async () => {
      await navigator.clipboard.writeText(shortUrlFor(item.short_code));
      copyBtn.textContent = '已複製';
      setTimeout(() => { copyBtn.textContent = '複製'; }, 1500);
    });

    li.append(info, clicks, copyBtn);
    list.appendChild(li);
  }
}

// ---------- 初始化 ----------

function openOptions() {
  chrome.runtime.openOptionsPage();
}

async function init() {
  $('open-options').addEventListener('click', openOptions);
  $('go-setup').addEventListener('click', openOptions);

  const { baseUrl, apiKey } = await chrome.storage.local.get(['baseUrl', 'apiKey']);
  if (!baseUrl || !apiKey) {
    $('not-configured').classList.remove('hidden');
    return;
  }
  state.baseUrl = baseUrl;
  state.apiKey = apiKey;
  $('main').classList.remove('hidden');

  // 當前分頁：只有 http(s) 網址可縮短（chrome:// 等頁面不行）
  const currentUrl = await getCurrentTabUrl();
  const shortenable = /^https?:\/\//.test(currentUrl);
  $('current-url').textContent = shortenable ? currentUrl : '（此頁面無法縮短）';
  $('current-url').title = currentUrl;
  $('shorten-current').disabled = !shortenable;

  $('shorten-current').addEventListener('click', () =>
    withBusy($('shorten-current'), () => shorten(currentUrl))
  );

  $('shorten-custom').addEventListener('click', () =>
    withBusy($('shorten-custom'), async () => {
      const url = $('custom-url').value.trim();
      const slug = $('custom-slug').value.trim();
      if (!url) {
        showStatus('請輸入要縮短的網址', 'error');
        return;
      }
      await shorten(url, slug || undefined);
    })
  );

  // Enter 直接送出（popup 沒有 form 元素）；isComposing 避免輸入法組字選字誤觸
  for (const id of ['custom-url', 'custom-slug']) {
    $(id).addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.isComposing) $('shorten-custom').click();
    });
  }

  $('copy-result').addEventListener('click', async () => {
    await navigator.clipboard.writeText($('result-link').textContent);
    showStatus('已複製到剪貼簿！', 'success');
  });

  try {
    await loadRecent();
  } catch (err) {
    showStatus(friendlyError(err), 'error');
  }
}

document.addEventListener('DOMContentLoaded', init);
