import pytest
from django.contrib.auth.models import User
from ninja import NinjaAPI
from ninja.testing import TestClient
from ninja_jwt.tokens import RefreshToken

from shortener.models import Link
from ninja_shortener.api import api


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

@pytest.mark.django_db
def test_authenticated_user_can_create_link():
    """
    測試已認證用戶可以透過 API 成功建立短網址。

    驗證：
    - HTTP 狀態碼為 200
    - 資料庫中創建了對應的 Link 記錄
    - 回應的 JSON 內容正確
    - Link 記錄的擁有者正確設置
    """
    # 創建用戶並生成 JWT token
    user = User.objects.create_user(username="testuser", password="password123")
    refresh = RefreshToken.for_user(user)
    token = str(refresh.access_token)

    client = TestClient(api, headers={"Authorization": f"Bearer {token}"})

    # 發送 POST 請求建立短網址
    original_url = "https://docs.pytest.org/en/latest/"
    response = client.post("/shorten", json={"original_url": original_url})

    # 驗證 HTTP 狀態碼
    assert response.status_code == 200

    # 驗證資料庫記錄
    assert Link.objects.filter(original_url=original_url).exists()
    link = Link.objects.get(original_url=original_url)
    assert link.owner == user

    # 驗證回應內容
    response_json = response.json()
    assert response_json["original_url"] == original_url
    assert "short_code" in response_json
    assert response_json["owner"] == user.id
    assert response_json["click_count"] == 0


@pytest.mark.django_db
def test_unauthenticated_user_cannot_create_link():
    """
    測試未認證用戶無法透過 API 建立短網址。

    驗證：
    - HTTP 狀態碼為 401 (Unauthorized)
    - 資料庫中沒有創建任何記錄
    """
    client = TestClient(api)
    original_url = "https://www.example.com"
    response = client.post("/shorten", json={"original_url": original_url})

    # 端點受 JWTAuth 保護，未授權請求應返回 401
    assert response.status_code == 401
    assert not Link.objects.filter(original_url=original_url).exists()


@pytest.mark.django_db
def test_create_link_with_invalid_url():
    """
    測試提交無效 URL 時的錯誤處理。

    驗證：
    - HTTP 狀態碼為 422 (Unprocessable Entity)
    - 資料庫中沒有創建任何記錄
    """
    user = User.objects.create_user(username="testuser_invalid", password="password123")
    refresh = RefreshToken.for_user(user)
    token = str(refresh.access_token)
    client = TestClient(api, headers={"Authorization": f"Bearer {token}"})

    # 發送無效的 URL
    response = client.post("/shorten", json={"original_url": "not-a-valid-url"})

    # Django Ninja 對於 Schema 驗證失敗通常返回 422
    assert response.status_code == 422
    assert not Link.objects.filter(original_url="not-a-valid-url").exists()
