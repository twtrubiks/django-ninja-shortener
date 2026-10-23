"""
連結列表 API（GET /api/links）測試

涵蓋：認證要求、擁有權隔離、排序、分頁與 page_size 上限
"""

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from ninja.testing import TestClient

from ninja_shortener.api import api
from shortener.models import Link, LinkPreview


@pytest.fixture
def make_links(db):
    """為指定用戶建立 n 個連結，short_code 依序為 {prefix}0..{prefix}n-1"""

    def _make(user, n, prefix='code'):
        return [
            Link.objects.create(
                original_url=f'https://example.com/{i}',
                short_code=f'{prefix}{i}',
                owner=user,
            )
            for i in range(n)
        ]

    return _make


@pytest.mark.django_db
def test_list_links_requires_auth():
    """未認證請求回 401"""
    client = TestClient(api)

    response = client.get('/links')

    assert response.status_code == 401


@pytest.mark.django_db
def test_list_links_only_returns_own_links(
    ninja_authenticated_client, test_user, other_user, make_links
):
    """只回傳自己的連結，不含他人的"""
    make_links(test_user, 2, prefix='mine')
    make_links(other_user, 3, prefix='theirs')

    response = ninja_authenticated_client.get('/links')

    assert response.status_code == 200
    data = response.json()
    assert data['count'] == 2
    assert {item['short_code'] for item in data['items']} == {'mine0', 'mine1'}
    assert all(item['owner'] == test_user.id for item in data['items'])


@pytest.mark.django_db
def test_list_links_ordered_newest_first(ninja_authenticated_client, test_user, make_links):
    """依建立時間新到舊排序"""
    make_links(test_user, 3)

    response = ninja_authenticated_client.get('/links')

    codes = [item['short_code'] for item in response.json()['items']]
    assert codes == ['code2', 'code1', 'code0']


@pytest.mark.django_db
def test_list_links_pagination(ninja_authenticated_client, test_user, make_links):
    """分頁：page_size=2 時第一頁 2 筆、第二頁 1 筆，count 皆為總數"""
    make_links(test_user, 3)

    page1 = ninja_authenticated_client.get('/links?page=1&page_size=2').json()
    page2 = ninja_authenticated_client.get('/links?page=2&page_size=2').json()

    assert page1['count'] == 3
    assert [i['short_code'] for i in page1['items']] == ['code2', 'code1']
    assert page2['count'] == 3
    assert [i['short_code'] for i in page2['items']] == ['code0']


@pytest.mark.django_db
def test_list_links_page_size_clamped(ninja_authenticated_client, test_user, make_links):
    """page_size 超過上限會被鉗制到 50；page/page_size 過小則回到下限"""
    make_links(test_user, 1)

    response = ninja_authenticated_client.get('/links?page=0&page_size=999')

    data = response.json()
    assert data['page'] == 1
    assert data['page_size'] == 50
    assert data['count'] == 1


@pytest.mark.django_db
def test_list_links_includes_preview_fields(ninja_authenticated_client, test_user, make_links):
    """回應項目含 preview 欄位（與單筆查詢端點同格式）"""
    make_links(test_user, 1)

    item = ninja_authenticated_client.get('/links').json()['items'][0]

    assert 'preview' in item
    assert item['original_url'] == 'https://example.com/0'
    assert item['click_count'] == 0


@pytest.mark.django_db
def test_list_links_default_pagination(ninja_authenticated_client, test_user, make_links):
    """未指定分頁參數時預設第 1 頁、每頁 10 筆"""
    make_links(test_user, 11)

    data = ninja_authenticated_client.get('/links').json()

    assert data['page'] == 1
    assert data['page_size'] == 10
    assert len(data['items']) == 10
    assert data['count'] == 11


@pytest.mark.django_db
def test_list_links_page_size_lower_bound(ninja_authenticated_client, test_user, make_links):
    """page_size 小於 1 時鉗制為 1"""
    make_links(test_user, 2)

    data = ninja_authenticated_client.get('/links?page_size=0').json()

    assert data['page_size'] == 1
    assert len(data['items']) == 1


@pytest.mark.django_db
def test_list_links_query_count_does_not_grow(ninja_authenticated_client, test_user, make_links):
    """preview 以 select_related 一併載入：查詢數不隨連結數量增加（無 N+1）"""
    links = make_links(test_user, 1)
    LinkPreview.objects.create(link=links[0])
    with CaptureQueriesContext(connection) as one_link:
        ninja_authenticated_client.get('/links')

    for link in make_links(test_user, 4, prefix='more'):
        LinkPreview.objects.create(link=link)
    with CaptureQueriesContext(connection) as five_links:
        ninja_authenticated_client.get('/links')

    assert len(five_links) == len(one_link)
