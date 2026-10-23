import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.contrib.messages import get_messages

from shortener.validators import (
    MAX_URL_LENGTH,
    validate_custom_slug,
    validate_url_format,
    validate_url_scheme,
)
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


# Fixture: client 已移至 conftest.py


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


class TestUrlLengthLimit:
    """測試目標網址長度上限（超過資料庫欄位上限需回錯誤而非撞庫 500）。"""

    @pytest.mark.django_db
    def test_api_accepts_long_url_within_limit(self, ninja_authenticated_client):
        """300 字元的網址（帶追蹤參數的真實場景）可正常建立。"""
        url = 'https://example.com/path?utm_content=' + 'a' * 270

        response = ninja_authenticated_client.post('/shorten', json={'original_url': url})

        assert response.status_code == 200
        assert Link.objects.filter(original_url=url).exists()

    @pytest.mark.django_db
    def test_api_rejects_url_over_limit(self, ninja_authenticated_client):
        """超過 MAX_URL_LENGTH 的網址回 422 與中文訊息。"""
        url = 'https://example.com/?q=' + 'a' * MAX_URL_LENGTH

        response = ninja_authenticated_client.post('/shorten', json={'original_url': url})

        assert response.status_code == 422
        assert '網址過長' in str(response.json())
        assert Link.objects.count() == 0

    @pytest.mark.django_db
    def test_web_form_rejects_url_over_limit(self, client):
        """網頁表單超長網址顯示錯誤訊息並導回首頁，不建立連結。"""
        url = 'https://example.com/?q=' + 'a' * MAX_URL_LENGTH

        response = client.post(reverse('shorten_url'), {'original_url': url})

        assert response.status_code == 302
        messages = [str(m) for m in get_messages(response.wsgi_request)]
        assert any('網址過長' in m for m in messages)
        assert Link.objects.count() == 0


class TestUrlLengthBoundary:
    """上限邊界：恰好 2000 字元可建立、2001 字元拒絕（寫死數字，不引用常數）"""

    @staticmethod
    def _url_of_length(n):
        base = 'https://example.com/?q='
        return base + 'a' * (n - len(base))

    @pytest.mark.django_db
    def test_api_boundary(self, ninja_authenticated_client):
        ok = ninja_authenticated_client.post('/shorten', json={'original_url': self._url_of_length(2000)})
        too_long = ninja_authenticated_client.post('/shorten', json={'original_url': self._url_of_length(2001)})

        assert ok.status_code == 200
        assert too_long.status_code == 422
        assert Link.objects.count() == 1

    @pytest.mark.django_db
    def test_web_form_boundary(self, client):
        client.post(reverse('shorten_url'), {'original_url': self._url_of_length(2000)})
        response = client.post(reverse('shorten_url'), {'original_url': self._url_of_length(2001)})

        assert Link.objects.count() == 1
        messages = [str(m) for m in get_messages(response.wsgi_request)]
        assert messages[-1] == '網址過長（上限 2000 字元）'


class TestValidateCustomSlug:
    """自訂 slug 驗證：正規化、長度、格式、連續連字號、保留字"""

    def test_none_passthrough(self):
        assert validate_custom_slug(None) is None

    @pytest.mark.parametrize('raw, expected', [
        ('  My-Link  ', 'my-link'),
        ('abc', 'abc'),
        ('a' * 50, 'a' * 50),
        ('a1-b2-c3', 'a1-b2-c3'),
    ])
    def test_valid_slugs_normalized(self, raw, expected):
        assert validate_custom_slug(raw) == expected

    @pytest.mark.parametrize('raw, message', [
        ('ab', '自訂網址必須至少 3 個字元'),
        ('  ab  ', '自訂網址必須至少 3 個字元'),
        ('a' * 51, '自訂網址不得超過 50 個字元'),
        ('-abc', '自訂網址只能包含英文字母、數字和連字號，且不能以連字號開頭或結尾'),
        ('abc-', '自訂網址只能包含英文字母、數字和連字號，且不能以連字號開頭或結尾'),
        ('ab_c', '自訂網址只能包含英文字母、數字和連字號，且不能以連字號開頭或結尾'),
        ('中文網址', '自訂網址只能包含英文字母、數字和連字號，且不能以連字號開頭或結尾'),
        ('a--b', '自訂網址不能包含連續的連字號'),
        ('Admin', '「admin」是系統保留字，請使用其他名稱'),
        ('dashboard', '「dashboard」是系統保留字，請使用其他名稱'),
    ])
    def test_invalid_slugs(self, raw, message):
        with pytest.raises(ValueError) as exc_info:
            validate_custom_slug(raw)
        assert str(exc_info.value) == message


class TestValidateUrlFormat:
    """網址格式驗證（網頁表單用；API 端由 pydantic HttpUrl 負責）"""

    @pytest.mark.parametrize('url', [
        'http://example.com',
        'https://example.com:8443/path?q=1#top',
        'http://localhost:8000/',
        'https://例子.測試/',
    ])
    def test_valid(self, url):
        validate_url_format(url)  # 不應拋出異常

    @pytest.mark.parametrize('url', [
        'http://',
        'http://exa mple.com',
        'example.com',
        'ftp://example.com',
    ])
    def test_invalid(self, url):
        with pytest.raises(ValidationError) as exc_info:
            validate_url_format(url)
        assert exc_info.value.message == '請輸入有效的網址'
