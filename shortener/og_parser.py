"""
Open Graph 資料解析模組

使用 metadata_parser 套件抓取網頁的 OG meta 標籤
"""

import logging
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import metadata_parser
import requests

logger = logging.getLogger(__name__)

# 設定常數
DEFAULT_TIMEOUT = 5  # 秒
MAX_TIMEOUT = 30
MAX_REDIRECTS = 5  # 最大重定向次數
USER_AGENT = (
    'Mozilla/5.0 (compatible; ShortenerBot/1.0; '
    '+https://github.com/twtrubiks/django-ninja-shortener)'
)

# 阻擋的私有 IP 範圍 (SSRF 防護)
BLOCKED_IP_PREFIXES = (
    '10.',
    '172.16.',
    '172.17.',
    '172.18.',
    '172.19.',
    '172.20.',
    '172.21.',
    '172.22.',
    '172.23.',
    '172.24.',
    '172.25.',
    '172.26.',
    '172.27.',
    '172.28.',
    '172.29.',
    '172.30.',
    '172.31.',
    '192.168.',
    '127.',
    '0.',
    '169.254.',  # link-local
)

BLOCKED_HOSTNAMES = (
    'localhost',
    'localhost.localdomain',
    'local',
)


@dataclass
class OGData:
    """Open Graph 資料結構"""

    title: str = ''
    description: str = ''
    image: str = ''
    site_name: str = ''
    og_type: str = ''

    @property
    def is_empty(self) -> bool:
        return not any([self.title, self.description, self.image])


class OGParserError(Exception):
    """OG 解析錯誤基類"""

    pass


class SSRFBlockedError(OGParserError):
    """SSRF 安全阻擋錯誤"""

    pass


class FetchTimeoutError(OGParserError):
    """抓取超時錯誤"""

    pass


class InvalidURLError(OGParserError):
    """無效 URL 錯誤"""

    pass


def _validate_url_security(url: str) -> None:
    """
    驗證 URL 安全性，防止 SSRF 攻擊

    Args:
        url: 要驗證的 URL

    Raises:
        SSRFBlockedError: 如果 URL 指向私有/內部網路
        InvalidURLError: 如果 URL 格式無效
    """
    try:
        parsed = urlparse(url)
    except Exception as e:
        raise InvalidURLError(f'無法解析 URL: {e}')

    # 檢查協議
    if parsed.scheme.lower() not in ('http', 'https'):
        raise InvalidURLError(f'不支援的協議: {parsed.scheme}')

    hostname = parsed.hostname
    if not hostname:
        raise InvalidURLError('URL 缺少主機名')

    # 檢查被阻擋的主機名
    hostname_lower = hostname.lower()
    if hostname_lower in BLOCKED_HOSTNAMES:
        raise SSRFBlockedError(f'禁止存取內部主機: {hostname}')

    # 檢查 IP 位址
    if any(hostname.startswith(prefix) for prefix in BLOCKED_IP_PREFIXES):
        raise SSRFBlockedError(f'禁止存取私有 IP 範圍: {hostname}')

    # 檢查 IPv6 localhost
    if hostname in ('::', '::1'):
        raise SSRFBlockedError('禁止存取 IPv6 localhost')


def _fetch_with_safe_redirects(url: str, timeout: int) -> requests.Response:
    """
    安全地抓取 URL，驗證每個重定向目標以防止 DNS 重綁定攻擊

    Args:
        url: 目標 URL
        timeout: 請求超時時間（秒）

    Returns:
        requests.Response: HTTP 回應

    Raises:
        SSRFBlockedError: 如果重定向目標指向私有網路
        OGParserError: 超過最大重定向次數或其他錯誤
    """
    with requests.Session() as session:
        session.headers.update({'User-Agent': USER_AGENT})

        current_url = url
        for _ in range(MAX_REDIRECTS):
            # 驗證當前 URL 的安全性
            _validate_url_security(current_url)

            response = session.get(
                current_url,
                timeout=timeout,
                allow_redirects=False,
            )

            # 如果不是重定向，返回回應
            if response.status_code not in (301, 302, 303, 307, 308):
                return response

            # 取得重定向目標
            location = response.headers.get('Location')
            if not location:
                raise OGParserError('重定向缺少 Location header')

            # 處理相對 URL
            current_url = urljoin(current_url, location)

        raise OGParserError(f'超過最大重定向次數 ({MAX_REDIRECTS})')


