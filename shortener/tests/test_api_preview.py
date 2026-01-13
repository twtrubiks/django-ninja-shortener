"""
API 端點整合測試 - OG 預覽功能
"""

import os
import pytest
from unittest.mock import patch
from django.contrib.auth.models import User
from ninja.testing import TestClient
from ninja_jwt.tokens import RefreshToken

# 避免 NinjaAPI 重複註冊問題
os.environ['NINJA_SKIP_REGISTRY'] = 'true'

from ninja_shortener.api import api
from shortener.models import Link, LinkPreview
from shortener.og_parser import OGData, OGParserError


@pytest.fixture
def test_user(db):
    """建立測試用戶"""
    return User.objects.create_user(username='testuser', password='password123')


@pytest.fixture
def authenticated_client(test_user):
    """建立已認證的測試客戶端"""
    refresh = RefreshToken.for_user(test_user)
    token = str(refresh.access_token)
    return TestClient(api, headers={'Authorization': f'Bearer {token}'})


@pytest.fixture
def other_user(db):
    """建立另一個測試用戶"""
    return User.objects.create_user(username='otheruser', password='password456')


@pytest.mark.django_db
class TestShortenWithPreview:
    """POST /shorten 端點測試"""

    @patch('shortener.api.fetch_og_data')
    def test_creates_link_with_preview_success(self, mock_fetch, authenticated_client, test_user):
        """成功建立短網址並抓取預覽"""
        mock_fetch.return_value = OGData(
            title='Test Title',
            description='Test Desc',
            image='https://example.com/img.jpg',
            site_name='Example',
            og_type='website',
        )

        response = authenticated_client.post(
            '/shorten',
            json={'original_url': 'https://example.com'},
        )

        assert response.status_code == 200
        data = response.json()

        # 驗證 Link
        assert data['short_code']
        assert 'example.com' in data['original_url']

        # 驗證 Preview
        assert data['preview'] is not None
        assert data['preview']['og_title'] == 'Test Title'
        assert data['preview']['fetch_status'] == 'success'

    @patch('shortener.api.fetch_og_data')
    def test_creates_link_even_if_preview_fails(self, mock_fetch, authenticated_client, test_user):
        """即使預覽抓取失敗，仍應建立短網址"""
        mock_fetch.side_effect = OGParserError('Connection refused')

        response = authenticated_client.post(
            '/shorten',
            json={'original_url': 'https://unreachable.com'},
        )

        assert response.status_code == 200
        data = response.json()

        # Link 應成功建立
        assert data['short_code']

        # Preview 應記錄失敗狀態
        assert data['preview']['fetch_status'] == 'failed'
        assert 'Connection refused' in data['preview']['fetch_error']


@pytest.mark.django_db
class TestRefreshPreview:
    """POST /links/{short_code}/refresh-preview 端點測試"""

    @patch('shortener.api.fetch_og_data')
    def test_owner_can_refresh_preview(self, mock_fetch, authenticated_client, test_user):
        """擁有者可以刷新預覽"""
        # 建立測試連結
        link = Link.objects.create(
            original_url='https://example.com',
            short_code='testcode',
            owner=test_user,
        )
        LinkPreview.objects.create(
            link=link,
            fetch_status=LinkPreview.FetchStatus.FAILED,
        )

        mock_fetch.return_value = OGData(title='Updated Title')

        response = authenticated_client.post(f'/links/{link.short_code}/refresh-preview')

        assert response.status_code == 200
        data = response.json()
        assert data['preview']['og_title'] == 'Updated Title'
        assert data['preview']['fetch_status'] == 'success'

    def test_non_owner_cannot_refresh(self, authenticated_client, other_user):
        """非擁有者無法刷新預覽"""
        link = Link.objects.create(
            original_url='https://example.com',
            short_code='othercode',
            owner=other_user,
        )

        response = authenticated_client.post(f'/links/{link.short_code}/refresh-preview')

        assert response.status_code == 403


@pytest.mark.django_db
class TestGetLinkDetail:
    """GET /links/{short_code} 端點測試"""

    def test_owner_can_view_link(self, authenticated_client, test_user):
        """擁有者可以查看連結詳情"""
        link = Link.objects.create(
            original_url='https://example.com',
            short_code='viewcode',
            owner=test_user,
        )
        LinkPreview.objects.create(
            link=link,
            og_title='Test',
            fetch_status=LinkPreview.FetchStatus.SUCCESS,
        )

        response = authenticated_client.get(f'/links/{link.short_code}')

        assert response.status_code == 200
        data = response.json()
        assert data['short_code'] == 'viewcode'
        assert data['preview']['og_title'] == 'Test'

    def test_non_owner_cannot_view(self, authenticated_client, other_user):
        """非擁有者無法查看連結詳情"""
        link = Link.objects.create(
            original_url='https://example.com',
            short_code='privatecode',
            owner=other_user,
        )

        response = authenticated_client.get(f'/links/{link.short_code}')

        assert response.status_code == 403

    def test_returns_404_for_nonexistent_link(self, authenticated_client):
        """不存在的連結應返回 404"""
        response = authenticated_client.get('/links/nonexistent')

        assert response.status_code == 404
