import re
from urllib.parse import urlparse

from django.conf import settings
from django.core.exceptions import ValidationError

ALLOWED_SCHEMES = {'http', 'https'}

# Slug 格式正規表達式：英數字和連字號，不能以連字號開頭或結尾
SLUG_PATTERN = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9-]*[a-zA-Z0-9]$|^[a-zA-Z0-9]$')


def validate_url_scheme(url: str) -> str:
    """驗證 URL 協議，只允許 http 和 https"""
    parsed = urlparse(url)
    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise ValidationError(
            f"不允許的 URL 協議: {parsed.scheme}。只允許 http 和 https。"
        )
    return url


def validate_custom_slug(slug: str) -> str:
    """
    驗證自訂 slug 格式。

    Args:
        slug: 使用者提供的自訂 slug

    Returns:
        正規化後的 slug（小寫）

    Raises:
        ValueError: 驗證失敗
    """
    if slug is None:
        return slug

    # 轉換為小寫並去除空白
    slug = slug.strip().lower()

    # 長度驗證：3-50 字元
    if len(slug) < 3:
        raise ValueError('自訂網址必須至少 3 個字元')
    if len(slug) > 50:
        raise ValueError('自訂網址不得超過 50 個字元')

    # 格式驗證：英數字和連字號，不能以連字號開頭或結尾
    if not SLUG_PATTERN.match(slug):
        raise ValueError(
            '自訂網址只能包含英文字母、數字和連字號，且不能以連字號開頭或結尾'
        )

    # 連續連字號檢查
    if '--' in slug:
        raise ValueError('自訂網址不能包含連續的連字號')

    # 保留字檢查
    if slug in settings.RESERVED_SLUGS:
        raise ValueError(f'「{slug}」是系統保留字，請使用其他名稱')

    return slug
