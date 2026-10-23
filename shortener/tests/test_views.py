from datetime import timedelta
from unittest.mock import patch

import pytest
from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.messages import get_messages
from django.db import connection
from django.shortcuts import resolve_url
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from shortener.models import ApiKey, Link, LinkPreview
from shortener.services import ShortCodeGenerationError


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
    assert response.url == '/login/?next=/dashboard/'


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
    messages_list = [str(m) for m in get_messages(response.wsgi_request)]
    assert messages_list == ['連結已成功刪除']


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
    messages_list = [str(m) for m in get_messages(response.wsgi_request)]
    assert messages_list == ['您沒有權限刪除此連結']


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
    assert response.url.startswith('/login/?next=')
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


# ===== Shorten URL View：過期時間（僅登入用戶、白名單）=====

@pytest.mark.django_db
@pytest.mark.parametrize('expires_in, seconds', [
    ('3600', 3600),
    ('86400', 86400),
    ('604800', 604800),
    ('2592000', 2592000),
])
def test_shorten_url_expires_in_sets_expires_at(authenticated_client, expires_in, seconds):
    """登入用戶選擇過期時間時，expires_at 應為「現在 + 對應秒數」。"""
    before = timezone.now()
    authenticated_client.post(reverse('shorten_url'), {
        'original_url': 'https://example.com/expiring',
        'expires_in': expires_in,
    })
    after = timezone.now()

    link = Link.objects.get(original_url='https://example.com/expiring')
    assert before + timedelta(seconds=seconds) <= link.expires_at <= after + timedelta(seconds=seconds)


@pytest.mark.django_db
@pytest.mark.parametrize('expires_in', ['', '999', 'abc'])
def test_shorten_url_expires_in_permanent_or_not_whitelisted(authenticated_client, expires_in):
    """空值（永久）或不在白名單的過期時間，一律建立永久連結。"""
    authenticated_client.post(reverse('shorten_url'), {
        'original_url': 'https://example.com/permanent',
        'expires_in': expires_in,
    })

    link = Link.objects.get(original_url='https://example.com/permanent')
    assert link.expires_at is None


@pytest.mark.django_db
def test_shorten_url_anonymous_ignores_expires_in(client):
    """匿名用戶送出過期時間會被忽略（僅登入用戶可設定）。"""
    client.post(reverse('shorten_url'), {
        'original_url': 'https://example.com/anon',
        'expires_in': '3600',
    })

    link = Link.objects.get(original_url='https://example.com/anon')
    assert link.expires_at is None


# ===== Shorten URL View：自訂 slug（僅登入用戶）=====

@pytest.mark.django_db
def test_shorten_url_custom_slug_normalized(authenticated_client, authenticated_user):
    """登入用戶的自訂 slug 會去空白、轉小寫後作為 short_code。"""
    authenticated_client.post(reverse('shorten_url'), {
        'original_url': 'https://example.com/custom',
        'custom_slug': '  My-Slug  ',
    })

    link = Link.objects.get(original_url='https://example.com/custom')
    assert link.short_code == 'my-slug'
    assert link.is_custom_slug is True
    assert link.owner == authenticated_user


@pytest.mark.django_db
def test_shorten_url_invalid_custom_slug_rejected(authenticated_client):
    """格式不合的自訂 slug：顯示驗證訊息、不建立連結。"""
    response = authenticated_client.post(reverse('shorten_url'), {
        'original_url': 'https://example.com/bad-slug',
        'custom_slug': 'ab',
    })

    assert response.status_code == 302
    assert response.url == reverse('home')
    assert Link.objects.count() == 0
    messages_list = [str(m) for m in get_messages(response.wsgi_request)]
    assert messages_list == ['自訂網址必須至少 3 個字元']


@pytest.mark.django_db
def test_shorten_url_duplicate_custom_slug_rejected(authenticated_client, authenticated_user):
    """自訂 slug 已被使用：顯示錯誤訊息、不新增連結。"""
    Link.objects.create(
        original_url='https://example.com/first', short_code='taken', owner=authenticated_user
    )

    response = authenticated_client.post(reverse('shorten_url'), {
        'original_url': 'https://example.com/second',
        'custom_slug': 'taken',
    })

    assert response.status_code == 302
    assert response.url == reverse('home')
    assert not Link.objects.filter(original_url='https://example.com/second').exists()
    messages_list = [str(m) for m in get_messages(response.wsgi_request)]
    assert messages_list == ['網址「taken」已被使用，請選擇其他名稱']


