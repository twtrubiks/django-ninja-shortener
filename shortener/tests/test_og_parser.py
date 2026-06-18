"""
Open Graph Parser 單元測試

使用 unittest.mock 模擬外部 HTTP 請求
"""

import ipaddress
import socket

import metadata_parser
import pytest
import requests
from unittest.mock import MagicMock, patch

from shortener.og_parser import (
    OGData,
    OGParserError,
    SSRFBlockedError,
    FetchTimeoutError,
    InvalidURLError,
    _validate_url_security,
    fetch_og_data,
)


def _fake_getaddrinfo(host, port, *args, **kwargs):
    """測試用假解析器：IP 字面原樣返回，網域名一律當公開 IP（93.184.216.34）。

    讓 og_parser 單元測試不需真實 DNS 即可離線執行，同時保留對「IP 字面」的
    真實判斷（例如 192.168.1.1 仍會被歸為私有而擋下）。以 ``new=`` 方式注入，
    不會改變被裝飾測試的參數簽名。
    """
    try:
        ipaddress.ip_address(host)
        ip = host
    except ValueError:
        ip = '93.184.216.34'
    family = socket.AF_INET6 if ':' in ip else socket.AF_INET
    return [(family, socket.SOCK_STREAM, socket.IPPROTO_TCP, '', (ip, port))]


class TestURLSecurityValidation:
    """URL 安全驗證測試"""

    @patch('shortener.og_parser.socket.getaddrinfo', new=_fake_getaddrinfo)
    def test_valid_https_url(self):
        """有效的 HTTPS URL 應通過驗證"""
        _validate_url_security('https://example.com')  # 不應拋出異常

    @patch('shortener.og_parser.socket.getaddrinfo', new=_fake_getaddrinfo)
    def test_valid_http_url(self):
        """有效的 HTTP URL 應通過驗證"""
        _validate_url_security('http://example.com')

    def test_blocks_localhost(self):
        """應阻擋 localhost"""
        with pytest.raises(SSRFBlockedError):
            _validate_url_security('http://localhost/test')

    def test_blocks_private_ip_10(self):
        """應阻擋 10.x.x.x 私有 IP"""
        with pytest.raises(SSRFBlockedError):
            _validate_url_security('http://10.0.0.1/test')

    def test_blocks_private_ip_172(self):
        """應阻擋 172.16-31.x.x 私有 IP"""
        with pytest.raises(SSRFBlockedError):
            _validate_url_security('http://172.16.0.1/test')

    def test_blocks_private_ip_192(self):
        """應阻擋 192.168.x.x 私有 IP"""
        with pytest.raises(SSRFBlockedError):
            _validate_url_security('http://192.168.1.1/test')

    def test_blocks_loopback(self):
        """應阻擋 127.x.x.x 回環地址"""
        with pytest.raises(SSRFBlockedError):
            _validate_url_security('http://127.0.0.1/test')

    def test_blocks_file_protocol(self):
        """應阻擋 file:// 協議"""
        with pytest.raises(InvalidURLError):
            _validate_url_security('file:///etc/passwd')

    def test_blocks_ftp_protocol(self):
        """應阻擋 ftp:// 協議"""
        with pytest.raises(InvalidURLError):
            _validate_url_security('ftp://example.com/file')


