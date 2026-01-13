"""
Open Graph Parser 單元測試

使用 unittest.mock 模擬外部 HTTP 請求
"""

import pytest
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


class TestURLSecurityValidation:
    """URL 安全驗證測試"""

    def test_valid_https_url(self):
        """有效的 HTTPS URL 應通過驗證"""
        _validate_url_security('https://example.com')  # 不應拋出異常

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


class TestFetchOGData:
    """OG 資料抓取測試"""

    @patch('shortener.og_parser.metadata_parser.MetadataParser')
    def test_successful_fetch(self, mock_parser_class):
        """成功抓取 OG 資料"""
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

    @patch('shortener.og_parser.metadata_parser.MetadataParser')
    def test_fallback_to_meta_tags(self, mock_parser_class):
        """無 OG 標籤時退回使用 meta 標籤"""
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

    @patch('shortener.og_parser.metadata_parser.MetadataParser')
    def test_handles_timeout(self, mock_parser_class):
        """處理請求超時"""
        mock_parser_class.side_effect = Exception('Connection timed out')

        with pytest.raises(FetchTimeoutError):
            fetch_og_data('https://slow-site.com')

    @patch('shortener.og_parser.metadata_parser.MetadataParser')
    def test_handles_parse_error(self, mock_parser_class):
        """處理解析錯誤"""
        import metadata_parser

        mock_parser_class.side_effect = metadata_parser.NotParsableFetchError('404')

        with pytest.raises(OGParserError):
            fetch_og_data('https://example.com/404')

    def test_blocks_ssrf_attempts(self):
        """SSRF 攻擊應被阻擋（不需要 mock）"""
        with pytest.raises(SSRFBlockedError):
            fetch_og_data('http://192.168.1.1/admin')

    @patch('shortener.og_parser.metadata_parser.MetadataParser')
    def test_truncates_long_content(self, mock_parser_class):
        """截斷過長的內容"""
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
