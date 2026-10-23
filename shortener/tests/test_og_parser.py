"""
Open Graph Parser 單元測試

使用 unittest.mock 模擬外部 HTTP 請求
"""

import io
import ipaddress
import socket

import metadata_parser
import pytest
import requests
from unittest.mock import MagicMock, patch

from shortener.og_parser import (
    MAX_REDIRECTS,
    MAX_RESPONSE_BYTES,
    OGData,
    OGParserError,
    SSRFBlockedError,
    FetchTimeoutError,
    InvalidURLError,
    _fetch_with_safe_redirects,
    _is_ip_blocked,
    _read_capped_body,
    _safe_get_from_metadata,
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
        with pytest.raises(InvalidURLError, match='^不支援的協議: file$'):
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

    def test_blocks_public_hostname_resolving_to_cgnat_metadata(self):
        """公開域名解析到 CGNAT 範圍的 metadata 服務（阿里雲 100.100.100.200）也要擋"""
        def resolver(host, port, *args, **kwargs):
            return [(
                socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP,
                '', ('100.100.100.200', port),
            )]

        with patch('shortener.og_parser.socket.getaddrinfo', new=resolver):
            with pytest.raises(SSRFBlockedError, match='100.100.100.200'):
                _validate_url_security('http://metadata.example.com/latest/meta-data/')

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
            with pytest.raises(InvalidURLError, match='^無法解析主機名 no-such-host.invalid: '):
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
        mock_response.iter_content.return_value = [b'<html></html>']
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
        mock_response.iter_content.return_value = [b'<html></html>']
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
        mock_response.iter_content.return_value = [b'<html></html>']
        mock_response.url = 'https://example.com/404'
        mock_get.return_value = mock_response

        mock_parser_class.side_effect = metadata_parser.NotParsableFetchError('404')

        with pytest.raises(OGParserError, match='^無法解析網頁: '):
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
        mock_response.iter_content.return_value = [b'<html></html>']
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
        """無資料時 is_empty 為 True，且各欄位預設為空字串"""
        og = OGData()
        assert og.is_empty is True
        assert (og.title, og.description, og.image, og.site_name, og.og_type) == ('', '', '', '', '')

    def test_not_empty_with_title(self):
        """有標題時 is_empty 為 False"""
        og = OGData(title='Test')
        assert og.is_empty is False

    def test_not_empty_with_image(self):
        """有圖片時 is_empty 為 False"""
        og = OGData(image='https://example.com/img.jpg')
        assert og.is_empty is False


class TestResponseSizeLimit:
    """回應大小上限：防解壓縮炸彈 / 超大 body 撐爆背景 worker 記憶體。

    iter_content 產出的是「已解壓」位元組，故以這些測試模擬「解壓後」的串流，
    驗證 _read_capped_body 在跨過上限時截斷、不會無限累積。
    """

    def test_caps_oversized_body(self):
        """解壓後總量超過上限時，主體應被截斷到 MAX_RESPONSE_BYTES"""
        mock_response = MagicMock()
        # 逐塊吐出，總和略超過上限
        n_chunks = (MAX_RESPONSE_BYTES // 8192) + 10
        mock_response.iter_content.return_value = [b'a' * 8192] * n_chunks

        _read_capped_body(mock_response)

        assert len(mock_response._content) == MAX_RESPONSE_BYTES
        assert mock_response._content_consumed is True
        # 跨過上限即停止迭代，連線應被關閉
        mock_response.close.assert_called_once()

    def test_decompression_bomb_single_huge_chunk(self):
        """單一超巨塊（高壓縮比炸彈解出）也應被截斷，不會原樣保留整塊"""
        mock_response = MagicMock()
        # 一個 chunk 就遠超上限，模擬炸彈解壓後的單塊
        mock_response.iter_content.return_value = [b'x' * (5 * 1024 * 1024)]

        _read_capped_body(mock_response)

        assert len(mock_response._content) == MAX_RESPONSE_BYTES

    def test_multiple_chunks_joined_verbatim(self):
        """多個小 chunk 原樣串接（不夾任何分隔字元）"""
        mock_response = MagicMock()
        mock_response.iter_content.return_value = [b'<html>', b'<head>', b'</head></html>']

        _read_capped_body(mock_response)

        assert mock_response._content == b'<html><head></head></html>'

    def test_stops_reading_once_limit_reached(self):
        """累計到上限就停止向串流要資料，不會把後面的 chunk 也讀進來"""
        consumed = []

        def stream():
            for i in range(10):
                consumed.append(i)
                yield b'a' * (MAX_RESPONSE_BYTES // 4)

        mock_response = MagicMock()
        mock_response.iter_content.return_value = stream()

        _read_capped_body(mock_response)

        assert consumed == [0, 1, 2, 3]
        assert len(mock_response._content) == MAX_RESPONSE_BYTES

    def test_limit_counts_cumulative_bytes(self):
        """上限以累計位元組計算：差 1 byte 未達上限時仍會再讀下一塊"""
        mock_response = MagicMock()
        mock_response.iter_content.return_value = [b'a' * (MAX_RESPONSE_BYTES - 1), b'b' * 10]

        _read_capped_body(mock_response)

        assert mock_response._content == b'a' * (MAX_RESPONSE_BYTES - 1) + b'b'

    def test_small_body_not_truncated(self):
        """未超過上限的正常回應應原樣保留"""
        body = b'<html><head><title>ok</title></head></html>'
        mock_response = MagicMock()
        mock_response.iter_content.return_value = [body]

        _read_capped_body(mock_response)

        assert mock_response._content == body
        assert mock_response._content_consumed is True

    @patch('shortener.og_parser.socket.getaddrinfo', new=_fake_getaddrinfo)
    @patch('shortener.og_parser.metadata_parser.MetadataParser')
    @patch('shortener.og_parser.requests.Session.get')
    def test_fetch_truncates_oversized_response(self, mock_get, mock_parser_class):
        """端到端：超大回應不應拋錯，截斷後仍照常解析 OG"""
        oversized_html = b'<html>' + b'A' * (MAX_RESPONSE_BYTES + 100_000)
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.url = 'https://example.com'
        mock_response.iter_content.return_value = [oversized_html]
        mock_get.return_value = mock_response

        mock_parser = MagicMock()
        mock_parser.parsed_result.metadata = {
            'og': {'title': 'Big Page'},
            'meta': {},
            'page': {},
            'dc': {},
        }
        mock_parser_class.return_value = mock_parser

        result = fetch_og_data('https://example.com')

        # 截斷後 _content 不超過上限
        assert len(mock_response._content) == MAX_RESPONSE_BYTES
        assert result.title == 'Big Page'


def _ok_response(url='https://example.com', body=b'<html></html>'):
    """模擬一個 200、可被 _read_capped_body 讀取的回應"""
    response = MagicMock()
    response.status_code = 200
    response.url = url
    response.iter_content.return_value = [body]
    return response


def _real_response(url='https://example.com', body=b'<html></html>'):
    """真實的 requests.Response（body 走 raw 串流），讓 response.text 照常解碼"""
    response = requests.Response()
    response.status_code = 200
    response.url = url
    response.raw = io.BytesIO(body)
    return response


def _redirect_response(status, location):
    response = MagicMock()
    response.status_code = status
    response.headers = {'Location': location} if location is not None else {}
    return response


class TestIsIpBlocked:
    """單一 IP 判定：每一類禁止範圍各自有代表，公開位址（含 IPv6 包裝）必須放行"""

    @pytest.mark.parametrize('ip, blocked', [
        ('93.184.216.34', False),           # 公開 IPv4
        ('2606:4700:4700::1111', False),    # 公開 IPv6
        ('::ffff:8.8.8.8', False),          # IPv4-mapped 公開位址
        ('2002:808:808::1', False),         # 6to4 包裝的公開位址（8.8.8.8）需拆解後放行
        ('10.0.0.1', True),                 # private
        ('127.0.0.1', True),                # loopback
        ('::1', True),                      # IPv6 loopback
        ('fe80::1%eth0', True),             # link-local + scope id
        ('224.0.0.1', True),                # multicast（非 private，需靠 is_multicast 擋）
        ('100.64.0.1', True),               # CGNAT 共享位址（非 private / reserved，靠 is_global 擋）
        ('100.100.100.200', True),          # 阿里雲 metadata 服務
        ('::ffff:100.100.100.200', True),   # 同上，IPv4-mapped 包裝
        ('2002:c0a8:101::1', True),         # 6to4 包裝的 192.168.1.1
        ('not-an-ip', True),                # 無法解析 → 保守視為不可信
    ])
    def test_classification(self, ip, blocked):
        assert _is_ip_blocked(ip) is blocked


class TestValidateUrlSecurityEdgeCases:
    """URL 解析邊界：缺主機名、格式錯誤、連接埠、多筆解析結果"""

    def test_missing_hostname(self):
        with pytest.raises(InvalidURLError, match='^URL 缺少主機名$'):
            _validate_url_security('http:///path-only')

    def test_unparsable_url(self):
        """urlparse 對未閉合的 IPv6 會拋 ValueError，需轉成 InvalidURLError"""
        with pytest.raises(InvalidURLError, match='無法解析 URL'):
            _validate_url_security('http://[::1/broken')

    @patch('shortener.og_parser.socket.getaddrinfo', new=_fake_getaddrinfo)
    def test_scheme_is_case_insensitive(self):
        _validate_url_security('HTTPS://example.com/')  # 不應拋出異常

    @pytest.mark.parametrize('url, expected_port', [
        ('http://example.com/', 80),
        ('https://example.com/', 443),
        ('https://example.com:8443/', 8443),
    ])
    def test_resolves_with_effective_port(self, url, expected_port):
        """以實際連線會用的連接埠解析（預設 80 / 443，或 URL 指定的連接埠）"""
        calls = []

        def resolver(host, port, *args, **kwargs):
            calls.append((host, port))
            return _fake_getaddrinfo(host, port)

        with patch('shortener.og_parser.socket.getaddrinfo', new=resolver):
            _validate_url_security(url)

        assert calls == [('example.com', expected_port)]

    @pytest.mark.parametrize('host', ['localhost', 'LOCALHOST', 'localhost.localdomain', 'local'])
    @patch('shortener.og_parser.socket.getaddrinfo', new=_fake_getaddrinfo)
    def test_blocked_hostnames_even_if_resolved_public(self, host):
        """主機名黑名單是獨立的一層：就算 DNS 被竄改成回公開 IP 也照擋"""
        with pytest.raises(SSRFBlockedError, match='禁止存取內部主機'):
            _validate_url_security(f'http://{host}/')

    def test_any_blocked_address_among_results_blocks(self):
        """解析出多個 IP 時，只要其中一個是內網就擋（不能只看第一筆）"""
        def resolver(host, port, *args, **kwargs):
            return [
                (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, '', ('93.184.216.34', port)),
                (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, '', ('10.0.0.8', port)),
            ]

        with patch('shortener.og_parser.socket.getaddrinfo', new=resolver):
            with pytest.raises(SSRFBlockedError, match='10.0.0.8'):
                _validate_url_security('http://dual.example.com/')


@patch('shortener.og_parser.socket.getaddrinfo', new=_fake_getaddrinfo)
class TestSafeRedirects:
    """手動跟隨重定向：逐跳重驗、相對路徑、次數上限、請求參數"""

    @pytest.mark.parametrize('status', [301, 302, 303, 307, 308])
    def test_follows_each_redirect_status(self, status):
        with patch('shortener.og_parser.requests.Session.get') as mock_get:
            mock_get.side_effect = [
                _redirect_response(status, 'https://example.com/final'),
                _ok_response('https://example.com/final'),
            ]
            response = _fetch_with_safe_redirects('https://example.com/start', timeout=5)

        assert response.url == 'https://example.com/final'
        assert [c.args[0] for c in mock_get.call_args_list] == [
            'https://example.com/start',
            'https://example.com/final',
        ]

    def test_relative_location_resolved_against_current_url(self):
        with patch('shortener.og_parser.requests.Session.get') as mock_get:
            mock_get.side_effect = [
                _redirect_response(302, '/next?x=1'),
                _ok_response('https://example.com/next?x=1'),
            ]
            _fetch_with_safe_redirects('https://example.com/a/b', timeout=5)

        assert mock_get.call_args_list[1].args[0] == 'https://example.com/next?x=1'

    def test_redirect_without_location_raises(self):
        with patch('shortener.og_parser.requests.Session.get') as mock_get:
            mock_get.return_value = _redirect_response(302, None)
            with pytest.raises(OGParserError, match='^重定向缺少 Location header$'):
                _fetch_with_safe_redirects('https://example.com/', timeout=5)

    def test_too_many_redirects_raises(self):
        """連續重定向超過 MAX_REDIRECTS 次即放棄，且不會多送請求"""
        with patch('shortener.og_parser.requests.Session.get') as mock_get:
            mock_get.return_value = _redirect_response(302, 'https://example.com/loop')
            with pytest.raises(OGParserError, match=f'超過最大重定向次數 \\({MAX_REDIRECTS}\\)'):
                _fetch_with_safe_redirects('https://example.com/', timeout=5)

        assert mock_get.call_count == MAX_REDIRECTS

    def test_request_options(self):
        """不讓 requests 自動跟隨重定向、串流讀取、帶逾時與自訂 User-Agent"""
        with patch('shortener.og_parser.requests.Session') as mock_session_class:
            session = mock_session_class.return_value.__enter__.return_value
            session.get.return_value = _ok_response()
            _fetch_with_safe_redirects('https://example.com/', timeout=7)

        session.headers.update.assert_called_once_with({
            'User-Agent': 'Mozilla/5.0 (compatible; ShortenerBot/1.0; '
                          '+https://github.com/twtrubiks/django-ninja-shortener)'
        })
        session.get.assert_called_once_with(
            'https://example.com/', timeout=7, allow_redirects=False, stream=True
        )

    def test_redirect_response_closed(self):
        redirect = _redirect_response(302, 'https://example.com/final')
        with patch('shortener.og_parser.requests.Session.get') as mock_get:
            mock_get.side_effect = [redirect, _ok_response('https://example.com/final')]
            _fetch_with_safe_redirects('https://example.com/', timeout=5)

        redirect.close.assert_called_once()


@patch('shortener.og_parser.socket.getaddrinfo', new=_fake_getaddrinfo)
class TestFetchOGDataExtra:
    """fetch_og_data 的整合解析、逾時上限、截斷與例外轉換"""

    HTML = (
        b'<html><head><title>Page Title</title>'
        b'<meta property="og:title" content="OG Title">'
        b'<meta property="og:description" content="OG Desc">'
        b'<meta property="og:image" content="https://example.com/i.png">'
        b'<meta property="og:site_name" content="Example">'
        b'<meta property="og:type" content="article">'
        b'</head><body></body></html>'
    )

    def test_real_html_parsed(self):
        """不 mock metadata_parser：以真實 HTML 驗證各欄位對應"""
        with patch('shortener.og_parser.requests.Session.get') as mock_get:
            mock_get.return_value = _real_response(body=self.HTML)
            result = fetch_og_data('https://example.com')

        assert result == OGData(
            title='OG Title',
            description='OG Desc',
            image='https://example.com/i.png',
            site_name='Example',
            og_type='article',
        )

    def test_page_title_and_meta_description_fallback(self):
        html = (
            b'<html><head><title>Only Title</title>'
            b'<meta name="description" content="Only Desc"></head></html>'
        )
        with patch('shortener.og_parser.requests.Session.get') as mock_get:
            mock_get.return_value = _real_response(body=html)
            result = fetch_og_data('https://example.com')

        assert result.title == 'Only Title'
        assert result.description == 'Only Desc'
        assert result.image == result.site_name == result.og_type == ''

    def test_empty_head_yields_empty_ogdata(self):
        """完全沒有任何 meta / title 時，各欄位都是空字串（不是 None 或其他預設值）"""
        with patch('shortener.og_parser.requests.Session.get') as mock_get:
            mock_get.return_value = _real_response(body=b'<html><head></head><body></body></html>')
            result = fetch_og_data('https://example.com')

        assert result == OGData()

    @pytest.mark.parametrize('timeout, expected', [(None, 5), (10, 10), (100, 30)])
    def test_timeout_default_and_cap(self, timeout, expected):
        with patch('shortener.og_parser._fetch_with_safe_redirects') as mock_fetch:
            response = _real_response(body=self.HTML)
            _read_capped_body(response)
            mock_fetch.return_value = response
            if timeout is None:
                fetch_og_data('https://example.com')
            else:
                fetch_og_data('https://example.com', timeout=timeout)

        mock_fetch.assert_called_once_with('https://example.com', expected)

    @patch('shortener.og_parser.metadata_parser.MetadataParser')
    def test_all_fields_truncated_to_model_limits(self, mock_parser_class):
        mock_parser_class.return_value.parsed_result.metadata = {
            'og': {
                'title': 'T' * 600,
                'description': 'D' * 2100,
                'image': 'I' * 2100,
                'site_name': 'S' * 300,
                'type': 'Y' * 150,
            },
        }
        with patch('shortener.og_parser.requests.Session.get') as mock_get:
            mock_get.return_value = _ok_response()
            result = fetch_og_data('https://example.com')

        assert (len(result.title), len(result.description), len(result.image)) == (500, 2000, 2000)
        assert (len(result.site_name), len(result.og_type)) == (200, 100)

    def test_connection_error_wrapped(self):
        with patch('shortener.og_parser.requests.Session.get') as mock_get:
            mock_get.side_effect = requests.exceptions.ConnectionError('refused')
            with pytest.raises(OGParserError, match='無法連線') as exc_info:
                fetch_og_data('https://example.com')

        assert type(exc_info.value) is OGParserError

    @patch('shortener.og_parser.metadata_parser.MetadataParser')
    def test_unexpected_error_wrapped(self, mock_parser_class):
        mock_parser_class.side_effect = RuntimeError('boom')
        with patch('shortener.og_parser.requests.Session.get') as mock_get:
            mock_get.return_value = _ok_response()
            with pytest.raises(OGParserError, match='解析錯誤: boom'):
                fetch_og_data('https://example.com')

    def test_timeout_error_message(self):
        with patch('shortener.og_parser.requests.Session.get') as mock_get:
            mock_get.side_effect = requests.exceptions.Timeout()
            with pytest.raises(FetchTimeoutError, match='請求超時: https://slow.example.com'):
                fetch_og_data('https://slow.example.com')

    def test_invalid_url_error_not_rewrapped(self):
        """安全相關錯誤原樣拋出，呼叫端才能區分（而非被包成一般 OGParserError）"""
        with pytest.raises(InvalidURLError):
            fetch_og_data('ftp://example.com/file')


class TestSafeGetFromMetadata:
    """metadata 字典取值：og → meta → page 的優先序、list 取第一筆、空值退回預設"""

    @pytest.mark.parametrize('metadata, key, expected', [
        ({'og': {'title': ['First', 'Second']}}, 'og:title', 'First'),
        ({'og': {'title': []}}, 'og:title', 'dflt'),
        ({'og': {'title': ''}}, 'og:title', 'dflt'),
        ({'og': {}, 'meta': {'og:title': 'From Meta'}}, 'og:title', 'From Meta'),
        ({'meta': {'description': ['M1', 'M2']}}, 'description', 'M1'),
        ({'meta': {'description': []}}, 'description', 'dflt'),
        ({'meta': {'description': ''}}, 'description', 'dflt'),
        ({'page': {'title': ['P1', 'P2']}}, 'title', 'P1'),
        ({'page': {'title': []}}, 'title', 'dflt'),
        ({'page': {'title': None}}, 'title', 'dflt'),
        ({'og': {'title': 'OG'}, 'meta': {'og:title': 'META'}}, 'og:title', 'OG'),
        ({}, 'og:title', 'dflt'),
        ({'og': None}, 'og:title', 'dflt'),  # 結構異常不拋例外
    ])
    def test_lookup(self, metadata, key, expected):
        assert _safe_get_from_metadata(metadata, key, 'dflt') == expected

    def test_default_is_empty_string(self):
        assert _safe_get_from_metadata({}, 'og:title') == ''