class TestSSRFBypassVectors:
    """SSRF 編碼繞過向量。

    這些字串在舊版「hostname 字串前綴比對」下全數被放行（十進位 / hex / octal /
    IPv6-mapped），是「看似有防護、實則可繞過」的核心。新版改以實際解析 + IP
    物件化檢查後，應全部阻擋。

    刻意不 mock 解析器：getaddrinfo 會把整數 / IPv6 寫法依 inet_aton 語意正規化
    成真正的內網 IP（與 requests 實際連線時一致），正好驗證修補在真實解析下生效。
    在套用 inet_aton 的平台（如 CI 用的 Debian glibc）上，這些會解析到內網 IP 而
    觸發 SSRFBlockedError。
    """

    @pytest.mark.parametrize('url', [
        'http://2130706433/',          # 十進位 = 127.0.0.1
        'http://0x7f000001/',          # hex = 127.0.0.1
        'http://0177.0.0.1/',          # octal = 127.0.0.1
        'http://2852039166/',          # 十進位 = 169.254.169.254（雲端 metadata）
        'http://[::ffff:127.0.0.1]/',  # IPv6-mapped = 127.0.0.1
        'http://[::ffff:a9fe:a9fe]/',  # IPv6-mapped = 169.254.169.254（metadata）
        'http://[::1]/',               # IPv6 loopback
    ])
    def test_blocks_encoded_internal_addresses(self, url):
        """整數 / IPv6 編碼指向內網或雲端 metadata 的 URL 應被阻擋"""
        with pytest.raises(SSRFBlockedError):
            _validate_url_security(url)

    def test_blocks_public_hostname_resolving_to_internal(self):
        """公開域名解析到內網 / metadata 也要擋（字串比對完全無法防這個）"""
        def resolver(host, port, *args, **kwargs):
            return [(
                socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP,
                '', ('169.254.169.254', port),
            )]

        with patch('shortener.og_parser.socket.getaddrinfo', new=resolver):
            with pytest.raises(SSRFBlockedError):
                _validate_url_security('http://totally-legit.example.com/')

    def test_blocks_ipv4_mapped_private_via_resolver(self):
        """解析結果為 IPv4-mapped 的私有位址應被拆解後擋下"""
        def resolver(host, port, *args, **kwargs):
            return [(
                socket.AF_INET6, socket.SOCK_STREAM, socket.IPPROTO_TCP,
                '', ('::ffff:10.0.0.5', port, 0, 0),
            )]

        with patch('shortener.og_parser.socket.getaddrinfo', new=resolver):
            with pytest.raises(SSRFBlockedError):
                _validate_url_security('http://mapped.example.com/')

    def test_unresolvable_host_raises_invalid(self):
        """無法解析的主機名應拋出 InvalidURLError（而非靜默放行）"""
        def resolver(host, port, *args, **kwargs):
            raise socket.gaierror('Name or service not known')

        with patch('shortener.og_parser.socket.getaddrinfo', new=resolver):
            with pytest.raises(InvalidURLError):
                _validate_url_security('http://no-such-host.invalid/')

    def test_allows_public_hostname(self):
        """解析到公開 IP 的正常域名應放行"""
        with patch('shortener.og_parser.socket.getaddrinfo', new=_fake_getaddrinfo):
            _validate_url_security('https://example.com/page')  # 不應拋出異常