@pytest.mark.django_db
def test_shorten_url_anonymous_ignores_custom_slug(client):
    """匿名用戶送出自訂 slug 會被忽略，改用自動生成短碼。"""
    client.post(reverse('shorten_url'), {
        'original_url': 'https://example.com/anon-slug',
        'custom_slug': 'anonslug',
    })

    link = Link.objects.get(original_url='https://example.com/anon-slug')
    assert link.short_code != 'anonslug'
    assert link.is_custom_slug is False


@pytest.mark.django_db
def test_shorten_url_generation_error_shows_message(authenticated_client):
    """短碼生成失敗（ShortCodeGenerationError）時顯示系統錯誤訊息。"""
    with patch('shortener.views.create_short_link', side_effect=ShortCodeGenerationError()):
        response = authenticated_client.post(
            reverse('shorten_url'), {'original_url': 'https://example.com/boom'}
        )

    assert response.status_code == 302
    assert response.url == reverse('home')
    messages_list = [str(m) for m in get_messages(response.wsgi_request)]
    assert messages_list == ['系統發生錯誤，請稍後再試']
    assert 'latest_short_url' not in authenticated_client.session


@pytest.mark.django_db
def test_shorten_url_stores_full_short_url_in_session(client):
    """成功建立後，session 存的是含 scheme / host 的完整短網址，供首頁一次性顯示。"""
    client.post(reverse('shorten_url'), {'original_url': 'https://example.com/full'})

    link = Link.objects.get(original_url='https://example.com/full')
    assert client.session['latest_short_url'] == f'http://testserver/{link.short_code}'

    # 首頁顯示後即清除
    response = client.get(reverse('home'))
    assert response.context['short_url'] == f'http://testserver/{link.short_code}'
    assert 'latest_short_url' not in client.session


@pytest.mark.django_db
def test_shorten_url_enqueues_preview_fetch(client):
    """網頁表單建立連結後，同樣會排入 OG 預覽抓取。"""
    client.post(reverse('shorten_url'), {'original_url': 'https://example.com/preview'})

    link = Link.objects.get(original_url='https://example.com/preview')
    # conftest 讓背景任務同步執行並樁住 OG 抓取 → preview 已寫入
    assert LinkPreview.objects.filter(link=link).exists()


# ===== Dashboard Context =====

@pytest.mark.django_db
def test_dashboard_shows_link_limit(authenticated_client, small_link_limit):
    """Dashboard 會帶出連結上限供頁面顯示用量。"""
    response = authenticated_client.get(reverse('dashboard'))

    assert response.context['max_links'] == small_link_limit
    assert f'/ {small_link_limit} 個連結' in response.content.decode()


# ===== Refresh Preview View =====

@pytest.mark.django_db
def test_refresh_preview_view_owner(authenticated_client, authenticated_user):
    """擁有者可重新排入 OG 抓取：preview 重設後回到 dashboard 並顯示提示。"""
    link = Link.objects.create(
        original_url='https://example.com', short_code='refresh1', owner=authenticated_user
    )
    LinkPreview.objects.create(
        link=link, fetch_status=LinkPreview.FetchStatus.FAILED, fetch_error='舊錯誤'
    )

    with patch('shortener.services.async_task') as mock_async:
        response = authenticated_client.get(reverse('refresh_preview', args=[link.short_code]))

    assert response.status_code == 302
    assert response.url == reverse('dashboard')
    mock_async.assert_called_once_with('shortener.services.run_preview_fetch', link.id)
    preview = LinkPreview.objects.get(link=link)
    assert preview.fetch_status == LinkPreview.FetchStatus.PENDING
    assert preview.fetch_error == ''
    messages_list = [str(m) for m in get_messages(response.wsgi_request)]
    assert messages_list == ['已開始重新抓取預覽，稍候會自動更新']


