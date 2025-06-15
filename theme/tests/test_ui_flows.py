import pytest
from django.test import Client
from django.contrib.auth.models import User
from django.urls import reverse
from shortener.models import Link

@pytest.mark.django_db
def test_login_logout_flow():
    """
    目標: 測試使用者登入和登出功能。
    步驟:
    1. 創建使用者。
    2. POST 請求到登入頁面, 登入成功 (重定向到儀表板)。
    3. GET 請求到登出 URL, 登出成功 (重定向到首頁)。
    """
    client = Client()
    username = "testuser_ui"
    password = "password123"

    # 1. 創建使用者
    user = User.objects.create_user(username=username, password=password)

    # 2. 測試登入
    login_url = reverse("login")
    dashboard_url = reverse("dashboard")

    # 嘗試登入
    response = client.post(login_url, {"username": username, "password": password})

    # 登入成功後重定向到儀表板
    assert response.status_code == 302
    assert response.url == dashboard_url

    # 3. 測試登出
    logout_url = reverse("logout")
    home_url = reverse("home")

    # 登入狀態下，請求登出 (必須使用 POST)
    response = client.post(logout_url)

    # 登出成功後重定向到首頁
    assert response.status_code == 302
    assert response.url == home_url

    # 驗證登出後 session 已清除
    response = client.get(dashboard_url)
    assert response.status_code == 302 # 應被重定向到登入頁面
    # Django 預設的登入 URL 是 /accounts/login/
    assert response.url.startswith("/accounts/login/")


@pytest.mark.django_db
def test_dashboard_shows_only_user_links():
    """
    目標: 儀表板只應顯示當前登入使用者的短網址。
    步驟:
    1. 創建兩個使用者 (User A, User B)。
    2. 為 User A 和 User B 分別創建幾個 Link 實例。
    3. 以 User A 的身份登入並存取儀表板。
    4. 回應的 HTML 內容中包含 User A 的連結，且不包含 User B 的連結。
    """
    # 1. 創建使用者
    user_a = User.objects.create_user(username="user_a", password="password_a")
    user_b = User.objects.create_user(username="user_b", password="password_b")

    # 2. 創建連結
    link_a = Link.objects.create(owner=user_a, original_url="https://a.com", short_code="link_a")
    link_b = Link.objects.create(owner=user_b, original_url="https://b.com", short_code="link_b")

    # 3. 以 User A 登入
    client = Client()
    client.login(username="user_a", password="password_a")

    # 存取儀表板
    dashboard_url = reverse("dashboard")
    response = client.get(dashboard_url)

    assert response.status_code == 200

    # 4. 內容
    content = response.content.decode("utf-8")

    # 應該包含 User A 的連結資訊
    assert link_a.original_url in content
    assert link_a.short_code in content

    # 不應該包含 User B 的連結資訊
    assert link_b.original_url not in content
    assert link_b.short_code not in content
