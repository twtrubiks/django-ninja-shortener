import pytest
from django.core.exceptions import ValidationError
from django.test import Client
from django.urls import reverse
from django.contrib.messages import get_messages

from shortener.validators import validate_url_scheme
from shortener.models import Link


class TestValidateUrlScheme:
    """測試 URL 協議驗證函式。"""

    def test_http_allowed(self):
        """測試 http 協議被允許。"""
        result = validate_url_scheme("http://example.com")
        assert result == "http://example.com"

    def test_https_allowed(self):
        """測試 https 協議被允許。"""
        result = validate_url_scheme("https://example.com")
        assert result == "https://example.com"

    def test_http_uppercase_allowed(self):
        """測試大寫 HTTP 協議被允許。"""
        result = validate_url_scheme("HTTP://example.com")
        assert result == "HTTP://example.com"

    def test_https_uppercase_allowed(self):
        """測試大寫 HTTPS 協議被允許。"""
        result = validate_url_scheme("HTTPS://example.com")
        assert result == "HTTPS://example.com"

    def test_javascript_rejected(self):
        """測試 javascript 協議被拒絕。"""
        with pytest.raises(ValidationError) as exc_info:
            validate_url_scheme("javascript:alert('xss')")
        assert "javascript" in str(exc_info.value)

    def test_data_rejected(self):
        """測試 data 協議被拒絕。"""
        with pytest.raises(ValidationError) as exc_info:
            validate_url_scheme("data:text/html,<script>alert('xss')</script>")
        assert "data" in str(exc_info.value)

    def test_ftp_rejected(self):
        """測試 ftp 協議被拒絕。"""
        with pytest.raises(ValidationError) as exc_info:
            validate_url_scheme("ftp://example.com")
        assert "ftp" in str(exc_info.value)

    def test_file_rejected(self):
        """測試 file 協議被拒絕。"""
        with pytest.raises(ValidationError) as exc_info:
            validate_url_scheme("file:///etc/passwd")
        assert "file" in str(exc_info.value)

    def test_vbscript_rejected(self):
        """測試 vbscript 協議被拒絕。"""
        with pytest.raises(ValidationError) as exc_info:
            validate_url_scheme("vbscript:msgbox('xss')")
        assert "vbscript" in str(exc_info.value)

    def test_empty_scheme_rejected(self):
        """測試空協議被拒絕。"""
        with pytest.raises(ValidationError):
            validate_url_scheme("//example.com")


@pytest.fixture
def client():
    """提供測試用的 Django 測試客戶端。"""
    return Client()


@pytest.mark.django_db
class TestShortenUrlViewXssProtection:
    """測試縮短 URL 視圖的 XSS 防護。"""

    def test_javascript_url_rejected(self, client):
        """測試 javascript URL 被拒絕。"""
        response = client.post(
            reverse('shorten_url'),
            {'original_url': "javascript:alert('xss')"}
        )

        assert response.status_code == 302
        assert response.url == reverse('home')
        assert Link.objects.count() == 0

        messages = list(get_messages(response.wsgi_request))
        assert len(messages) == 1
        assert "javascript" in str(messages[0]).lower()

    def test_data_url_rejected(self, client):
        """測試 data URL 被拒絕。"""
        response = client.post(
            reverse('shorten_url'),
            {'original_url': "data:text/html,<script>alert('xss')</script>"}
        )

        assert response.status_code == 302
        assert Link.objects.count() == 0

    def test_valid_http_url_accepted(self, client):
        """測試有效的 http URL 被接受。"""
        response = client.post(
            reverse('shorten_url'),
            {'original_url': "http://example.com"}
        )

        assert response.status_code == 302
        assert Link.objects.count() == 1

    def test_valid_https_url_accepted(self, client):
        """測試有效的 https URL 被接受。"""
        response = client.post(
            reverse('shorten_url'),
            {'original_url': "https://example.com"}
        )

        assert response.status_code == 302
        assert Link.objects.count() == 1
