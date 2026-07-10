"""
流量限制（throttling）測試

驗證限流確實接在端點上：
- 公開 QR 端點：AnonRateThrottle，按來源 IP → 429
- 已認證端點：AuthRateThrottle，按使用者 → 429
- 網頁表單 shorten_url_view：UserRateThrottle（登入按帳號、匿名按 IP）
  → 超量時 redirect + 錯誤訊息（web 慣例，非 429）

以 monkeypatch 把 throttle 上限調極低（num_requests=2），避免實打數十次請求；
計數存於快取，conftest 的 autouse fixture 已將測試 cache 切為 LocMemCache 並逐測試清空。
"""

import pytest
from django.contrib.messages import get_messages
from django.urls import reverse
from ninja.testing import TestClient

from ninja_shortener.api import api
from shortener import api as shortener_api
from shortener import views as shortener_views
from shortener.models import Link


@pytest.mark.django_db
def test_qr_endpoint_throttled_returns_429(monkeypatch):
    """公開 QR 端點超過匿名速率上限應回 429"""
    monkeypatch.setattr(shortener_api._anon_throttle, 'num_requests', 2)

    Link.objects.create(original_url='https://example.com', short_code='thr1')
    client = TestClient(api)

    assert client.get('/links/thr1/qr').status_code == 200
    assert client.get('/links/thr1/qr').status_code == 200
    # 第 3 次超量
    assert client.get('/links/thr1/qr').status_code == 429


@pytest.mark.django_db
def test_authenticated_endpoint_throttled_returns_429(
    monkeypatch, ninja_authenticated_client, test_user
):
    """已認證端點超過使用者速率上限應回 429"""
    monkeypatch.setattr(shortener_api._user_throttle, 'num_requests', 2)

    Link.objects.create(
        original_url='https://example.com', short_code='thr2', owner=test_user
    )

    assert ninja_authenticated_client.get('/links/thr2').status_code == 200
    assert ninja_authenticated_client.get('/links/thr2').status_code == 200
    assert ninja_authenticated_client.get('/links/thr2').status_code == 429


@pytest.mark.django_db
def test_under_limit_not_throttled(monkeypatch):
    """未超過上限的請求不應被限流"""
    monkeypatch.setattr(shortener_api._anon_throttle, 'num_requests', 5)

    Link.objects.create(original_url='https://example.com', short_code='thr3')
    client = TestClient(api)

    for _ in range(5):
        assert client.get('/links/thr3/qr').status_code == 200


@pytest.mark.django_db
def test_web_shorten_anonymous_throttled(monkeypatch, client):
    """匿名網頁表單超過速率上限應被擋下並顯示錯誤訊息"""
    monkeypatch.setattr(shortener_views._shorten_throttle, 'num_requests', 2)

    url = reverse('shorten_url')
    data = {'original_url': 'https://example.com'}

    for _ in range(2):
        response = client.post(url, data)
        assert response.status_code == 302

    assert Link.objects.count() == 2

    # 第 3 次超量：被擋下、不建立連結
    response = client.post(url, data)
    assert response.status_code == 302
    assert Link.objects.count() == 2
    messages_list = list(get_messages(response.wsgi_request))
    assert any('操作過於頻繁' in str(msg) for msg in messages_list)


@pytest.mark.django_db
def test_web_shorten_authenticated_separate_bucket(monkeypatch, client, authenticated_user):
    """登入用戶按帳號計數，與匿名（IP）分屬不同 bucket、互不影響"""
    monkeypatch.setattr(shortener_views._shorten_throttle, 'num_requests', 2)

    url = reverse('shorten_url')
    data = {'original_url': 'https://example.com'}

    # 匿名先打滿上限
    for _ in range(2):
        client.post(url, data)

    # 同一 client（同 IP）登入後不受匿名計數影響
    client.login(username='testuser', password='password123')
    response = client.post(url, data)
    messages_list = list(get_messages(response.wsgi_request))
    assert not any('操作過於頻繁' in str(msg) for msg in messages_list)
    assert Link.objects.filter(owner=authenticated_user).count() == 1
