"""
非同步 OG 預覽（Django-Q）相關測試

涵蓋：
- enqueue_preview_fetch：設為 pending 並排入正確的任務
- run_preview_fetch：背景任務實際抓取與寫入、刪除安全
- preview_status_view：dashboard 輪詢用的狀態端點（session 認證）
"""

import pytest
from unittest.mock import patch

from shortener import services
from shortener.models import Link, LinkPreview
from shortener.og_parser import OGData


@pytest.mark.django_db
class TestEnqueuePreviewFetch:
    """enqueue_preview_fetch 行為"""

    def test_sets_pending_and_enqueues_correct_task(self, test_user):
        """應把 preview 設為 pending，並以 link.id 排入 run_preview_fetch"""
        link = Link.objects.create(
            original_url='https://example.com',
            short_code='enq001',
            owner=test_user,
        )

        # 內層 patch 覆蓋 conftest 的同步 fixture：只驗證「入列」，不實際執行
        with patch('shortener.services.async_task') as mock_async:
            services.enqueue_preview_fetch(link)

        preview = LinkPreview.objects.get(link=link)
        assert preview.fetch_status == LinkPreview.FetchStatus.PENDING

        mock_async.assert_called_once()
        args = mock_async.call_args.args
        assert args[0] == 'shortener.services.run_preview_fetch'
        assert args[1] == link.id

    def test_resets_existing_preview_to_pending(self, test_user):
        """既有的 failed preview 重新入列時應被重設為 pending"""
        link = Link.objects.create(
            original_url='https://example.com',
            short_code='enq002',
            owner=test_user,
        )
        LinkPreview.objects.create(
            link=link,
            fetch_status=LinkPreview.FetchStatus.FAILED,
            fetch_error='舊錯誤',
        )

        with patch('shortener.services.async_task'):
            services.enqueue_preview_fetch(link)

        preview = LinkPreview.objects.get(link=link)
        assert preview.fetch_status == LinkPreview.FetchStatus.PENDING
        assert preview.fetch_error == ''


@pytest.mark.django_db
class TestRunPreviewFetchTask:
    """run_preview_fetch 背景任務"""

    @patch('shortener.services.fetch_og_data')
    def test_fetches_and_saves(self, mock_fetch, test_user):
        mock_fetch.return_value = OGData(title='背景標題', description='背景描述')
        link = Link.objects.create(
            original_url='https://example.com',
            short_code='task01',
            owner=test_user,
        )

        services.run_preview_fetch(link.id)

        preview = LinkPreview.objects.get(link=link)
        assert preview.fetch_status == LinkPreview.FetchStatus.SUCCESS
        assert preview.og_title == '背景標題'

    def test_missing_link_is_safe(self, db):
        """連結在排程後被刪除：任務應安全略過、不拋例外"""
        services.run_preview_fetch(999999)


@pytest.mark.django_db
class TestPreviewStatusView:
    """preview_status_view 狀態端點（dashboard 輪詢用）"""

    def test_owner_gets_status_and_html(self, authenticated_client, authenticated_user):
        link = Link.objects.create(
            original_url='https://example.com',
            short_code='stat01',
            owner=authenticated_user,
        )
        LinkPreview.objects.create(
            link=link,
            og_title='你好預覽',
            fetch_status=LinkPreview.FetchStatus.SUCCESS,
        )

        res = authenticated_client.get(f'/links/{link.short_code}/preview-status/')

        assert res.status_code == 200
        data = res.json()
        assert data['status'] == 'success'
        assert '你好預覽' in data['html']

    def test_pending_status(self, authenticated_client, authenticated_user):
        link = Link.objects.create(
            original_url='https://example.com',
            short_code='stat02',
            owner=authenticated_user,
        )
        LinkPreview.objects.create(
            link=link,
            fetch_status=LinkPreview.FetchStatus.PENDING,
        )

        res = authenticated_client.get(f'/links/{link.short_code}/preview-status/')

        assert res.status_code == 200
        assert res.json()['status'] == 'pending'

    def test_status_none_when_no_preview(self, authenticated_client, authenticated_user):
        link = Link.objects.create(
            original_url='https://example.com',
            short_code='stat03',
            owner=authenticated_user,
        )

        res = authenticated_client.get(f'/links/{link.short_code}/preview-status/')

        assert res.status_code == 200
        assert res.json()['status'] == 'none'

    def test_non_owner_forbidden(self, authenticated_client, other_user):
        link = Link.objects.create(
            original_url='https://example.com',
            short_code='stat04',
            owner=other_user,
        )

        res = authenticated_client.get(f'/links/{link.short_code}/preview-status/')

        assert res.status_code == 403
        assert res.json() == {'detail': '您沒有權限查看此連結'}

    def test_requires_login(self, client):
        res = client.get('/links/whatever/preview-status/')
        assert res.status_code == 302  # @login_required 導向登入頁
