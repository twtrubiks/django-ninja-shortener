"""點擊分析（ClickEvent / 統計頁）測試"""

from datetime import datetime, time, timedelta, timezone as dt_timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.contrib.messages import get_messages
from django.utils import timezone

from ua_parser import parse

from shortener.analytics import (
    DISPLAY_TIMEZONE,
    _device_category,
    _referrer_domain,
    get_link_stats,
)
from shortener.models import ClickEvent, Link
from shortener.services import cleanup_old_click_events

DESKTOP_UA = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
)
MOBILE_UA = (
    'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 '
    '(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1'
)
BOT_UA = 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)'
ANDROID_PHONE_UA = (
    'Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36'
)


@pytest.fixture
def owned_link(db, test_user):
    return Link.objects.create(
        original_url='https://example.com',
        short_code='statlink',
        owner=test_user,
    )


# =============================================================================
# 轉址時的事件記錄
# =============================================================================


class TestRedirectRecordsClick:
    def test_redirect_creates_event_with_parsed_fields(self, client, owned_link):
        response = client.get(
            '/statlink',
            HTTP_USER_AGENT=DESKTOP_UA,
            HTTP_REFERER='https://Google.com/search?q=x',
        )

        assert response.status_code == 302
        event = ClickEvent.objects.get(link=owned_link)
        assert event.referrer_domain == 'google.com'
        assert event.device == 'desktop'
        assert event.browser == 'Chrome'
        assert event.is_bot is False

    def test_mobile_ua_parsed(self, client, owned_link):
        client.get('/statlink', HTTP_USER_AGENT=MOBILE_UA)

        event = ClickEvent.objects.get(link=owned_link)
        assert event.device == 'mobile'
        assert event.os == 'iOS'

    def test_bot_ua_marked(self, client, owned_link):
        client.get('/statlink', HTTP_USER_AGENT=BOT_UA)

        event = ClickEvent.objects.get(link=owned_link)
        assert event.is_bot is True
        assert event.device == 'bot'

    def test_no_referrer_stored_as_empty(self, client, owned_link):
        client.get('/statlink', HTTP_USER_AGENT=DESKTOP_UA)

        event = ClickEvent.objects.get(link=owned_link)
        assert event.referrer_domain == ''

    def test_overlong_referrer_truncated(self, client, owned_link):
        long_referrer = 'https://' + 'a' * 300 + '.com/path'
        client.get('/statlink', HTTP_USER_AGENT=DESKTOP_UA, HTTP_REFERER=long_referrer)

        event = ClickEvent.objects.get(link=owned_link)
        assert len(event.referrer_domain) == 200

    def test_missing_user_agent_recorded_as_other(self, client, owned_link):
        """沒有 User-Agent 標頭也要照常記錄（各欄位落到 Other / other）"""
        client.get('/statlink')

        event = ClickEvent.objects.get(link=owned_link)
        assert (event.device, event.browser, event.os, event.is_bot) == ('other', 'Other', 'Other', False)
        assert event.referrer_domain == ''

    def test_android_phone_recorded_as_mobile(self, client, owned_link):
        """Android 手機（UA 含 Mobile）經轉址記錄為 mobile，而非平板"""
        client.get('/statlink', HTTP_USER_AGENT=ANDROID_PHONE_UA)

        event = ClickEvent.objects.get(link=owned_link)
        assert event.device == 'mobile'
        assert event.os == 'Android'

    def test_unparsable_referrer_stored_as_empty(self, client, owned_link):
        """Referer 是 client 可控字串，解析失敗時記為空字串而不是讓事件寫入失敗"""
        client.get('/statlink', HTTP_USER_AGENT=DESKTOP_UA, HTTP_REFERER='http://[::1')

        event = ClickEvent.objects.get(link=owned_link)
        assert event.referrer_domain == ''

    def test_overlong_family_names_truncated(self, client, owned_link):
        """瀏覽器 / OS 名稱超過欄位長度時截斷到 50 字元，事件照常寫入"""
        long_name = 'X' * 80
        fake = SimpleNamespace(
            user_agent=SimpleNamespace(family=long_name),
            os=SimpleNamespace(family=long_name),
            device=SimpleNamespace(family='Other'),
        )
        with patch('shortener.analytics.parse_user_agent', return_value=fake):
            client.get('/statlink', HTTP_USER_AGENT='custom')

        event = ClickEvent.objects.get(link=owned_link)
        assert event.browser == 'X' * 50
        assert event.os == 'X' * 50

    def test_anonymous_link_records_no_event(self, client, db):
        Link.objects.create(original_url='https://example.com', short_code='anonlink')

        response = client.get('/anonlink', HTTP_USER_AGENT=DESKTOP_UA)

        assert response.status_code == 302
        assert ClickEvent.objects.count() == 0
        # click_count 照常累計
        assert Link.objects.get(short_code='anonlink').click_count == 1

    def test_expired_link_records_no_event(self, client, owned_link):
        owned_link.expires_at = timezone.now() - timedelta(hours=1)
        owned_link.save(update_fields=['expires_at'])

        response = client.get('/statlink', HTTP_USER_AGENT=DESKTOP_UA)

        assert response.status_code == 410
        assert ClickEvent.objects.count() == 0

    def test_event_write_failure_does_not_break_redirect(self, client, owned_link):
        with patch(
            'shortener.analytics.ClickEvent.objects.create',
            side_effect=RuntimeError('db down'),
        ):
            response = client.get('/statlink', HTTP_USER_AGENT=DESKTOP_UA)

        assert response.status_code == 302
        assert response.url == 'https://example.com'
        # click_count 不受影響
        assert Link.objects.get(pk=owned_link.pk).click_count == 1


