"""
點擊分析：事件記錄與統計聚合。

設計要點：
- 事件在轉址請求內同步寫入。Django-Q 走 ORM broker（Postgres），入列本身
  就是一筆 PG INSERT，改走佇列不會更快，反而多出輪詢延遲與佇列表寫入。
- 隱私：不儲存 IP 與原始 User-Agent，只留解析後欄位。
- 清理排程放在 services.cleanup_old_click_events（不在本模組），
  讓 qcluster 不需載入 ua_parser 相依。
"""

import logging
from datetime import datetime, time, timedelta
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from django.db.models import Count
from django.db.models.functions import TruncDate
from django.utils import timezone
from ua_parser import parse as parse_user_agent

from .models import ClickEvent, Link

logger = logging.getLogger(__name__)

# 粗分類用的 family 清單；bot 依 uap-core 慣例以 device family 'Spider' 判斷
_MOBILE_OS_FAMILIES = frozenset(
    {'iOS', 'Android', 'Windows Phone', 'KaiOS', 'Symbian OS', 'BlackBerry OS'}
)
_DESKTOP_OS_FAMILIES = frozenset(
    {'Mac OS X', 'Linux', 'Chrome OS', 'Ubuntu', 'Fedora', 'Debian', 'FreeBSD', 'Solaris'}
)
_TABLET_DEVICE_FAMILIES = frozenset({'iPad', 'Kindle', 'Kindle Fire', 'Kindle Fire HD'})

# 統計頁的圖表區間（天）
STATS_DAYS = 30

# 圖表以此時區切日；明確指定而不依賴 settings.TIME_ZONE，
# 避免全域設定變動時默默改變統計的切日行為
DISPLAY_TIMEZONE = ZoneInfo('Asia/Taipei')

DEVICE_LABELS = {
    'desktop': '桌面裝置',
    'mobile': '手機',
    'tablet': '平板',
    'other': '其他',
}


def record_click(link: Link, request) -> None:
    """盡力而為地記錄一次點擊；任何失敗只記 log，絕不影響轉址。"""
    try:
        ua_string = request.META.get('HTTP_USER_AGENT', '')
        result = parse_user_agent(ua_string)
        device = _device_category(result, ua_string)
        ClickEvent.objects.create(
            link=link,
            referrer_domain=_referrer_domain(request.META.get('HTTP_REFERER', '')),
            device=device,
            browser=(result.user_agent.family if result.user_agent else 'Other')[:50],
            os=(result.os.family if result.os else 'Other')[:50],
            is_bot=device == 'bot',
        )
    except Exception:
        logger.exception('點擊事件寫入失敗：%s', link.short_code)


def _referrer_domain(referrer: str) -> str:
    """從 Referer 標頭取出網域。它是 client 可控的任意字串：解析失敗或超長都須安全落地。"""
    try:
        # hostname 而非 netloc：去除 userinfo 與 port，並自動小寫
        return (urlparse(referrer).hostname or '')[:200]
    except ValueError:
        return ''


def _device_category(result, ua_string: str) -> str:
    device = result.device.family if result.device else 'Other'
    os_family = result.os.family if result.os else 'Other'
    if device == 'Spider':
        return 'bot'
    if (
        device in _TABLET_DEVICE_FAMILIES
        or 'Tablet' in device
        # Android 慣例：平板 UA 不含 'Mobile' 字樣
        or (os_family == 'Android' and 'Mobile' not in ua_string)
    ):
        return 'tablet'
    if os_family in _MOBILE_OS_FAMILIES:
        return 'mobile'
    # Windows 用前綴比對：uap-core 對舊版會給 'Windows XP' 等獨立 family
    if os_family.startswith('Windows') or os_family in _DESKTOP_OS_FAMILIES:
        return 'desktop'
    return 'other'


def get_link_stats(link: Link) -> dict:
    """近 STATS_DAYS 天統計：每日點擊時間序列（零填充）、Top referrers、裝置分佈。

    bot 點擊不計入圖表，只另計總數供參考。
    """
    today = timezone.now().astimezone(DISPLAY_TIMEZONE).date()
    start_date = today - timedelta(days=STATS_DAYS - 1)
    window_start = datetime.combine(start_date, time.min, tzinfo=DISPLAY_TIMEZONE)

    events = ClickEvent.objects.filter(link=link, clicked_at__gte=window_start)
    humans = events.filter(is_bot=False)

    per_day = dict(
        humans.annotate(day=TruncDate('clicked_at', tzinfo=DISPLAY_TIMEZONE))
        .values('day')
        .annotate(clicks=Count('id'))
        .values_list('day', 'clicks')
    )
    timeseries = [
        {
            'date': (start_date + timedelta(days=i)).isoformat(),
            'clicks': per_day.get(start_date + timedelta(days=i), 0),
        }
        for i in range(STATS_DAYS)
    ]

    referrers = [
        {'domain': row['referrer_domain'] or '（直接開啟）', 'clicks': row['clicks']}
        for row in (
            humans.values('referrer_domain')
            .annotate(clicks=Count('id'))
            .order_by('-clicks')[:10]
        )
    ]

    devices = [
        {'label': DEVICE_LABELS.get(row['device'], row['device']), 'clicks': row['clicks']}
        for row in (
            humans.values('device')
            .annotate(clicks=Count('id'))
            .order_by('-clicks')
        )
    ]

    return {
        'days': STATS_DAYS,
        'timeseries': timeseries,
        'referrers': referrers,
        'devices': devices,
        'total_clicks': sum(per_day.values()),
        'bot_clicks': events.filter(is_bot=True).count(),
    }
