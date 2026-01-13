from datetime import timedelta

import pytest
from django.utils import timezone
from ninja.testing import TestClient

from ninja_shortener.api import api
from shortener.models import Link


# Fixture: reset_ninja_registry 已移至 conftest.py


@pytest.mark.django_db
class TestQRCodeAPI:
    def test_get_qr_code_default_size(self):
        """測試預設尺寸 QR Code"""
        link = Link.objects.create(
            original_url="https://example.com",
            short_code="testcode",
        )
        client = TestClient(api)
        response = client.get(f"/links/{link.short_code}/qr")

        assert response.status_code == 200
        assert response.headers['Content-Type'] == 'image/png'

    def test_get_qr_code_custom_size(self):
        """測試自訂尺寸"""
        link = Link.objects.create(
            original_url="https://example.com",
            short_code="testsize",
        )
        client = TestClient(api)

        for size in [128, 256, 512]:
            response = client.get(f"/links/{link.short_code}/qr?size={size}")
            assert response.status_code == 200
            assert response.headers['Content-Type'] == 'image/png'

    def test_get_qr_code_invalid_size(self):
        """測試無效尺寸"""
        link = Link.objects.create(
            original_url="https://example.com",
            short_code="badsize",
        )
        client = TestClient(api)
        response = client.get(f"/links/{link.short_code}/qr?size=100")

        assert response.status_code == 422  # Validation error

    def test_get_qr_code_custom_colors(self):
        """測試自訂顏色"""
        link = Link.objects.create(
            original_url="https://example.com",
            short_code="colors",
        )
        client = TestClient(api)
        response = client.get(
            f"/links/{link.short_code}/qr?dark=%23FF0000&light=%23FFFFFF"
        )

        assert response.status_code == 200
        assert response.headers['Content-Type'] == 'image/png'

    def test_get_qr_code_expired_link(self):
        """測試過期連結"""
        link = Link.objects.create(
            original_url="https://example.com",
            short_code="expired",
            expires_at=timezone.now() - timedelta(hours=1),
        )
        client = TestClient(api)
        response = client.get(f"/links/{link.short_code}/qr")

        assert response.status_code == 410

    def test_get_qr_code_not_found(self):
        """測試不存在的短碼"""
        client = TestClient(api)
        response = client.get("/links/notexist/qr")

        assert response.status_code == 404

    def test_get_qr_code_not_expired_link(self):
        """測試未過期連結"""
        link = Link.objects.create(
            original_url="https://example.com",
            short_code="valid",
            expires_at=timezone.now() + timedelta(hours=1),
        )
        client = TestClient(api)
        response = client.get(f"/links/{link.short_code}/qr")

        assert response.status_code == 200

    def test_get_qr_code_invalid_color_format(self):
        """測試無效顏色格式"""
        link = Link.objects.create(
            original_url="https://example.com",
            short_code="badcolor",
        )
        client = TestClient(api)

        # 測試無效格式
        response = client.get(f"/links/{link.short_code}/qr?dark=invalid")
        assert response.status_code == 422

        # 測試缺少 # 號
        response = client.get(f"/links/{link.short_code}/qr?dark=FF0000")
        assert response.status_code == 422

        # 測試長度不對
        response = client.get(f"/links/{link.short_code}/qr?dark=%23FFF")
        assert response.status_code == 422

    def test_get_qr_code_valid_color_formats(self):
        """測試有效顏色格式"""
        link = Link.objects.create(
            original_url="https://example.com",
            short_code="goodcolor",
        )
        client = TestClient(api)

        # 測試大寫
        response = client.get(f"/links/{link.short_code}/qr?dark=%23FF0000")
        assert response.status_code == 200

        # 測試小寫
        response = client.get(f"/links/{link.short_code}/qr?dark=%23ff0000")
        assert response.status_code == 200

        # 測試混合
        response = client.get(f"/links/{link.short_code}/qr?dark=%23Ff00Aa")
        assert response.status_code == 200
