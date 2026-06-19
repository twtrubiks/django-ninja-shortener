"""
Service 層核心邏輯與例外路徑測試

補上 create_short_link 兩條過去零覆蓋的例外分支：
- 自訂 slug 撞名 → SlugAlreadyExistsError
- 自動短碼生成遇非預期唯一約束衝突 → ShortCodeGenerationError（並驗證 atomic 回滾）
"""

from unittest.mock import patch

import pytest

from shortener.models import Link
from shortener.services import (
    ShortCodeGenerationError,
    SlugAlreadyExistsError,
    create_short_link,
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

    def test_auto_short_code_collision_raises_generation_error(self, test_user):
        """
        自動短碼路徑若撞上既有 short_code（理論上不該發生），
        應轉為 ShortCodeGenerationError，且 atomic 區塊回滾不留半成品。
        """
        Link.objects.create(
            original_url='https://example.com/existing',
            short_code='taken01',
            is_custom_slug=False,
            owner=test_user,
        )

        # 強制自動生成回傳已存在的短碼 → save 觸發真實 IntegrityError
        with patch('shortener.services.generate_short_code_from_id', return_value='taken01'):
            with pytest.raises(ShortCodeGenerationError):
                create_short_link(
                    original_url='https://example.com/new',
                    owner=test_user,
                )

        # atomic 應已回滾：既有那筆仍在、半成品（short_code=NULL 的新列）不留存
        assert Link.objects.filter(short_code='taken01').count() == 1
        assert Link.objects.filter(original_url='https://example.com/new').count() == 0