def _safe_get_from_metadata(metadata: dict, key: str, default: str = '') -> str:
    """
    從 metadata 字典中安全取得值

    metadata 結構範例：
    {
        'og': {'title': '...', 'image': '...'},
        'meta': {'og:title': '...', 'description': '...'},
        'page': {'title': '...'},
        'dc': {}
    }
    """
    try:
        # 嘗試從 og 區塊取得（不帶 og: 前綴）
        og_key = key.replace('og:', '') if key.startswith('og:') else key
        if 'og' in metadata and og_key in metadata['og']:
            value = metadata['og'][og_key]
            if isinstance(value, list):
                return value[0] if value else default
            return value or default

        # 嘗試從 meta 區塊取得（帶 og: 前綴）
        if 'meta' in metadata and key in metadata['meta']:
            value = metadata['meta'][key]
            if isinstance(value, list):
                return value[0] if value else default
            return value or default

        # 嘗試從 page 區塊取得
        if 'page' in metadata and key in metadata['page']:
            value = metadata['page'][key]
            if isinstance(value, list):
                return value[0] if value else default
            return value or default

        return default
    except Exception:
        return default


def fetch_og_data(
    url: str,
    timeout: int = DEFAULT_TIMEOUT,
) -> OGData:
    """
    抓取指定 URL 的 Open Graph 資料

    Args:
        url: 目標網頁 URL
        timeout: 請求超時時間（秒），預設 5 秒，最大 30 秒

    Returns:
        OGData: 包含 OG 資料的資料結構

    Raises:
        SSRFBlockedError: URL 指向私有網路
        FetchTimeoutError: 請求超時
        OGParserError: 其他解析錯誤
    """
    # 限制超時時間
    timeout = min(timeout, MAX_TIMEOUT)

    try:
        # 使用安全重定向處理抓取 HTML
        response = _fetch_with_safe_redirects(url, timeout)

        # 使用 metadata_parser 解析已抓取的 HTML
        page = metadata_parser.MetadataParser(
            html=response.text,
            url=response.url,
            search_head_only=True,  # 只搜索 <head>，提升效能
            support_malformed=True,  # 處理格式錯誤的 HTML
            strategy=['page', 'meta', 'og', 'dc'],  # 嘗試多種策略
        )

        # 從 parsed_result 取得 metadata 字典
        metadata = page.parsed_result.metadata

        # 提取 OG 資料
        og_data = OGData(
            title=(
                _safe_get_from_metadata(metadata, 'og:title')
                or _safe_get_from_metadata(metadata, 'title', '')
                or ''
            ),
            description=(
                _safe_get_from_metadata(metadata, 'og:description')
                or _safe_get_from_metadata(metadata, 'description', '')
                or ''
            ),
            image=_safe_get_from_metadata(metadata, 'og:image') or '',
            site_name=_safe_get_from_metadata(metadata, 'og:site_name') or '',
            og_type=_safe_get_from_metadata(metadata, 'og:type') or '',
        )

        # 截斷過長的內容
        og_data.title = og_data.title[:500] if og_data.title else ''
        og_data.description = og_data.description[:2000] if og_data.description else ''

        logger.info(f'Successfully fetched OG data for {url}')
        return og_data

    except requests.exceptions.Timeout:
        logger.warning(f'Timeout fetching {url}')
        raise FetchTimeoutError(f'請求超時: {url}')

    except requests.exceptions.ConnectionError as e:
        logger.warning(f'Connection error fetching {url}: {e}')
        raise OGParserError(f'無法連線: {e}')

    except (SSRFBlockedError, InvalidURLError):
        # 重新拋出安全相關錯誤
        raise

    except metadata_parser.NotParsableFetchError as e:
        logger.warning(f'Failed to parse {url}: {e}')
        raise OGParserError(f'無法解析網頁: {e}')

    except Exception as e:
        logger.exception(f'Unexpected error fetching OG data for {url}')
        raise OGParserError(f'解析錯誤: {e}')
