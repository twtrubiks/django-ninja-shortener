"""
Open Graph 資料解析模組

使用 metadata_parser 套件抓取網頁的 OG meta 標籤
"""

import ipaddress
import logging
import socket
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import metadata_parser
import requests

logger = logging.getLogger(__name__)

# 設定常數
DEFAULT_TIMEOUT = 5  # 秒
MAX_TIMEOUT = 30
MAX_REDIRECTS = 5  # 最大重定向次數
# 回應主體大小上限（解壓後）。防「解壓縮炸彈」與超大 body 撐爆背景 worker 記憶體：
# 目標 URL 由使用者提供，惡意站點可回傳數 KB 的 gzip 卻解壓成數 GB。OG/meta 標籤都在
# <head>，2 MiB 綽綽有餘；超出採截斷（而非整筆失敗），仍足以解析開頭的 <head>。
MAX_RESPONSE_BYTES = 2 * 1024 * 1024  # 2 MiB
USER_AGENT = (
    'Mozilla/5.0 (compatible; ShortenerBot/1.0; '
    '+https://github.com/twtrubiks/django-ninja-shortener)'
)

# SSRF 防護
#
# 重要：不可用「hostname 字串前綴」判斷是否為內網位址。字串比對會被整組繞過——
# 十進位（http://2130706433/）、hex（0x7f000001）、octal（0177.0.0.1）、
# IPv6-mapped（[::ffff:127.0.0.1]），以及「公開域名解析到內網 / 雲端 metadata」。
#
# 正確做法：用「實際連線會用到的同一個解析器」(socket.getaddrinfo) 把 hostname
# 解析成真正的 IP，再對每個 IP 做物件化的範圍檢查（見 _is_ip_blocked）。
#
# 已知限制：本模組在「驗證」與「連線」之間各做一次 DNS 解析，理論上仍存在
# DNS rebinding 的 TOCTOU 窗口（同一域名兩次解析回不同 IP）。要徹底消除需把連線
# 釘死在已驗證的 IP（自訂 HTTPAdapter）；目前以逐跳重驗 + 全 IP 檢查作為務實緩解。

# 明確封鎖的主機名（防禦縱深；真正的保護以下方 IP 解析為準）
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


def _is_ip_blocked(ip_str: str) -> bool:
    """
    判斷單一 IP 是否落在禁止存取的範圍（私有 / 迴環 / link-local / 保留等）。

    會拆解 IPv6 內嵌的 IPv4（IPv4-mapped、6to4），避免 ::ffff:127.0.0.1
    這類包裝形式繞過檢查。

    最後再以 is_global 兜底：凡不是公網位址一律擋下。像 CGNAT 共享位址
    100.64.0.0/10 不屬於上面任何一類，但雲端 metadata 服務可能就在其中
    （例如阿里雲 100.100.100.200）。multicast 的 is_global 為 True，
    故仍需保留 is_multicast 那一條，不能只靠 is_global。
    """
    # 去掉 IPv6 的 scope id（例如 fe80::1%eth0）再解析
    ip_str = ip_str.split('%')[0]

    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        # getaddrinfo 理論上只會回合法 IP；無法解析時保守視為不可信
        return True

    # 拆出 IPv6 內嵌的 IPv4 後再判斷
    if isinstance(ip, ipaddress.IPv6Address):
        mapped = ip.ipv4_mapped or ip.sixtofour
        if mapped is not None:
            ip = mapped

    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
        or not ip.is_global
    )