class TestDeviceCategory:
    """轉址測試已涵蓋 desktop/mobile/bot，這裡補齊 tablet 與 other 分支"""

    @pytest.mark.parametrize(
        'ua_string, expected',
        [
            # iPad：device family 比對
            (
                'Mozilla/5.0 (iPad; CPU OS 16_6 like Mac OS X) AppleWebKit/605.1.15 '
                '(KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1',
                'tablet',
            ),
            # Android 平板：UA 不含 'Mobile' 字樣
            (
                'Mozilla/5.0 (Linux; Android 13; SM-X710) AppleWebKit/537.36 '
                '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'tablet',
            ),
            ('curl/8.5.0', 'other'),
            ('', 'other'),
        ],
    )
    def test_classification(self, ua_string, expected):
        assert _device_category(parse(ua_string), ua_string) == expected


    @pytest.mark.parametrize(
        'ua_string, expected',
        [
            # _MOBILE_OS_FAMILIES
            ('Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 '
             '(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36', 'mobile'),
            ('Mozilla/5.0 (compatible; MSIE 10.0; Windows Phone 8.0; Trident/6.0; '
             'IEMobile/10.0; ARM; Touch; NOKIA; Lumia 920)', 'mobile'),
            ('Mozilla/5.0 (Mobile; Nokia_8110_4G; rv:48.0) Gecko/48.0 Firefox/48.0 KAIOS/2.5',
             'mobile'),
            ('Mozilla/5.0 (SymbianOS/9.4; Series60/5.0 NokiaN97-1/12.0.024; Profile/MIDP-2.1 '
             'Configuration/CLDC-1.1; en-us) AppleWebKit/525 (KHTML, like Gecko) '
             'BrowserNG/7.1.18124', 'mobile'),
            ('Mozilla/5.0 (BlackBerry; U; BlackBerry 9900; en) AppleWebKit/534.11+ '
             '(KHTML, like Gecko) Version/7.1.0.346 Mobile Safari/534.11+', 'mobile'),
            # _DESKTOP_OS_FAMILIES（Windows 走前綴比對）
            ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 '
             '(KHTML, like Gecko) Version/17.0 Safari/605.1.15', 'desktop'),
            ('Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
             '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36', 'desktop'),
            ('Mozilla/5.0 (X11; CrOS x86_64 14541.0.0) AppleWebKit/537.36 '
             '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36', 'desktop'),
            ('Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0',
             'desktop'),
            ('Mozilla/5.0 (X11; Fedora; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0',
             'desktop'),
            ('Mozilla/5.0 (X11; Debian; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0',
             'desktop'),
            ('Mozilla/5.0 (X11; FreeBSD amd64; rv:120.0) Gecko/20100101 Firefox/120.0',
             'desktop'),
            ('Mozilla/5.0 (X11; SunOS i86pc; rv:91.0) Gecko/20100101 Firefox/91.0', 'desktop'),
            ('Mozilla/4.0 (compatible; MSIE 8.0; Windows NT 5.1; Trident/4.0)', 'desktop'),
            # _TABLET_DEVICE_FAMILIES（Kindle Fire 的 UA 含 Mobile，靠 device family 判定）
            ('Mozilla/5.0 (X11; U; Linux armv7l like Android; en-us) AppleWebKit/531.2+ '
             '(KHTML, like Gecko) Version/5.0 Safari/531.2+ Kindle/3.0+', 'tablet'),
            ('Mozilla/5.0 (Linux; U; Android 2.3.4; en-us; Kindle Fire Build/GINGERBREAD) '
             'AppleWebKit/533.1 (KHTML, like Gecko) Version/4.0 Mobile Safari/533.1', 'tablet'),
            ('Mozilla/5.0 (Linux; U; Android 4.0.3; en-us; KFTT Build/IML74K) '
             'AppleWebKit/535.19 (KHTML, like Gecko) Silk/3.4 Mobile Safari/535.19 '
             'Silk-Accelerated=true', 'tablet'),
            # device family 含 'Tablet'
            ('Mozilla/5.0 (Linux; Android 9; Lenovo TB-X505F Tablet) AppleWebKit/537.36 '
             '(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36', 'tablet'),
        ],
    )
    def test_family_tables(self, ua_string, expected):
        """各 OS / 裝置 family 清單的每一項都要對到正確分類"""
        assert _device_category(parse(ua_string), ua_string) == expected


