from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.contrib.messages import get_messages
from django.urls import reverse
from django.utils import timezone

from shortener.models import Link


# Fixtures: client, authenticated_user, authenticated_client 已移至 conftest.py


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


@pytest.mark.django_db
def test_redirect_view_expired_link(client, authenticated_user):
    """測試過期的短網址返回 410 Gone。"""
    link = Link.objects.create(
        original_url="https://example.com",
        short_code="expired1",
        owner=authenticated_user,
        expires_at=timezone.now() - timedelta(hours=1)
    )

    response = client.get(f'/{link.short_code}')
    assert response.status_code == 410
    assert 'expired.html' in [t.name for t in response.templates]


@pytest.mark.django_db
def test_redirect_view_not_expired_link(client, authenticated_user):
    """測試未過期的短網址正常重導向。"""
    link = Link.objects.create(
        original_url="https://example.com",
        short_code="active1",
        owner=authenticated_user,
        expires_at=timezone.now() + timedelta(days=7)
    )

    response = client.get(f'/{link.short_code}')
    assert response.status_code == 302
    assert response.url == link.original_url


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


# ===== Dashboard Pagination Tests =====

@pytest.mark.django_db
def test_dashboard_pagination_first_page(authenticated_client, authenticated_user):
    """測試 Dashboard 分頁功能 - 第一頁顯示正確數量。"""
    from shortener.views import DASHBOARD_ITEMS_PER_PAGE

    # 建立超過一頁的連結數量
    for i in range(30):
        Link.objects.create(
            original_url=f"https://example{i}.com",
            short_code=f"code{i:03d}",
            owner=authenticated_user
        )

    response = authenticated_client.get(reverse('dashboard'))
    assert response.status_code == 200
    assert len(response.context['links']) == DASHBOARD_ITEMS_PER_PAGE
    assert response.context['page_obj'].number == 1
    assert response.context['page_obj'].has_next() is True


@pytest.mark.django_db
def test_dashboard_pagination_second_page(authenticated_client, authenticated_user):
    """測試 Dashboard 分頁功能 - 第二頁正確顯示。"""
    from shortener.views import DASHBOARD_ITEMS_PER_PAGE

    # 建立超過一頁的連結數量
    for i in range(30):
        Link.objects.create(
            original_url=f"https://example{i}.com",
            short_code=f"code{i:03d}",
            owner=authenticated_user
        )

    response = authenticated_client.get(reverse('dashboard') + '?page=2')
    assert response.status_code == 200
    assert response.context['page_obj'].number == 2
    assert response.context['page_obj'].has_previous() is True
    # 第二頁應該有剩餘的連結
    assert len(response.context['links']) == 30 - DASHBOARD_ITEMS_PER_PAGE


@pytest.mark.django_db
def test_dashboard_pagination_invalid_page(authenticated_client, authenticated_user):
    """測試 Dashboard 分頁功能 - 無效頁碼處理。"""
    Link.objects.create(
        original_url="https://example.com",
        short_code="testcode",
        owner=authenticated_user
    )

    # 無效頁碼應該回到第一頁
    response = authenticated_client.get(reverse('dashboard') + '?page=invalid')
    assert response.status_code == 200
    assert response.context['page_obj'].number == 1


@pytest.mark.django_db
def test_dashboard_pagination_out_of_range(authenticated_client, authenticated_user):
    """測試 Dashboard 分頁功能 - 超出範圍的頁碼。"""
    Link.objects.create(
        original_url="https://example.com",
        short_code="testcode",
        owner=authenticated_user
    )

    # 超出範圍的頁碼應該顯示最後一頁
    response = authenticated_client.get(reverse('dashboard') + '?page=999')
    assert response.status_code == 200
    # get_page() 會自動處理超出範圍的頁碼


# ===== User Link Limit Tests (Form View) =====

@pytest.mark.django_db
def test_user_link_limit_reached_form(authenticated_client, authenticated_user, small_link_limit):
    """測試表單視圖 - 用戶達到連結上限時顯示錯誤。"""
    # 建立連結達到上限
    for i in range(small_link_limit):
        Link.objects.create(
            original_url=f"https://example{i}.com",
            short_code=f"code{i:03d}",
            owner=authenticated_user
        )

    # 嘗試建立新連結
    response = authenticated_client.post(
        reverse('shorten_url'),
        {'original_url': 'https://newsite.com'}
    )

    assert response.status_code == 302
    assert response.url == reverse('home')

    # 檢查錯誤訊息
    messages_list = list(get_messages(response.wsgi_request))
    assert any('上限' in str(msg) for msg in messages_list)

    # 驗證沒有建立新連結
    assert Link.objects.filter(owner=authenticated_user).count() == small_link_limit


