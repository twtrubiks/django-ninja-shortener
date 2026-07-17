"""API Key（Personal Access Token）認證。

金鑰格式：`sk_` + secrets.token_urlsafe(32)（共 46 字元）。
資料庫只存 SHA-256 雜湊（見 models.ApiKey），驗證時將來 token 雜湊後查表，
金鑰明文僅在建立當下顯示一次，可隨時於網頁管理頁撤銷。
"""

import hashlib
import secrets
from typing import Optional

from django.contrib.auth.models import User
from django.http import HttpRequest
from django.utils import timezone
from ninja_jwt.authentication import JWTAuth

from .models import ApiKey

API_KEY_PREFIX = 'sk_'


def generate_api_key() -> str:
    """產生新的 API Key 明文（sk_ 開頭）"""
    return API_KEY_PREFIX + secrets.token_urlsafe(32)


def hash_api_key(raw_key: str) -> str:
    """回傳金鑰明文的 SHA-256 十六進位雜湊（存庫與查表用）"""
    return hashlib.sha256(raw_key.encode()).hexdigest()


class ApiKeyOrJWTAuth(JWTAuth):
    """Bearer 認證：`sk_` 開頭視為長效 API Key，其餘沿用 JWT。

    兩種憑證共用 Authorization: Bearer 標頭，既有 JWT 客戶端零改動；
    API Key 驗證成功時與 JWTAuth 行為一致（設定 request.user 並回傳 user），
    AuthRateThrottle 因此照常以使用者為 key 計數。
    """

    def authenticate(self, request: HttpRequest, token: str) -> Optional[User]:
        if not token.startswith(API_KEY_PREFIX):
            return super().authenticate(request, token)

        try:
            api_key = ApiKey.objects.select_related('owner').get(
                key_hash=hash_api_key(token)
            )
        except ApiKey.DoesNotExist:
            return None

        if not api_key.owner.is_active:
            return None

        ApiKey.objects.filter(pk=api_key.pk).update(last_used_at=timezone.now())
        request.user = api_key.owner
        return api_key.owner