class TestReferrerDomain:
    @pytest.mark.parametrize(
        'referrer, expected',
        [
            ('https://google.com/search?q=x', 'google.com'),
            ('https://T.CO/abc', 't.co'),
            # userinfo 與 port 都不入庫，避免偽造 Referer 夾帶帳密、同網域被 port 拆列
            ('https://alice:s3cret@evil.com:8443/x', 'evil.com'),
            ('http://localhost:3000/page', 'localhost'),
            ('not a url', ''),
            ('http://[::1', ''),  # urlparse 拋 ValueError
            ('', ''),
        ],
    )
    def test_extraction(self, referrer, expected):
        assert _referrer_domain(referrer) == expected


# =============================================================================
# 統計聚合
# =============================================================================


class TestGetLinkStats:
    def test_timeseries_zero_filled_and_bucketed(self, owned_link):
        now = timezone.now()
        ClickEvent.objects.create(link=owned_link, clicked_at=now)
        ClickEvent.objects.create(link=owned_link, clicked_at=now)
        ClickEvent.objects.create(link=owned_link, clicked_at=now - timedelta(days=3))

        stats = get_link_stats(owned_link)

        assert len(stats['timeseries']) == 30
        assert stats['total_clicks'] == 3
        per_date = {row['date']: row['clicks'] for row in stats['timeseries']}
        today = now.astimezone(DISPLAY_TIMEZONE).date()
        three_days_ago = (now - timedelta(days=3)).astimezone(DISPLAY_TIMEZONE).date()
        assert per_date[today.isoformat()] == 2
        assert per_date[three_days_ago.isoformat()] == 1

    def test_day_bucketing_uses_display_timezone(self, owned_link):
        """UTC 昨天 23:30 = 台北今天 07:30，必須算進「今天」"""
        taipei_today = timezone.now().astimezone(DISPLAY_TIMEZONE).date()
        utc_dt = datetime.combine(
            taipei_today - timedelta(days=1), time(23, 30), tzinfo=dt_timezone.utc
        )
        ClickEvent.objects.create(link=owned_link, clicked_at=utc_dt)

        stats = get_link_stats(owned_link)

        per_date = {row['date']: row['clicks'] for row in stats['timeseries']}
        assert per_date[taipei_today.isoformat()] == 1
        assert per_date[(taipei_today - timedelta(days=1)).isoformat()] == 0

    def test_day_bucketing_independent_of_time_zone_setting(self, owned_link, settings):
        """切日固定用台北時區，不受 settings.TIME_ZONE 影響。

        刻意不引用 DISPLAY_TIMEZONE 計算期望值：否則常數被改壞時，測試的期望值會跟著
        一起變，永遠驗不出錯。UTC 1/10 20:00 = 台北 1/11 04:00，必須算進 1/11。
        """
        settings.TIME_ZONE = 'UTC'
        fixed_now = datetime(2026, 1, 10, 20, 0, tzinfo=dt_timezone.utc)
        ClickEvent.objects.create(link=owned_link, clicked_at=fixed_now)
        # 視窗起點是台北 12/13 00:00（= UTC 12/12 16:00）：台北 12/13 01:00 要算進第一天、
        # 台北 12/12 23:00 則在視窗外
        ClickEvent.objects.create(
            link=owned_link, clicked_at=datetime(2025, 12, 12, 17, 0, tzinfo=dt_timezone.utc)
        )
        ClickEvent.objects.create(
            link=owned_link, clicked_at=datetime(2025, 12, 12, 15, 0, tzinfo=dt_timezone.utc)
        )

        with patch('shortener.analytics.timezone.now', return_value=fixed_now):
            stats = get_link_stats(owned_link)

        assert stats['timeseries'][-1] == {'date': '2026-01-11', 'clicks': 1}
        assert stats['timeseries'][0] == {'date': '2025-12-13', 'clicks': 1}
        assert stats['total_clicks'] == 2

    def test_old_events_outside_window_excluded(self, owned_link):
        ClickEvent.objects.create(
            link=owned_link, clicked_at=timezone.now() - timedelta(days=45)
        )

        stats = get_link_stats(owned_link)

        assert stats['total_clicks'] == 0

    def test_bots_excluded_from_charts_but_counted(self, owned_link):
        ClickEvent.objects.create(
            link=owned_link, referrer_domain='google.com', device='desktop'
        )
        ClickEvent.objects.create(link=owned_link, device='bot', is_bot=True)

        stats = get_link_stats(owned_link)

        assert stats['total_clicks'] == 1
        assert stats['bot_clicks'] == 1
        assert all(r['domain'] != '（直接開啟）' or r['clicks'] == 0 for r in stats['referrers'])
        assert [d['label'] for d in stats['devices']] == ['桌面裝置']

    def test_bot_and_human_counts_are_separate(self, owned_link):
        """人類與 bot 數量不同時各自計數正確（避免兩者恰好相等而互相掩蓋）"""
        for _ in range(3):
            ClickEvent.objects.create(link=owned_link, device='desktop')
        ClickEvent.objects.create(link=owned_link, device='bot', is_bot=True)

        stats = get_link_stats(owned_link)

        assert stats['total_clicks'] == 3
        assert stats['bot_clicks'] == 1
        assert stats['days'] == 30

    def test_top_referrers_limited_to_10(self, owned_link):
        """來源只列前 10 名，依點擊數排序"""
        for i in range(11):
            for _ in range(i + 1):
                ClickEvent.objects.create(link=owned_link, referrer_domain=f'site{i}.com')

        referrers = get_link_stats(owned_link)['referrers']

        assert len(referrers) == 10
        assert referrers[0] == {'domain': 'site10.com', 'clicks': 11}
        assert 'site0.com' not in [r['domain'] for r in referrers]

    def test_device_labels(self, owned_link):
        """裝置分佈以中文標籤呈現，未知類別原樣顯示"""
        for device in ['desktop', 'mobile', 'mobile', 'tablet', 'other', 'tv']:
            ClickEvent.objects.create(link=owned_link, device=device)

        stats = get_link_stats(owned_link)

        labels = {d['label']: d['clicks'] for d in stats['devices']}
        assert labels == {'桌面裝置': 1, '手機': 2, '平板': 1, '其他': 1, 'tv': 1}
        assert stats['devices'][0] == {'label': '手機', 'clicks': 2}

    def test_empty_referrer_grouped_as_direct(self, owned_link):
        ClickEvent.objects.create(link=owned_link, referrer_domain='')
        ClickEvent.objects.create(link=owned_link, referrer_domain='google.com')
        ClickEvent.objects.create(link=owned_link, referrer_domain='google.com')

        stats = get_link_stats(owned_link)

        assert stats['referrers'][0] == {'domain': 'google.com', 'clicks': 2}
        assert stats['referrers'][1] == {'domain': '（直接開啟）', 'clicks': 1}

    def test_other_links_events_not_included(self, owned_link, other_user):
        other_link = Link.objects.create(
            original_url='https://other.com', short_code='otherlink', owner=other_user
        )
        ClickEvent.objects.create(link=other_link)

        stats = get_link_stats(owned_link)

        assert stats['total_clicks'] == 0