@pytest.mark.django_db
def test_refresh_preview_view_non_owner(authenticated_client, other_user):
    """非擁有者不可重新抓取：不入列，回 dashboard 並顯示無權限訊息。"""
    link = Link.objects.create(
        original_url='https://example.com', short_code='refresh2', owner=other_user
    )

    with patch('shortener.services.async_task') as mock_async:
        response = authenticated_client.get(reverse('refresh_preview', args=[link.short_code]))

    assert response.status_code == 302
    assert response.url == reverse('dashboard')
    mock_async.assert_not_called()
    assert not LinkPreview.objects.filter(link=link).exists()
    messages_list = [str(m) for m in get_messages(response.wsgi_request)]
    assert messages_list == ['您沒有權限操作此連結']


@pytest.mark.django_db
def test_refresh_preview_view_requires_login(client, authenticated_user):
    """未登入不可重新抓取，會被導向登入頁。"""
    link = Link.objects.create(
        original_url='https://example.com', short_code='refresh3', owner=authenticated_user
    )

    with patch('shortener.services.async_task') as mock_async:
        response = client.get(reverse('refresh_preview', args=[link.short_code]))

    assert response.status_code == 302
    assert response.url.startswith(resolve_url(settings.LOGIN_URL))
    mock_async.assert_not_called()


# ===== 登入保護（每個需登入的網頁端點都必須擋下匿名請求）=====

@pytest.mark.django_db
@pytest.mark.parametrize('method, url_name, args', [
    ('get', 'dashboard', []),
    ('get', 'refresh_preview', ['guarded']),
    ('get', 'preview_status', ['guarded']),
    ('post', 'delete_link', ['guarded']),
    ('get', 'link_stats', ['guarded']),
    ('get', 'api_keys', []),
    ('post', 'create_api_key', []),
    ('post', 'delete_api_key', [1]),
])
def test_login_required_views_redirect_anonymous(client, authenticated_user, method, url_name, args):
    """匿名請求一律導向登入頁，且不產生任何副作用"""
    Link.objects.create(original_url='https://example.com', short_code='guarded', owner=authenticated_user)
    ApiKey.objects.create(owner=authenticated_user, name='k', key_hash='h' * 64, prefix='sk_x', pk=1)

    response = getattr(client, method)(reverse(url_name, args=args))

    assert response.status_code == 302
    assert response.url.startswith(resolve_url(settings.LOGIN_URL))
    assert Link.objects.filter(short_code='guarded').exists()
    assert ApiKey.objects.count() == 1
    assert not LinkPreview.objects.exists()


@pytest.mark.django_db
def test_dashboard_query_count_does_not_grow(authenticated_client, authenticated_user):
    """dashboard 以 select_related 預載 preview：查詢數不隨連結數量增加（無 N+1）"""
    def add_links(prefix, n):
        for i in range(n):
            link = Link.objects.create(
                original_url='https://example.com', short_code=f'{prefix}{i}', owner=authenticated_user
            )
            LinkPreview.objects.create(link=link, og_title='t', fetch_status='success')

    add_links('one', 1)
    with CaptureQueriesContext(connection) as one_link:
        authenticated_client.get(reverse('dashboard'))

    add_links('more', 4)
    with CaptureQueriesContext(connection) as five_links:
        authenticated_client.get(reverse('dashboard'))

    assert len(five_links) == len(one_link)


@pytest.mark.django_db
def test_delete_link_deletes_only_target(authenticated_client, authenticated_user):
    """有多筆連結時只刪除指定的那一筆"""
    for code in ('keep0001', 'drop0001', 'keep0002'):
        Link.objects.create(original_url='https://example.com', short_code=code, owner=authenticated_user)

    authenticated_client.post(reverse('delete_link', args=['drop0001']))

    assert set(Link.objects.values_list('short_code', flat=True)) == {'keep0001', 'keep0002'}


