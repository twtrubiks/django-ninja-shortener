from datetime import datetime, timedelta, timezone as tz
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from ninja.testing import TestClient
from ninja_jwt.tokens import RefreshToken

from ninja_shortener.api import api
from shortener.models import Link
from shortener.services import ShortCodeGenerationError


# Fixture: reset_ninja_registry 已移至 conftest.py


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


@pytest.mark.django_db
def test_create_link_with_expires_at():
    """
    測試建立帶有過期時間的短網址。

    驗證：
    - HTTP 狀態碼為 200
    - 資料庫中的 expires_at 欄位正確設置
    - 回應的 JSON 包含 expires_at
    """
    user = User.objects.create_user(username="testuser_expires", password="password123")
    refresh = RefreshToken.for_user(user)
    token = str(refresh.access_token)
    client = TestClient(api, headers={"Authorization": f"Bearer {token}"})

    original_url = "https://example.com/expiring"
    expires_at = (datetime.now(tz.utc) + timedelta(days=7)).isoformat()

    response = client.post(
        "/shorten",
        json={"original_url": original_url, "expires_at": expires_at}
    )

    assert response.status_code == 200

    # 驗證資料庫記錄
    link = Link.objects.get(original_url=original_url)
    assert link.expires_at is not None

    # 驗證回應內容
    response_json = response.json()
    assert response_json["expires_at"] is not None


@pytest.mark.django_db
def test_create_link_without_expires_at():
    """
    測試建立不帶過期時間的短網址（向後相容）。

    驗證：
    - HTTP 狀態碼為 200
    - 資料庫中的 expires_at 欄位為 None
    """
    user = User.objects.create_user(username="testuser_no_exp", password="password123")
    refresh = RefreshToken.for_user(user)
    token = str(refresh.access_token)
    client = TestClient(api, headers={"Authorization": f"Bearer {token}"})

    original_url = "https://example.com/permanent"

    response = client.post("/shorten", json={"original_url": original_url})

    assert response.status_code == 200

    # 驗證資料庫記錄
    link = Link.objects.get(original_url=original_url)
    assert link.expires_at is None


# ===== User Link Limit Tests (API) =====

@pytest.mark.django_db
def test_user_link_limit_reached_api(test_user, ninja_authenticated_client, small_link_limit):
    """
    測試 API - 用戶達到連結上限時回傳 403。

    驗證：
    - HTTP 狀態碼為 403
    - 回應包含正確的錯誤訊息和數量資訊
    """
    # 建立連結達到上限
    for i in range(small_link_limit):
        Link.objects.create(
            original_url=f"https://example{i}.com",
            short_code=f"limit{i:03d}",
            owner=test_user
        )

    # 嘗試建立新連結
    response = ninja_authenticated_client.post(
        "/shorten",
        json={"original_url": "https://newsite.com"}
    )

    assert response.status_code == 403
    response_json = response.json()
    assert 'detail' in response_json
    assert '上限' in response_json['detail']
    assert response_json['current_count'] == small_link_limit
    assert response_json['max_links'] == small_link_limit


@pytest.mark.django_db
def test_user_link_limit_not_reached_api(test_user, ninja_authenticated_client, small_link_limit):
    """
    測試 API - 未達上限時可以正常建立連結。

    驗證：
    - HTTP 狀態碼為 200
    - 連結成功建立
    """
    # 建立少於上限的連結
    for i in range(small_link_limit - 1):
        Link.objects.create(
            original_url=f"https://example{i}.com",
            short_code=f"under{i:03d}",
            owner=test_user
        )

    # 應該可以建立新連結
    response = ninja_authenticated_client.post(
        "/shorten",
        json={"original_url": "https://newsite.com"}
    )

    assert response.status_code == 200
    response_json = response.json()
    assert response_json['original_url'] == "https://newsite.com/"
    assert 'short_code' in response_json

    # 驗證連結已建立
    assert Link.objects.filter(owner=test_user).count() == small_link_limit


# ===== Delete Link API Tests =====

@pytest.mark.django_db
def test_delete_link_api_success(test_user, ninja_authenticated_client):
    """
    測試 API - 擁有者可以成功刪除自己的連結。

    驗證：
    - HTTP 狀態碼為 200
    - 連結已從資料庫刪除
    """
    link = Link.objects.create(
        original_url="https://example.com/api-delete",
        short_code="apidel01",
        owner=test_user
    )

    response = ninja_authenticated_client.delete(f"/links/{link.short_code}")

    assert response.status_code == 200
    response_json = response.json()
    assert '成功刪除' in response_json['detail']
    assert response_json['short_code'] == 'apidel01'
    assert not Link.objects.filter(short_code="apidel01").exists()


