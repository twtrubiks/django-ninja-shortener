import pytest
from django.contrib.auth.models import User
from ninja import NinjaAPI
from ninja.testing import TestClient
from shortener.models import Link
from ninja_shortener.api import api
from ninja_jwt.tokens import RefreshToken

@pytest.fixture(autouse=True)
def reset_ninja_registry():
    """
    This fixture automatically runs for each test.
    It clears Ninja's internal registry before each test run to prevent ConfigError.
    """
    yield
    # Teardown: clear the registry after the test has run
    if hasattr(NinjaAPI, "_registry"):
        NinjaAPI._registry = []

@pytest.mark.django_db
def test_authenticated_user_can_create_link():
    """
    目標: 已登入的使用者可以成功建立短網址。
    步驟:
    1. 創建並認證一個使用者。
    2. 使用 TestClient 發送一個帶有 original_url 的 POST 請求到 /api/shorten。
    3. HTTP 狀態碼為 200。
    4. 資料庫中已創建對應的 Link 記錄。
    5. 回應的 JSON 內容符合預期。
    """
    # 1. 創建使用者
    user = User.objects.create_user(username="testuser", password="password123")
    refresh = RefreshToken.for_user(user)
    token = str(refresh.access_token)

    client = TestClient(api, headers={"Authorization": f"Bearer {token}"})

    # 2. 發送 POST 請求
    original_url = "https://docs.pytest.org/en/latest/"
    response = client.post("/shorten", json={"original_url": original_url})

    # 3. HTTP 狀態碼
    assert response.status_code == 200

    # 4. 資料庫中已創建記錄
    assert Link.objects.filter(original_url=original_url).exists()
    link = Link.objects.get(original_url=original_url)
    assert link.owner == user

    # 5. 回應的 JSON 內容
    response_json = response.json()
    assert response_json["original_url"] == original_url
    assert "short_code" in response_json
    # Note: The owner field might not be serialized as just the ID depending on the schema.
    # Let's check if the owner information is present and correct.
    # If LinkSchema serializes the owner, it might be a nested object.
    # For now, we'll assume the schema was adjusted to return the owner's ID.
    # If the test fails here, we'll need to inspect the actual response.
    assert response_json["owner"] == user.id
    assert response_json["click_count"] == 0


@pytest.mark.django_db
def test_unauthenticated_user_cannot_create_link():
    """
    目標: 未登入的使用者無法建立短網址。
    步驟:
    1. 不進行認證，直接使用 TestClient 發送 POST 請求。
    2. HTTP 狀態碼為 401 (Unauthorized)。
    """
    client = TestClient(api)
    original_url = "https://www.example.com"
    response = client.post("/shorten", json={"original_url": original_url})

    # 因為端點受 JWTAuth 保護，未經授權的請求應返回 401
    assert response.status_code == 401
    assert not Link.objects.filter(original_url=original_url).exists()


@pytest.mark.django_db
def test_create_link_with_invalid_url():
    """
    目標: 提交無效的 URL 時，應返回驗證錯誤。
    步驟:
    1. 認證一個使用者。
    2. 發送一個 original_url 為無效格式的 POST 請求。
    3. HTTP 狀態碼為 422 (Unprocessable Entity)。
    """
    user = User.objects.create_user(username="testuser_invalid", password="password123")
    refresh = RefreshToken.for_user(user)
    token = str(refresh.access_token)
    client = TestClient(api, headers={"Authorization": f"Bearer {token}"})

    # 發送一個無效的 URL
    response = client.post("/shorten", json={"original_url": "not-a-valid-url"})

    # Django Ninja 對於請求 Schema 驗證失敗，通常返回 422
    assert response.status_code == 422
