"""URL 契約測試

其他測試多以 reverse() 或 Ninja TestClient（直接呼叫 api 物件、繞過 urls.py）發請求，
路由字串被改動時它們照樣會過；但對外的網址是契約——書籤、分享出去的連結、
Chrome 擴充套件（呼叫 /api/shorten、/api/links）都依賴它。這裡把實際路徑釘住。
"""

import pytest
from django.urls import resolve, reverse

from shortener import views


@pytest.mark.parametrize('name, args, path', [
    ('home', [], '/'),
    ('dashboard', [], '/dashboard/'),
    ('shorten_url', [], '/shorten/'),
    ('register', [], '/register/'),
    ('login', [], '/login/'),
    ('logout', [], '/logout/'),
    ('refresh_preview', ['abc'], '/links/abc/refresh/'),
    ('preview_status', ['abc'], '/links/abc/preview-status/'),
    ('delete_link', ['abc'], '/links/abc/delete/'),
    ('link_stats', ['abc'], '/links/abc/stats/'),
    ('api_keys', [], '/settings/api-keys/'),
    ('create_api_key', [], '/settings/api-keys/create/'),
    ('delete_api_key', [7], '/settings/api-keys/7/delete/'),
    ('redirect', ['abc'], '/abc'),
])
def test_named_routes(name, args, path):
    assert reverse(name, args=args) == path


@pytest.mark.parametrize('path, view', [
    ('/', views.home_view),
    ('/dashboard/', views.dashboard_view),
    ('/shorten/', views.shorten_url_view),
    ('/links/abc/refresh/', views.refresh_preview_view),
    ('/links/abc/preview-status/', views.preview_status_view),
    ('/links/abc/delete/', views.delete_link_view),
    ('/links/abc/stats/', views.link_stats_view),
    ('/settings/api-keys/', views.api_keys_view),
    ('/settings/api-keys/create/', views.create_api_key_view),
    ('/settings/api-keys/7/delete/', views.delete_api_key_view),
    ('/abc', views.redirect_view),
])
def test_paths_resolve_to_views(path, view):
    assert resolve(path).func == view


@pytest.mark.django_db
@pytest.mark.parametrize('method, path', [
    ('post', '/api/shorten'),
    ('get', '/api/links'),
    ('get', '/api/links/abc'),
    ('get', '/api/check-slug/abc'),
])
def test_api_mounted_under_api_prefix(client, method, path):
    """API 掛在 /api/ 底下（擴充套件寫死此路徑）；未認證應回 401 而非 404"""
    response = getattr(client, method)(path, content_type='application/json')

    assert response.status_code == 401


@pytest.mark.django_db
def test_jwt_token_endpoint_mounted(client):
    """JWT 取得 token 的端點可用（帳密錯誤回 401，而非 404）"""
    response = client.post(
        '/api/token/pair',
        {'username': 'nobody', 'password': 'wrong'},
        content_type='application/json',
    )

    assert response.status_code == 401


@pytest.mark.django_db
def test_login_page_renders(client):
    """登入頁使用專案的模板"""
    response = client.get('/login/')

    assert response.status_code == 200
    assert 'registration/login.html' in [t.name for t in response.templates]


def test_admin_mounted(client):
    """Django Admin 掛在 /admin/（未登入導向 admin 登入頁）"""
    response = client.get('/admin/')

    assert response.status_code == 302
    assert response.url.startswith('/admin/login/')


@pytest.mark.django_db
def test_jwt_token_pair_flow(client, django_user_model):
    """以帳密向 /api/token/pair 換取 access token，並可用它呼叫受保護端點"""
    django_user_model.objects.create_user(username='jwtuser', password='pw-123456')

    token_response = client.post(
        '/api/token/pair',
        {'username': 'jwtuser', 'password': 'pw-123456'},
        content_type='application/json',
    )
    assert token_response.status_code == 200
    access = token_response.json()['access']

    response = client.get('/api/links', HTTP_AUTHORIZATION=f'Bearer {access}')
    assert response.status_code == 200
    assert response.json()['count'] == 0