def _validate_url_security(url: str) -> None:
    """
    驗證 URL 安全性，防止 SSRF 攻擊。

    解析 hostname 為實際 IP（涵蓋十進位 / hex / octal 整數 IP、IPv6，以及
    公開域名解析到內網），再逐一檢查每個 IP 是否落在禁止範圍。

    Args:
        url: 要驗證的 URL

    Raises:
        SSRFBlockedError: 如果 URL 解析到私有 / 內部 / 保留位址
        InvalidURLError: 如果 URL 格式無效或主機名無法解析
    """
    try:
        parsed = urlparse(url)
    except Exception as e:
        raise InvalidURLError(f'無法解析 URL: {e}')

    # 檢查協議
    scheme = parsed.scheme.lower()
    if scheme not in ('http', 'https'):
        raise InvalidURLError(f'不支援的協議: {parsed.scheme}')

    hostname = parsed.hostname
    if not hostname:
        raise InvalidURLError('URL 缺少主機名')

    # 明確封鎖的主機名（防禦縱深）
    if hostname.lower() in BLOCKED_HOSTNAMES:
        raise SSRFBlockedError(f'禁止存取內部主機: {hostname}')

    # 用與實際連線相同的解析器解析所有候選 IP。getaddrinfo 會套用 inet_aton
    # 語意，把 2130706433 / 0x7f000001 / 0177.0.0.1 之類的整數寫法正規化成真正
    # 的 IP，並涵蓋公開域名指向內網 / 雲端 metadata 的情況。
    port = parsed.port or (443 if scheme == 'https' else 80)
    try:
        addrinfos = socket.getaddrinfo(hostname, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as e:
        raise InvalidURLError(f'無法解析主機名 {hostname}: {e}')

    for info in addrinfos:
        ip_str = info[4][0]
        if _is_ip_blocked(ip_str):
            raise SSRFBlockedError(
                f'禁止存取內部 / 保留位址: {hostname} -> {ip_str}'
            )


def _read_capped_body(response: requests.Response) -> None:
    """串流讀取回應主體並對「解壓後」大小設硬上限，就地寫回 response._content。

    為何用串流計數：requests 的 iter_content 產出的是「已解壓」位元組，逐塊累加長度
    即可在跨過上限時立刻停止——不會把整顆 gzip/deflate 解壓縮炸彈解完（DEFLATE 單次
    讀取的膨脹比約上限 1032:1，故暫態記憶體仍有界）。

    超過上限採「截斷」而非整筆失敗：OG/meta 標籤位於 <head>（解析時亦 search_head_only），
    保留開頭的 MAX_RESPONSE_BYTES 已足以取得預覽，對超大但合法的頁面更友善。

    讀畢把位元組塞回 response._content 並標記已消費，讓上層照常使用 response.text
    （沿用 requests 自身的字元集偵測）。
    """
    chunks = []
    total = 0
    truncated = False
    for chunk in response.iter_content(chunk_size=8192):
        chunks.append(chunk)
        total += len(chunk)
        if total >= MAX_RESPONSE_BYTES:
            truncated = True
            break

    response._content = b''.join(chunks)[:MAX_RESPONSE_BYTES]
    response._content_consumed = True
    response.close()

    if truncated:
        logger.info(
            f'Response body from {response.url} exceeded '
            f'{MAX_RESPONSE_BYTES} bytes; truncated for OG parsing'
        )


def _fetch_with_safe_redirects(url: str, timeout: int) -> requests.Response:
    """
    安全地抓取 URL，對「起始 URL 與每一次重定向目標」都重新做 SSRF 驗證。

    注意：驗證與實際連線各自解析一次 DNS，無法完全防止單一 hostname 的 DNS
    rebinding；徹底防護需把連線釘死在已驗證的 IP（見 _validate_url_security 註解）。

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

            # stream=True：先不把 body 讀進記憶體，改由 _read_capped_body 設限讀取，
            # 避免 requests 在此處就把（可能是解壓縮炸彈的）整包 body 載入。
            response = session.get(
                current_url,
                timeout=timeout,
                allow_redirects=False,
                stream=True,
            )

            # 如果不是重定向，設限讀取 body 後返回
            if response.status_code not in (301, 302, 303, 307, 308):
                _read_capped_body(response)
                return response

            # 重定向：body 未讀，主動關閉釋放連線後再跳下一跳
            location = response.headers.get('Location')
            response.close()
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

        # 截斷過長的內容（長度對齊 LinkPreview 各欄位的 max_length，
        # 避免超長值在 preview.save() 觸發 DataError 而讓狀態卡在 pending）
        og_data.title = og_data.title[:500] if og_data.title else ''
        og_data.description = og_data.description[:2000] if og_data.description else ''
        og_data.image = og_data.image[:2000] if og_data.image else ''
        og_data.site_name = og_data.site_name[:200] if og_data.site_name else ''
        og_data.og_type = og_data.og_type[:100] if og_data.og_type else ''

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
