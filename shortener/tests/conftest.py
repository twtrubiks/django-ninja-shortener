"""
中央 Pytest Fixtures 管理

此檔案集中管理所有測試共用的 fixtures，避免重複定義。

Fixtures 分類：
- 基礎 fixtures: client, db
- 用戶 fixtures: test_user, authenticated_user, other_user
- 認證 fixtures:
  - authenticated_client: Django Session 認證（視圖測試用）
  - ninja_authenticated_client: JWT Token 認證（API 測試用）
- 清理 fixtures: reset_ninja_registry
"""

import pytest
from django.contrib.auth.models import User
from django.test import Client
from ninja import NinjaAPI


# =============================================================================
# 基礎 Fixtures
# =============================================================================


@pytest.fixture
def client():
    """提供測試用的 Django 測試客戶端。"""
    return Client()


# =============================================================================
# 清理 Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def local_memory_cache(settings):
    """
    測試一律改用記憶體快取後端，並在每個測試前後清空。

    正式環境用 DatabaseCache（需 `createcachetable` 建表），但 pytest 的測試資料庫
    不含該表；且 API throttling 的請求計數存於快取，需在測試間清空以確保彼此隔離
    （避免前一個測試累積的計數讓後續測試誤觸 429）。
    """
    settings.CACHES = {
        'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'},
    }
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


@pytest.fixture(autouse=True)
def reset_ninja_registry():
    """
    自動運行的 fixture，清除 Ninja 的內部註冊表以防止 ConfigError。

    這個 fixture 會在每個測試前後自動運行，確保測試之間不會互相影響。
    """
    yield
    # 測試結束後清理註冊表
    if hasattr(NinjaAPI, "_registry"):
        NinjaAPI._registry = []


@pytest.fixture(autouse=True)
def run_q_tasks_sync(monkeypatch):
    """
    測試時讓排入的背景任務同步執行，免啟動 qcluster / broker，
    並預設樁住 OG 抓取以避免真實對外網路請求。

    - async_task → 直接同步呼叫 run_preview_fetch，使「建立 → 抓取 → 寫入
      preview」在單一請求內完成、便於斷言。
    - fetch_og_data → 預設回傳空 OGData（不連網）。需要特定 OG 結果的測試可
      自行 patch shortener.services.fetch_og_data 覆蓋；需要驗證「只入列、不
      執行」的測試可在內層 patch async_task 覆蓋。
    """
    from shortener import services
    from shortener.og_parser import OGData

    def _run_inline(func, *args, **kwargs):
        return services.run_preview_fetch(*args)

    monkeypatch.setattr(services, 'async_task', _run_inline)
    monkeypatch.setattr(services, 'fetch_og_data', lambda *args, **kwargs: OGData())


# =============================================================================
# 用戶 Fixtures
# =============================================================================


@pytest.fixture
def test_user(db):
    """建立測試用戶（通用）"""
    return User.objects.create_user(
        username='testuser',
        password='password123'
    )


@pytest.fixture
def authenticated_user(db):
    """建立已認證用戶（Django Session 用）"""
    return User.objects.create_user(
        username='testuser',
        password='password123'
    )


@pytest.fixture
def other_user(db):
    """建立另一個測試用戶（權限測試用）"""
    return User.objects.create_user(
        username='otheruser',
        password='password456'
    )


# =============================================================================
# 認證 Fixtures
# =============================================================================


@pytest.fixture
def authenticated_client(client, authenticated_user):
    """
    已登入的 Django 測試客戶端（Session 認證）

    適用於：Django 視圖測試
    """
    client.login(username='testuser', password='password123')
    return client


@pytest.fixture
def ninja_authenticated_client(test_user):
    """
    已認證的 Ninja TestClient（JWT 認證）

    適用於：Django Ninja API 測試
    """
    from ninja.testing import TestClient
    from ninja_jwt.tokens import RefreshToken
    from ninja_shortener.api import api

    refresh = RefreshToken.for_user(test_user)
    token = str(refresh.access_token)
    return TestClient(api, headers={'Authorization': f'Bearer {token}'})


# =============================================================================
# 設定 Fixtures
# =============================================================================


@pytest.fixture
def small_link_limit(settings):
    """
    測試用小型連結上限

    適用於：測試連結數量限制功能，避免建立過多測試資料
    """
    settings.USER_MAX_LINKS = 5
    return 5