@pytest.mark.django_db
def test_delete_link_api_permission_denied(test_user, ninja_authenticated_client):
    """
    測試 API - 用戶無法刪除他人的連結。

    驗證：
    - HTTP 狀態碼為 403
    - 連結仍然存在
    """
    other_user = User.objects.create_user(username="apiother", password="password123")
    link = Link.objects.create(
        original_url="https://example.com/api-others",
        short_code="apioth01",
        owner=other_user
    )

    response = ninja_authenticated_client.delete(f"/links/{link.short_code}")

    assert response.status_code == 403
    response_json = response.json()
    assert '沒有權限' in response_json['detail']
    # 連結應該仍然存在
    assert Link.objects.filter(short_code="apioth01").exists()


@pytest.mark.django_db
def test_delete_link_api_not_found(ninja_authenticated_client):
    """
    測試 API - 刪除不存在的連結返回 404。
    """
    response = ninja_authenticated_client.delete("/links/notexist")
    assert response.status_code == 404


@pytest.mark.django_db
def test_delete_link_api_unauthenticated():
    """
    測試 API - 未認證用戶無法刪除連結。

    驗證：
    - HTTP 狀態碼為 401
    - 連結仍然存在
    """
    from ninja.testing import TestClient
    from ninja_shortener.api import api

    user = User.objects.create_user(username="unauthtest", password="password123")
    link = Link.objects.create(
        original_url="https://example.com/unauth",
        short_code="unauth01",
        owner=user
    )

    client = TestClient(api)
    response = client.delete(f"/links/{link.short_code}")

    assert response.status_code == 401
    # 連結應該仍然存在
    assert Link.objects.filter(short_code="unauth01").exists()


# ===== Shorten 例外路徑（自訂 slug 撞名 / 短碼生成錯誤）=====

@pytest.mark.django_db
def test_shorten_duplicate_custom_slug_returns_409(test_user, ninja_authenticated_client):
    """
    測試 API - 自訂 slug 與既有連結衝突時回傳 409。
    """
    Link.objects.create(
        original_url="https://example.com/first",
        short_code="takenslug",
        is_custom_slug=True,
        owner=test_user,
    )

    response = ninja_authenticated_client.post(
        "/shorten",
        json={"original_url": "https://example.com/second", "custom_slug": "takenslug"},
    )

    assert response.status_code == 409
    assert "已被使用" in response.json()["detail"]
    # 不應因衝突而多建立連結
    assert Link.objects.filter(short_code="takenslug").count() == 1


@pytest.mark.django_db
def test_shorten_short_code_generation_error_returns_500(ninja_authenticated_client):
    """
    測試 API - 短碼生成發生非預期錯誤（ShortCodeGenerationError）時回傳 500。
    """
    with patch(
        "shortener.api.create_short_link",
        side_effect=ShortCodeGenerationError(),
    ):
        response = ninja_authenticated_client.post(
            "/shorten",
            json={"original_url": "https://example.com/boom"},
        )

    assert response.status_code == 500
    assert "系統發生錯誤" in response.json()["detail"]


# ===== check-slug 端點 =====

@pytest.mark.django_db
def test_check_slug_available(ninja_authenticated_client):
    """可用的 slug 應回 available=True"""
    response = ninja_authenticated_client.get("/check-slug/freeslug")

    assert response.status_code == 200
    data = response.json()
    assert data["available"] is True
    assert data["slug"] == "freeslug"


@pytest.mark.django_db
def test_check_slug_already_taken(test_user, ninja_authenticated_client):
    """已被使用的 slug 應回 available=False"""
    Link.objects.create(
        original_url="https://example.com",
        short_code="usedslug",
        owner=test_user,
    )

    response = ninja_authenticated_client.get("/check-slug/usedslug")

    assert response.status_code == 200
    data = response.json()
    assert data["available"] is False
    assert "已被使用" in data["message"]


@pytest.mark.django_db
def test_check_slug_reserved_word(ninja_authenticated_client):
    """系統保留字應不可用"""
    response = ninja_authenticated_client.get("/check-slug/admin")

    assert response.status_code == 200
    data = response.json()
    assert data["available"] is False
    assert "保留字" in data["message"]


@pytest.mark.django_db
def test_check_slug_invalid_format(ninja_authenticated_client):
    """格式不合（過短）應不可用，且回傳對應訊息"""
    response = ninja_authenticated_client.get("/check-slug/ab")

    assert response.status_code == 200
    data = response.json()
    assert data["available"] is False
    assert "至少 3 個字元" in data["message"]
