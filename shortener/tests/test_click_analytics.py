"""點擊分析（ClickEvent / 統計頁）測試"""

from datetime import datetime, time, timedelta, timezone as dt_timezone
from unittest.mock import patch

import pytest
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