@pytest.mark.django_db
def test_dashboard_and_stats_show_full_short_url(authenticated_client, authenticated_user):
    """dashboard 與統計頁以 {% short_url %} 顯示含 scheme / host 的完整短網址"""
    Link.objects.create(original_url='https://example.com', short_code='fullurl1', owner=authenticated_user)

    dashboard = authenticated_client.get(reverse('dashboard')).content.decode()
    stats = authenticated_client.get(reverse('link_stats', args=['fullurl1'])).content.decode()

    assert 'http://testserver/fullurl1' in dashboard
    assert 'http://testserver/fullurl1' in stats


@pytest.mark.django_db
def test_home_form_has_csrf_token(client):
    """首頁表單以 request 渲染，才會帶出 CSRF token（否則送出必定 403）"""
    response = client.get(reverse('home'))

    assert 'name="csrfmiddlewaretoken"' in response.content.decode()


@pytest.mark.django_db
def test_redirect_view_targets_requested_link(client):
    """有多筆連結時，各短碼轉址到各自的目標網址"""
    for i in range(3):
        Link.objects.create(original_url=f'https://example.com/{i}', short_code=f'multi{i}')

    assert client.get('/multi1').url == 'https://example.com/1'
    assert client.get('/multi2').url == 'https://example.com/2'
    assert Link.objects.get(short_code='multi1').click_count == 1
    assert Link.objects.get(short_code='multi0').click_count == 0


@pytest.mark.django_db
def test_expired_page_shows_short_code(client):
    """過期頁會顯示是哪個短網址過期"""
    Link.objects.create(
        original_url='https://example.com', short_code='gone2024',
        expires_at=timezone.now() - timedelta(minutes=1),
    )

    response = client.get('/gone2024')

    assert response.status_code == 410
    assert response.context['short_code'] == 'gone2024'
    assert 'gone2024' in response.content.decode()


@pytest.mark.django_db
def test_expired_page_rendered_with_request(authenticated_client, authenticated_user):
    """過期頁以 request 渲染：登入者的導覽列照常顯示帳號"""
    Link.objects.create(
        original_url='https://example.com', short_code='gone2025',
        expires_at=timezone.now() - timedelta(minutes=1),
    )

    response = authenticated_client.get('/gone2025')

    assert response.status_code == 410
    assert f'您好, {authenticated_user.username}!' in response.content.decode()


@pytest.mark.django_db
def test_login_redirect_lands_on_login_page_and_returns(client, authenticated_user):
    """未登入被導向的登入頁真實存在（不是 404），登入後回到原本要去的頁面"""
    Link.objects.create(original_url='https://example.com', short_code='backhere', owner=authenticated_user)
    stats_url = reverse('link_stats', args=['backhere'])

    login_page = client.get(stats_url, follow=True)
    assert login_page.status_code == 200
    assert 'registration/login.html' in [t.name for t in login_page.templates]

    # 表單沒有 action，會送回含 ?next= 的同一個網址
    response = client.post(
        login_page.request['PATH_INFO'] + '?' + login_page.request['QUERY_STRING'],
        {'username': 'testuser', 'password': 'password123'},
    )
    assert response.status_code == 302
    assert response.url == stats_url


# ===== Shorten URL View：網址格式 =====

@pytest.mark.django_db
@pytest.mark.parametrize('url', [
    'http://',
    'https://',
    'http://exa mple.com',
    'https:// not a host',
    'http://.com',
])
def test_shorten_url_rejects_malformed_url(client, url):
    """協議正確但格式錯誤的網址（無主機名、含空白）不建立連結，與 API 的驗證一致"""
    response = client.post(reverse('shorten_url'), {'original_url': url})

    assert response.status_code == 302
    assert response.url == reverse('home')
    assert Link.objects.count() == 0
    assert [str(m) for m in get_messages(response.wsgi_request)] == ['請輸入有效的網址']


@pytest.mark.django_db
@pytest.mark.parametrize('url', [
    'http://localhost:8000/path',
    'https://sub.example.co.uk/a/b?x=1&y=2#frag',
    'https://例子.測試/路徑',
    'HTTPS://EXAMPLE.COM/',
])
def test_shorten_url_accepts_valid_url_forms(client, url):
    """常見的合法寫法（含連接埠、IDN 網域、大寫協議）照常建立"""
    client.post(reverse('shorten_url'), {'original_url': url})

    assert Link.objects.filter(original_url=url).exists()