class TestFetchOGData:
    """OG 資料抓取測試"""

    @patch('shortener.og_parser.socket.getaddrinfo', new=_fake_getaddrinfo)
    @patch('shortener.og_parser.metadata_parser.MetadataParser')
    @patch('shortener.og_parser.requests.Session.get')
    def test_successful_fetch(self, mock_get, mock_parser_class):
        """成功抓取 OG 資料"""
        # Mock requests 回應
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '<html></html>'
        mock_response.url = 'https://example.com'
        mock_get.return_value = mock_response

        # 設定 mock - 模擬 parsed_result.metadata 結構
        mock_parser = MagicMock()
        mock_parser.parsed_result.metadata = {
            'og': {
                'title': 'Test Title',
                'description': 'Test Description',
                'image': 'https://example.com/image.jpg',
                'site_name': 'Example Site',
                'type': 'website',
            },
            'meta': {},
            'page': {'title': 'Fallback Title'},
            'dc': {},
        }
        mock_parser_class.return_value = mock_parser

        # 執行
        result = fetch_og_data('https://example.com')

        # 驗證
        assert result.title == 'Test Title'
        assert result.description == 'Test Description'
        assert result.image == 'https://example.com/image.jpg'
        assert result.site_name == 'Example Site'
        assert result.is_empty is False

    @patch('shortener.og_parser.socket.getaddrinfo', new=_fake_getaddrinfo)
    @patch('shortener.og_parser.metadata_parser.MetadataParser')
    @patch('shortener.og_parser.requests.Session.get')
    def test_fallback_to_meta_tags(self, mock_get, mock_parser_class):
        """無 OG 標籤時退回使用 meta 標籤"""
        # Mock requests 回應
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '<html></html>'
        mock_response.url = 'https://example.com'
        mock_get.return_value = mock_response

        mock_parser = MagicMock()
        mock_parser.parsed_result.metadata = {
            'og': {},
            'meta': {'description': 'Meta Description'},
            'page': {'title': 'Page Title'},
            'dc': {},
        }
        mock_parser_class.return_value = mock_parser

        result = fetch_og_data('https://example.com')

        assert result.title == 'Page Title'
        assert result.description == 'Meta Description'

    @patch('shortener.og_parser.socket.getaddrinfo', new=_fake_getaddrinfo)
    @patch('shortener.og_parser.requests.Session.get')
    def test_handles_timeout(self, mock_get):
        """處理請求超時"""
        mock_get.side_effect = requests.exceptions.Timeout('Connection timed out')

        with pytest.raises(FetchTimeoutError):
            fetch_og_data('https://slow-site.com')

    @patch('shortener.og_parser.socket.getaddrinfo', new=_fake_getaddrinfo)
    @patch('shortener.og_parser.metadata_parser.MetadataParser')
    @patch('shortener.og_parser.requests.Session.get')
    def test_handles_parse_error(self, mock_get, mock_parser_class):
        """處理解析錯誤"""
        # Mock requests 回應
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '<html></html>'
        mock_response.url = 'https://example.com/404'
        mock_get.return_value = mock_response

        mock_parser_class.side_effect = metadata_parser.NotParsableFetchError('404')

        with pytest.raises(OGParserError):
            fetch_og_data('https://example.com/404')

    def test_blocks_ssrf_attempts(self):
        """SSRF 攻擊應被阻擋（不需要 mock）"""
        with pytest.raises(SSRFBlockedError):
            fetch_og_data('http://192.168.1.1/admin')

    @patch('shortener.og_parser.socket.getaddrinfo', new=_fake_getaddrinfo)
    @patch('shortener.og_parser.metadata_parser.MetadataParser')
    @patch('shortener.og_parser.requests.Session.get')
    def test_truncates_long_content(self, mock_get, mock_parser_class):
        """截斷過長的內容"""
        # Mock requests 回應
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '<html></html>'
        mock_response.url = 'https://example.com'
        mock_get.return_value = mock_response

        mock_parser = MagicMock()
        long_title = 'A' * 1000  # 超過 500 字元
        mock_parser.parsed_result.metadata = {
            'og': {'title': long_title},
            'meta': {},
            'page': {},
            'dc': {},
        }
        mock_parser_class.return_value = mock_parser

        result = fetch_og_data('https://example.com')

        assert len(result.title) == 500

    @patch('shortener.og_parser.socket.getaddrinfo', new=_fake_getaddrinfo)
    @patch('shortener.og_parser.requests.Session')
    def test_blocks_redirect_to_private_ip(self, mock_session_class):
        """重定向到私有 IP 應被阻擋（起始 host 解析為公開、重定向目標為私有）"""
        mock_session = MagicMock()
        mock_session_class.return_value.__enter__.return_value = mock_session

        # 模擬 301 重定向到私有 IP
        mock_response = MagicMock()
        mock_response.status_code = 301
        mock_response.headers = {'Location': 'http://192.168.1.1/admin'}
        mock_session.get.return_value = mock_response

        with pytest.raises(SSRFBlockedError):
            fetch_og_data('https://evil-site.com')


class TestOGDataClass:
    """OGData 資料類測試"""

    def test_is_empty_when_no_data(self):
        """無資料時 is_empty 為 True"""
        og = OGData()
        assert og.is_empty is True

    def test_not_empty_with_title(self):
        """有標題時 is_empty 為 False"""
        og = OGData(title='Test')
        assert og.is_empty is False

    def test_not_empty_with_image(self):
        """有圖片時 is_empty 為 False"""
        og = OGData(image='https://example.com/img.jpg')
        assert og.is_empty is False