@pytest.mark.django_db
def test_user_link_limit_not_reached_form(authenticated_client, authenticated_user, small_link_limit):
    """測試表單視圖 - 未達上限時可以正常建立連結。"""
    # 建立少於上限的連結
    for i in range(small_link_limit - 1):
        Link.objects.create(
            original_url=f"https://example{i}.com",
            short_code=f"code{i:03d}",
            owner=authenticated_user
        )

    # 應該可以建立新連結
    response = authenticated_client.post(
        reverse('shorten_url'),
        {'original_url': 'https://newsite.com'}
    )

    assert response.status_code == 302

    # 檢查成功訊息
    messages_list = list(get_messages(response.wsgi_request))
    assert any('成功' in str(msg) for msg in messages_list)

    # 驗證連結已建立
    assert Link.objects.filter(owner=authenticated_user).count() == small_link_limit


@pytest.mark.django_db
def test_anonymous_user_no_link_limit(client):
    """測試匿名用戶沒有連結數量限制。"""
    # 匿名用戶建立多個連結
    for i in range(10):
        response = client.post(
            reverse('shorten_url'),
            {'original_url': f'https://example{i}.com'}
        )
        assert response.status_code == 302

    # 應該成功建立所有連結
    assert Link.objects.filter(owner=None).count() == 10


# ===== Delete Link View Tests =====

@pytest.mark.django_db
def test_delete_link_success(authenticated_client, authenticated_user):
    """測試擁有者可以成功刪除自己的連結。"""
    link = Link.objects.create(
        original_url="https://example.com/to-delete",
        short_code="delete01",
        owner=authenticated_user
    )

    response = authenticated_client.post(reverse('delete_link', args=[link.short_code]))

    assert response.status_code == 302
    assert response.url == reverse('dashboard')
    assert not Link.objects.filter(short_code="delete01").exists()

    # 檢查成功訊息
    messages_list = list(get_messages(response.wsgi_request))
    assert any('成功刪除' in str(msg) for msg in messages_list)


@pytest.mark.django_db
def test_delete_link_permission_denied(authenticated_client, authenticated_user):
    """測試用戶無法刪除他人的連結。"""
    other_user = User.objects.create_user(username="otheruser2", password="password123")
    link = Link.objects.create(
        original_url="https://example.com/others",
        short_code="other001",
        owner=other_user
    )

    response = authenticated_client.post(reverse('delete_link', args=[link.short_code]))

    assert response.status_code == 302
    assert response.url == reverse('dashboard')
    # 連結應該仍然存在
    assert Link.objects.filter(short_code="other001").exists()

    # 檢查錯誤訊息
    messages_list = list(get_messages(response.wsgi_request))
    assert any('沒有權限' in str(msg) for msg in messages_list)


@pytest.mark.django_db
def test_delete_link_not_found(authenticated_client):
    """測試刪除不存在的連結返回 404。"""
    response = authenticated_client.post(reverse('delete_link', args=['notexist']))
    assert response.status_code == 404


@pytest.mark.django_db
def test_delete_link_unauthenticated(client, authenticated_user):
    """測試未登入用戶無法刪除連結。"""
    link = Link.objects.create(
        original_url="https://example.com/protected",
        short_code="protect1",
        owner=authenticated_user
    )

    response = client.post(reverse('delete_link', args=[link.short_code]))

    assert response.status_code == 302
    assert '/accounts/login/' in response.url
    # 連結應該仍然存在
    assert Link.objects.filter(short_code="protect1").exists()


@pytest.mark.django_db
def test_delete_link_get_request_redirects(authenticated_client, authenticated_user):
    """測試 GET 請求會被重定向到 dashboard。"""
    link = Link.objects.create(
        original_url="https://example.com/get-test",
        short_code="gettest1",
        owner=authenticated_user
    )

    response = authenticated_client.get(reverse('delete_link', args=[link.short_code]))

    assert response.status_code == 302
    assert response.url == reverse('dashboard')
    # 連結應該仍然存在（GET 請求不應刪除）
    assert Link.objects.filter(short_code="gettest1").exists()
