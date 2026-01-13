from urllib.parse import urlparse

from django.core.exceptions import ValidationError

ALLOWED_SCHEMES = {'http', 'https'}


def validate_url_scheme(url: str) -> str:
    """驗證 URL 協議，只允許 http 和 https"""
    parsed = urlparse(url)
    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise ValidationError(
            f"不允許的 URL 協議: {parsed.scheme}。只允許 http 和 https。"
        )
    return url
