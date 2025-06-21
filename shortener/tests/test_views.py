import pytest
from django.test import Client
from django.contrib.auth.models import User
from django.urls import reverse
from django.contrib.messages import get_messages

from shortener.models import Link


@pytest.fixture
def client():
    """提供測試用的 Django 測試客戶端。"""
    return Client()


@pytest.fixture
def authenticated_user():
    """創建測試用的已認證用戶。"""
    return User.objects.create_user(username="testuser", password="password123")


@pytest.fixture
def authenticated_client(client, authenticated_user):
    """提供已登入的測試客戶端。"""
    client.login(username="testuser", password="password123")
    return client

# ===== Home View Tests =====

@pytest.mark.django_db
def test_home_view(client):
    """測試首頁視圖的基本功能。"""
    response = client.get(reverse('home'))
    assert response.status_code == 200
    assert 'home.html' in [t.name for t in response.templates]


@pytest.mark.django_db
def test_home_view_with_session_data(client):
    """測試首頁視圖處理 session 中的短網址數據。"""
    # 設置 session 數據
    session = client.session
    session['latest_short_url'] = 'http://test.com/short'
    session.save()

    response = client.get(reverse('home'))
    assert response.status_code == 200
    assert 'short_url' in response.context
    assert response.context['short_url'] == 'http://test.com/short'
    # 檢查 session 是否被清除
    assert 'latest_short_url' not in client.session

# ===== Dashboard View Tests =====

@pytest.mark.django_db
def test_dashboard_view_unauthenticated(client):
    """測試未登入用戶訪問儀表板會被重定向到登入頁面。"""
    response = client.get(reverse('dashboard'))
    assert response.status_code == 302
    assert response.url.startswith('/accounts/login/')


@pytest.mark.django_db
def test_dashboard_view_authenticated(authenticated_client, authenticated_user):
    """測試已登入用戶可以在儀表板看見自己的連結。"""
    # 創建其他用戶和連結
    other_user = User.objects.create_user(username="otheruser", password="password123")
    Link.objects.create(
        original_url="http://myurl.com",
        short_code="mycode",
        owner=authenticated_user
    )
    Link.objects.create(
        original_url="http://otherurl.com",
        short_code="othercode",
        owner=other_user
    )

    response = authenticated_client.get(reverse('dashboard'))
    assert response.status_code == 200
    assert 'dashboard.html' in [t.name for t in response.templates]
    # 檢查只能看到自己的連結
    assert len(response.context['links']) == 1
    assert response.context['links'][0].short_code == 'mycode'

# ===== Redirect View Tests =====

@pytest.mark.django_db
def test_redirect_view_valid(client, authenticated_user):
    """測試有效的短網址會重定向並增加點擊次數。"""
    link = Link.objects.create(
        original_url="https://example.com",
        short_code="valid123",
        owner=authenticated_user,
        click_count=0
    )

    response = client.get(f'/{link.short_code}')
    assert response.status_code == 302
    assert response.url == link.original_url

    # 檢查點擊次數是否增加
    link.refresh_from_db()
    assert link.click_count == 1
    assert link.last_clicked_at is not None


@pytest.mark.django_db
def test_redirect_view_invalid(client):
    """測試無效的短網址返回 404。"""
    response = client.get('/invalid123')
    assert response.status_code == 404

# ===== Shorten URL View Tests =====

@pytest.mark.django_db
def test_shorten_url_get_request(client):
    """測試 GET 請求會被重定向到首頁。"""
    response = client.get(reverse('shorten_url'))
    assert response.status_code == 302
    assert response.url == reverse('home')


@pytest.mark.django_db
def test_shorten_url_post_unauthenticated(client):
    """測試未登入用戶可以建立短網址。"""
    original_url = "https://google.com"
    response = client.post(reverse('shorten_url'), {'original_url': original_url})

    assert response.status_code == 302
    assert response.url == reverse('home')

    # 檢查資料庫中的記錄
    link = Link.objects.get(original_url=original_url)
    assert link is not None
    assert link.owner is None  # 匿名用戶

    # 檢查成功訊息和 session
    messages = list(get_messages(response.wsgi_request))
    assert len(messages) == 1
    assert str(messages[0]) == "成功建立短網址！"
    assert 'latest_short_url' in client.session

@pytest.mark.django_db
def test_shorten_url_post_authenticated(authenticated_client, authenticated_user):
    """測試已登入用戶可以建立短網址。"""
    original_url = "https://djangoproject.com"
    response = authenticated_client.post(reverse('shorten_url'), {'original_url': original_url})

    assert response.status_code == 302
    assert response.url == reverse('home')

    # 檢查資料庫中的記錄
    link = Link.objects.get(original_url=original_url)
    assert link.owner == authenticated_user


@pytest.mark.django_db
def test_shorten_url_post_empty_url(client):
    """測試提交空的 URL 不會建立連結。"""
    response = client.post(reverse('shorten_url'), {'original_url': ''})
    assert response.status_code == 302
    assert response.url == reverse('home')
    assert Link.objects.count() == 0

# ===== Register View Tests =====

@pytest.mark.django_db
def test_register_view_get(client):
    """測試可以正常訪問註冊頁面。"""
    response = client.get(reverse('register'))
    assert response.status_code == 200
    assert 'registration/register.html' in [t.name for t in response.templates]


@pytest.mark.django_db
def test_register_view_post_success(client):
    """測試成功的用戶註冊。"""
    response = client.post(reverse('register'), {
        'username': 'newuser',
        'password1': 'a-strong-password-123',
        'password2': 'a-strong-password-123',
    })
    # 成功註冊應該重定向到登入頁面
    assert response.status_code == 302
    assert response.url == reverse('login')
    assert User.objects.filter(username='newuser').exists()


@pytest.mark.django_db
def test_register_view_post_password_mismatch(client):
    """測試密碼不匹配時的註冊失敗。"""
    response = client.post(reverse('register'), {
        'username': 'newuser',
        'password1': 'password123',  # 修復：使用正確的字段名稱
        'password2': 'password456',  # 密碼不匹配
    })
    assert response.status_code == 200
    assert not User.objects.filter(username='newuser').exists()
    # 檢查是否有錯誤訊息顯示在表單中
    assert 'form' in response.context
    assert response.context['form'].errors