# =============================================================================
# 統計頁權限
# =============================================================================


class TestLinkStatsView:
    def test_owner_sees_stats_page(self, authenticated_client, authenticated_user):
        link = Link.objects.create(
            original_url='https://example.com', short_code='mylink', owner=authenticated_user
        )
        ClickEvent.objects.create(link=link, referrer_domain='google.com', device='desktop')

        response = authenticated_client.get('/links/mylink/stats/')

        assert response.status_code == 200
        assert response.context['stats']['total_clicks'] == 1

    def test_last_clicked_at_rendered_in_display_timezone(
        self, authenticated_client, authenticated_user
    ):
        """UTC 昨天 23:30 = 台北今天 07:30，磁磚須與圖表同用台北時區顯示"""
        taipei_today = timezone.now().astimezone(DISPLAY_TIMEZONE).date()
        utc_dt = datetime.combine(
            taipei_today - timedelta(days=1), time(23, 30), tzinfo=dt_timezone.utc
        )
        Link.objects.create(
            original_url='https://example.com',
            short_code='mylink',
            owner=authenticated_user,
            last_clicked_at=utc_dt,
        )

        response = authenticated_client.get('/links/mylink/stats/')

        content = response.content.decode()
        assert f'{taipei_today.isoformat()} 07:30' in content
        assert '23:30' not in content

    def test_non_owner_redirected(self, authenticated_client, other_user):
        Link.objects.create(
            original_url='https://example.com', short_code='notmine', owner=other_user
        )

        response = authenticated_client.get('/links/notmine/stats/')

        assert response.status_code == 302
        assert response.url == '/dashboard/'
        assert [str(m) for m in get_messages(response.wsgi_request)] == ['您沒有權限查看此連結']

    def test_anonymous_redirected_to_login(self, client, owned_link):
        response = client.get('/links/statlink/stats/')

        assert response.status_code == 302
        # 專案未設 LOGIN_URL，login_required 導向 Django 預設（與既有測試一致）
        assert response.url.startswith('/accounts/login/')

    def test_unknown_short_code_404(self, authenticated_client):
        response = authenticated_client.get('/links/nosuchlink/stats/')

        assert response.status_code == 404


# =============================================================================
# 清理排程任務
# =============================================================================


class TestCleanupOldClickEvents:
    def test_deletes_only_expired_events(self, owned_link):
        old = ClickEvent.objects.create(
            link=owned_link, clicked_at=timezone.now() - timedelta(days=91)
        )
        recent = ClickEvent.objects.create(link=owned_link)

        deleted = cleanup_old_click_events()

        assert deleted == 1
        assert not ClickEvent.objects.filter(pk=old.pk).exists()
        assert ClickEvent.objects.filter(pk=recent.pk).exists()

    def test_retention_boundary_is_90_days(self, owned_link):
        """保留 90 天：89 天前的事件保留、90 天又 1 小時前的事件刪除"""
        kept = ClickEvent.objects.create(
            link=owned_link, clicked_at=timezone.now() - timedelta(days=89)
        )
        expired = ClickEvent.objects.create(
            link=owned_link, clicked_at=timezone.now() - timedelta(days=90, hours=1)
        )

        assert cleanup_old_click_events() == 1
        assert ClickEvent.objects.filter(pk=kept.pk).exists()
        assert not ClickEvent.objects.filter(pk=expired.pk).exists()
