"""
LinkPreview Model 單元測試
"""

import pytest
from django.db import IntegrityError

from shortener.models import Link, LinkPreview


@pytest.mark.django_db
class TestLinkPreviewModel:
    """LinkPreview 模型測試"""

    def test_create_preview(self):
        """測試建立預覽記錄"""
        link = Link.objects.create(
            original_url='https://example.com',
            short_code='testprev',
        )

        preview = LinkPreview.objects.create(
            link=link,
            og_title='Test Title',
            og_description='Test Description',
            og_image='https://example.com/img.jpg',
            fetch_status=LinkPreview.FetchStatus.SUCCESS,
        )

        assert preview.link == link
        assert preview.og_title == 'Test Title'
        assert preview.fetch_status == 'success'
        assert preview.has_preview_data is True

    def test_one_to_one_relationship(self):
        """測試一對一關聯"""
        link = Link.objects.create(
            original_url='https://example.com',
            short_code='onetoone',
        )

        LinkPreview.objects.create(link=link)

        # 嘗試建立第二個 preview 應失敗
        with pytest.raises(IntegrityError):
            LinkPreview.objects.create(link=link)

    def test_has_preview_data_false_when_empty(self):
        """無資料時 has_preview_data 為 False"""
        link = Link.objects.create(
            original_url='https://example.com',
            short_code='empty',
        )

        preview = LinkPreview.objects.create(link=link)

        assert preview.has_preview_data is False

    @pytest.mark.parametrize('field, value', [
        ('og_title', 'Only Title'),
        ('og_description', 'Only Description'),
        ('og_image', 'https://example.com/only.jpg'),
    ])
    def test_has_preview_data_with_any_single_field(self, field, value):
        """標題、描述、圖片任一有值即視為有預覽資料"""
        link = Link.objects.create(
            original_url='https://example.com',
            short_code=f'single-{field}',
        )

        preview = LinkPreview.objects.create(link=link, **{field: value})

        assert preview.has_preview_data is True

    def test_cascade_delete(self):
        """刪除 Link 時應一併刪除 Preview"""
        link = Link.objects.create(
            original_url='https://example.com',
            short_code='cascade',
        )
        LinkPreview.objects.create(link=link)

        link_pk = link.pk
        link.delete()

        assert not LinkPreview.objects.filter(link_id=link_pk).exists()

    def test_str_representation(self):
        """測試字串表示"""
        link = Link.objects.create(
            original_url='https://example.com',
            short_code='strtest',
        )
        preview = LinkPreview.objects.create(
            link=link,
            fetch_status=LinkPreview.FetchStatus.SUCCESS,
        )

        assert 'strtest' in str(preview)
        assert 'success' in str(preview)

    def test_fetch_status_choices(self):
        """測試抓取狀態選項"""
        link = Link.objects.create(
            original_url='https://example.com',
            short_code='statuses',
        )

        # 測試各種狀態
        for status in [
            LinkPreview.FetchStatus.PENDING,
            LinkPreview.FetchStatus.SUCCESS,
            LinkPreview.FetchStatus.FAILED,
        ]:
            preview = LinkPreview.objects.create(link=link, fetch_status=status)
            preview.delete()
            # 重新建立 link 以避免 unique 約束
            link.delete()
            link = Link.objects.create(
                original_url='https://example.com',
                short_code=f'status{status}',
            )

    def test_preview_with_all_og_fields(self):
        """測試填寫所有 OG 欄位"""
        link = Link.objects.create(
            original_url='https://example.com',
            short_code='allfields',
        )

        preview = LinkPreview.objects.create(
            link=link,
            og_title='Full Title',
            og_description='Full Description',
            og_image='https://example.com/img.jpg',
            og_site_name='Example Site',
            og_type='website',
            fetch_status=LinkPreview.FetchStatus.SUCCESS,
        )

        assert preview.og_title == 'Full Title'
        assert preview.og_description == 'Full Description'
        assert preview.og_image == 'https://example.com/img.jpg'
        assert preview.og_site_name == 'Example Site'
        assert preview.og_type == 'website'
        assert preview.has_preview_data is True

    def test_related_name_access(self):
        """測試從 Link 存取 preview"""
        link = Link.objects.create(
            original_url='https://example.com',
            short_code='related',
        )

        preview = LinkPreview.objects.create(
            link=link,
            og_title='Related Test',
        )

        # 透過 related_name 存取
        assert link.preview == preview
        assert link.preview.og_title == 'Related Test'
