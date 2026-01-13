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
def reset_ninja_registry():
    """
    自動運行的 fixture，清除 Ninja 的內部註冊表以防止 ConfigError。

    這個 fixture 會在每個測試前後自動運行，確保測試之間不會互相影響。
    """
    yield
    # 測試結束後清理註冊表
    if hasattr(NinjaAPI, "_registry"):
        NinjaAPI._registry = []


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
