import pytest
from django.test import Client
from django.contrib.auth.models import User
from django.urls import reverse
from shortener.models import Link


# 測試常量
TEST_USERNAME = "testuser_ui"
TEST_PASSWORD = "password123"
USER_A_USERNAME = "user_a"
USER_A_PASSWORD = "password_a"
USER_B_USERNAME = "user_b"
USER_B_PASSWORD = "password_b"


@pytest.fixture
def test_client():
    """提供測試客戶端"""
    return Client()


@pytest.fixture
def test_user():
    """創建測試用戶"""
    return User.objects.create_user(username=TEST_USERNAME, password=TEST_PASSWORD)


@pytest.fixture
def two_users():
    """創建兩個測試用戶"""
    user_a = User.objects.create_user(username=USER_A_USERNAME, password=USER_A_PASSWORD)
    user_b = User.objects.create_user(username=USER_B_USERNAME, password=USER_B_PASSWORD)
    return user_a, user_b


@pytest.mark.django_db
def test_login_logout_flow(test_client, test_user):
    """
    測試使用者登入和登出功能流程

    測試步驟:
    1. 使用有效憑證登入，驗證重定向到儀表板
    2. 執行登出操作，驗證重定向到首頁
    3. 驗證登出後無法存取需要認證的頁面
    """
    # 準備 URL
    login_url = reverse("login")
    logout_url = reverse("logout")
    dashboard_url = reverse("dashboard")
    home_url = reverse("home")

    # 測試登入流程
    login_response = test_client.post(login_url, {
        "username": TEST_USERNAME,
        "password": TEST_PASSWORD
    })

    assert login_response.status_code == 302, "登入應該返回重定向狀態碼"
    assert login_response.url == dashboard_url, "登入成功後應重定向到儀表板"

    # 測試登出流程
    logout_response = test_client.post(logout_url)

    assert logout_response.status_code == 302, "登出應該返回重定向狀態碼"
    assert logout_response.url == home_url, "登出成功後應重定向到首頁"

    # 驗證登出後 session 已清除
    dashboard_response = test_client.get(dashboard_url)
    assert dashboard_response.status_code == 302, "登出後存取儀表板應被重定向"
    assert dashboard_response.url.startswith("/accounts/login/"), "應重定向到登入頁面"


@pytest.mark.django_db
def test_dashboard_shows_only_user_links(test_client, two_users):
    """
    測試儀表板權限隔離功能

    驗證儀表板只顯示當前登入使用者的短網址，不會洩露其他使用者的資料

    測試步驟:
    1. 為兩個不同使用者分別創建短網址
    2. 以其中一個使用者身份登入
    3. 驗證儀表板只顯示該使用者的連結，不顯示其他使用者的連結
    """
    user_a, user_b = two_users

    # 創建測試連結資料
    link_a = Link.objects.create(
        owner=user_a,
        original_url="https://example-a.com",
        short_code="link_a"
    )
    link_b = Link.objects.create(
        owner=user_b,
        original_url="https://example-b.com",
        short_code="link_b"
    )

    # 以 User A 身份登入
    login_success = test_client.login(
        username=USER_A_USERNAME,
        password=USER_A_PASSWORD
    )
    assert login_success, "使用者 A 登入應該成功"

    # 存取儀表板
    dashboard_url = reverse("dashboard")
    response = test_client.get(dashboard_url)

    assert response.status_code == 200, "儀表板頁面應該正常載入"

    # 檢查回應內容
    content = response.content.decode("utf-8")

    # 驗證包含 User A 的連結資訊
    assert link_a.original_url in content, f"儀表板應顯示使用者 A 的原始網址: {link_a.original_url}"
    assert link_a.short_code in content, f"儀表板應顯示使用者 A 的短代碼: {link_a.short_code}"

    # 驗證不包含 User B 的連結資訊
    assert link_b.original_url not in content, f"儀表板不應顯示使用者 B 的原始網址: {link_b.original_url}"
    assert link_b.short_code not in content, f"儀表板不應顯示使用者 B 的短代碼: {link_b.short_code}"
