"""
API 流量限制（throttling）測試

驗證限流確實接在端點上並回應 429：
- 公開 QR 端點：AnonRateThrottle，按來源 IP
- 已認證端點：AuthRateThrottle，按使用者

以 monkeypatch 把 throttle 上限調極低（num_requests=2），避免實打數十次請求；
計數存於快取，conftest 的 autouse fixture 已將測試 cache 切為 LocMemCache 並逐測試清空。
"""

import pytest
from ninja.testing import TestClient

from ninja_shortener.api import api
from shortener import api as shortener_api
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
