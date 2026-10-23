import struct
from datetime import timedelta
from io import BytesIO
from unittest.mock import patch

import pytest
import segno
from django.utils import timezone
from ninja.testing import TestClient

from ninja_shortener.api import api
from shortener.models import Link
from shortener.qr_utils import generate_qr_code


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
        assert response.json()['detail'][0]['msg'] == 'Value error, 尺寸必須是 128, 256 或 512'

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
        assert response.json() == {'detail': '連結已過期'}

    def test_get_qr_code_not_found(self):
        """測試不存在的短碼（即使資料庫中有其他連結）"""
        Link.objects.create(original_url="https://example.com", short_code="someother")
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
        assert response.json()['detail'][0]['msg'] == 'Value error, 顏色必須是有效的十六進位格式，例如 #FF0000'

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

    def test_qr_encodes_short_url_and_passes_params(self):
        """
        QR 內容驗證：應以「完整短網址」與正確的尺寸 / 顏色參數呼叫產生器。

        既有測試只驗 PNG 與狀態碼，無法擋住 URL 拼裝或參數傳遞的迴歸；
        這裡以 mock 攔截 generate_qr_code，直接斷言傳入內容。
        """
        link = Link.objects.create(
            original_url="https://example.com",
            short_code="urltest",
        )
        client = TestClient(api)

        with patch("shortener.api.generate_qr_code", return_value=BytesIO(b"PNG")) as mock_gen:
            response = client.get(
                f"/links/{link.short_code}/qr?size=512&dark=%23FF0000"
            )

        assert response.status_code == 200
        mock_gen.assert_called_once()
        kwargs = mock_gen.call_args.kwargs
        # URL 應為「scheme://host/short_code」結構，且結尾必含本連結短碼
        # （TestClient 下 scheme/host 為 mock，故只驗結構與短碼，不驗實際主機名）
        assert "://" in kwargs["url"]
        assert kwargs["url"].endswith("/urltest")
        # 尺寸與顏色參數應原樣傳遞
        assert kwargs["size"] == 512
        assert kwargs["dark"] == "#FF0000"
        assert kwargs["light"] == "#FFFFFF"

    def test_get_qr_code_invalid_light_color(self):
        """背景色（light）同樣需驗證格式"""
        link = Link.objects.create(
            original_url="https://example.com",
            short_code="badlight",
        )
        client = TestClient(api)

        response = client.get(f"/links/{link.short_code}/qr?light=white")

        assert response.status_code == 422

    def test_qr_default_params(self):
        """未指定參數時以預設尺寸 256、黑底白字呼叫產生器"""
        link = Link.objects.create(
            original_url="https://example.com",
            short_code="defaults",
        )
        client = TestClient(api)

        with patch("shortener.api.generate_qr_code", return_value=BytesIO(b"PNG")) as mock_gen:
            response = client.get(f"/links/{link.short_code}/qr")

        assert response.status_code == 200
        kwargs = mock_gen.call_args.kwargs
        assert kwargs["size"] == 256
        assert kwargs["dark"] == "#000000"
        assert kwargs["light"] == "#FFFFFF"

    def test_qr_response_body_is_png(self):
        """回應主體是完整 PNG（buffer 需從頭讀，否則會回空 body）"""
        link = Link.objects.create(
            original_url="https://example.com",
            short_code="pngbody",
        )
        client = TestClient(api)

        response = client.get(f"/links/{link.short_code}/qr")

        assert response.content.startswith(b'\x89PNG\r\n\x1a\n')


class TestGenerateQrCode:
    """qr_utils.generate_qr_code：尺寸 → scale 換算與預設參數"""

    URL = 'https://example.com/abc12345'

    @staticmethod
    def _png_width(buffer):
        data = buffer.read()
        assert data.startswith(b'\x89PNG\r\n\x1a\n')
        return struct.unpack('>I', data[16:20])[0]

    @staticmethod
    def _png_chunks(data):
        """解析 PNG chunk：{chunk 類型: [資料, ...]}"""
        chunks, pos = {}, 8
        while pos < len(data):
            length = struct.unpack('>I', data[pos:pos + 4])[0]
            chunk_type = data[pos + 4:pos + 8].decode()
            chunks.setdefault(chunk_type, []).append(data[pos + 8:pos + 8 + length])
            pos += 12 + length
        return chunks

    def test_custom_colors_applied(self):
        """自訂前景 / 背景色寫入 PNG 調色盤（背景在前、前景在後）"""
        data = generate_qr_code(self.URL, dark='#FF0000', light='#00FF00').read()

        assert self._png_chunks(data)['PLTE'] == [b'\x00\xff\x00\xff\x00\x00']

    def test_default_colors_are_opaque_black_on_white(self):
        """預設黑白：segno 以灰階輸出，無調色盤、無透明色"""
        chunks = self._png_chunks(generate_qr_code(self.URL).read())

        assert 'PLTE' not in chunks
        assert 'tRNS' not in chunks

    @pytest.mark.parametrize('size, scale', [(128, 4), (256, 8), (512, 17)])
    def test_size_maps_to_scale(self, size, scale):
        expected_width = segno.make(self.URL, error='M').symbol_size(scale=scale)[0]

        assert self._png_width(generate_qr_code(self.URL, size=size)) == expected_width

    def test_defaults(self):
        """預設 256px、黑白配色即可直接產生"""
        expected_width = segno.make(self.URL, error='M').symbol_size(scale=8)[0]

        assert self._png_width(generate_qr_code(self.URL)) == expected_width
