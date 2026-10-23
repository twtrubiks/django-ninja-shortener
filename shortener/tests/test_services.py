"""
Service 層核心邏輯與例外路徑測試

補上 create_short_link 兩條過去零覆蓋的例外分支：
- 自訂 slug 撞名 → SlugAlreadyExistsError
- 自動短碼首次撞唯一約束 → retry 一次自癒
- 自動短碼 retry 後仍衝突 → ShortCodeGenerationError（並驗證 atomic 回滾）
"""

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from shortener.models import Link, LinkPreview
from shortener.og_parser import OGData, OGParserError
from shortener.services import (
    ShortCodeGenerationError,
    SlugAlreadyExistsError,
    create_short_link,
    fetch_and_save_preview,
)


@pytest.mark.django_db
class TestCreateShortLink:
    """create_short_link 行為與例外路徑"""

    def test_custom_slug_is_used_as_short_code(self, test_user):
        """自訂 slug 應直接作為 short_code，並標記 is_custom_slug"""
        link = create_short_link(
            original_url='https://example.com',
            owner=test_user,
            custom_slug='mycustom',
        )
        assert link.short_code == 'mycustom'
        assert link.is_custom_slug is True
        assert link.owner == test_user

    def test_auto_generated_short_code(self, test_user):
        """未給 slug 時應以 DB id 自動生成非空短碼"""
        link = create_short_link(
            original_url='https://example.com',
            owner=test_user,
        )
        assert link.short_code
        assert link.is_custom_slug is False

    def test_duplicate_custom_slug_raises_slug_exists(self, test_user):
        """相同自訂 slug 第二次建立應拋 SlugAlreadyExistsError，且不留殘骸"""
        create_short_link(
            original_url='https://example.com/1',
            owner=test_user,
            custom_slug='dup',
        )

        with pytest.raises(SlugAlreadyExistsError) as exc_info:
            create_short_link(
                original_url='https://example.com/2',
                owner=test_user,
                custom_slug='dup',
            )

        assert exc_info.value.slug == 'dup'
        assert Link.objects.filter(short_code='dup').count() == 1

    def test_auto_short_code_collision_retries_and_succeeds(self, test_user):
        """
        自動短碼首次撞上既有 short_code（例如恰好等於某 ID 編碼結果的自訂 slug）時，
        應 retry 一次並以新 ID 生成的短碼成功建立。
        """
        Link.objects.create(
            original_url='https://example.com/existing',
            short_code='taken01',
            is_custom_slug=True,
            owner=test_user,
        )

        # 第一次生成撞名，retry 拿到新短碼
        with patch(
            'shortener.services.generate_short_code_from_id',
            side_effect=['taken01', 'fresh002'],
        ):
            link = create_short_link(
                original_url='https://example.com/new',
                owner=test_user,
            )

        assert link.short_code == 'fresh002'
        assert link.is_custom_slug is False
        # 首次失敗的半成品已回滾，最終只留一筆新連結
        assert Link.objects.filter(original_url='https://example.com/new').count() == 1

    def test_auto_short_code_collision_raises_generation_error(self, test_user):
        """
        自動短碼路徑若 retry 一次後仍撞上既有 short_code（理論上不該發生），
        應轉為 ShortCodeGenerationError，且 atomic 區塊回滾不留半成品。
        """
        Link.objects.create(
            original_url='https://example.com/existing',
            short_code='taken01',
            is_custom_slug=False,
            owner=test_user,
        )

        # 強制自動生成回傳已存在的短碼 → save 觸發真實 IntegrityError
        with patch(
            'shortener.services.generate_short_code_from_id', return_value='taken01'
        ) as mock_generate:
            with pytest.raises(ShortCodeGenerationError):
                create_short_link(
                    original_url='https://example.com/new',
                    owner=test_user,
                )

        # 只 retry 一次（共嘗試兩次）
        assert mock_generate.call_count == 2

        # atomic 應已回滾：既有那筆仍在、半成品（short_code=NULL 的新列）不留存
        assert Link.objects.filter(short_code='taken01').count() == 1
        assert Link.objects.filter(original_url='https://example.com/new').count() == 0

    @pytest.mark.parametrize('custom_slug', ['persisted', None])
    def test_fields_persisted(self, test_user, custom_slug):
        """自訂 / 自動兩條路徑都要把目標網址、擁有者、過期時間寫進資料庫"""
        expires_at = timezone.now() + timedelta(days=1)

        link = create_short_link(
            original_url='https://example.com/persist',
            owner=test_user,
            custom_slug=custom_slug,
            expires_at=expires_at,
        )

        link.refresh_from_db()
        assert link.original_url == 'https://example.com/persist'
        assert link.owner == test_user
        assert link.expires_at == expires_at

    def test_slug_exists_error_message(self):
        assert str(SlugAlreadyExistsError('dup')) == '網址「dup」已被使用'


@pytest.mark.django_db
class TestFetchAndSavePreview:
    """fetch_and_save_preview：成功 / 失敗時寫入 preview 的欄位"""

    @pytest.fixture
    def link(self, test_user):
        return Link.objects.create(
            original_url='https://example.com/page', short_code='fsp001', owner=test_user
        )

    def test_success_saves_all_fields(self, link):
        LinkPreview.objects.create(
            link=link, fetch_status=LinkPreview.FetchStatus.FAILED, fetch_error='舊錯誤'
        )
        og = OGData(title='T', description='D', image='https://example.com/i.png',
                    site_name='S', og_type='article')

        with patch('shortener.services.fetch_og_data', return_value=og) as mock_fetch:
            returned = fetch_and_save_preview(link)

        mock_fetch.assert_called_once_with('https://example.com/page')
        preview = LinkPreview.objects.get(link=link)
        assert returned == preview
        assert (preview.og_title, preview.og_description, preview.og_image) == (
            'T', 'D', 'https://example.com/i.png'
        )
        assert (preview.og_site_name, preview.og_type) == ('S', 'article')
        assert preview.fetch_status == LinkPreview.FetchStatus.SUCCESS
        assert preview.fetch_error == ''
        assert preview.fetched_at is not None

    def test_failure_records_error(self, link):
        with patch('shortener.services.fetch_og_data', side_effect=OGParserError('壞掉了')):
            returned = fetch_and_save_preview(link)

        preview = LinkPreview.objects.get(link=link)
        assert returned == preview
        assert preview.fetch_status == LinkPreview.FetchStatus.FAILED
        assert preview.fetch_error == '壞掉了'
        assert preview.fetched_at is None
