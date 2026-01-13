import uuid

from django.db import transaction
from ninja import ModelSchema, Router, Schema
from ninja_jwt.authentication import JWTAuth
from pydantic import HttpUrl

from .models import Link
from .utils import generate_short_code_from_id

router = Router(tags=["shorteners"])

# Input Schema
class ShortenRequest(Schema):
    original_url: HttpUrl

# Output Schema
class LinkSchema(ModelSchema):
    class Meta:
        model = Link
        exclude = ["id"]

@router.post("/shorten", response=LinkSchema, auth=JWTAuth())
def shorten_url(request, payload: ShortenRequest):
    # The endpoint is now protected by JWTAuth.
    # The authenticated user is available via request.user
    owner = request.user

    with transaction.atomic():
        # 先建立記錄（使用 UUID 作為暫時值，避免 unique 約束衝突）
        link = Link.objects.create(
            original_url=str(payload.original_url),
            short_code=str(uuid.uuid4())[:15],
            owner=owner
        )

        # 使用資料庫 ID 生成短碼（零碰撞）
        link.short_code = generate_short_code_from_id(link.id)
        link.save(update_fields=['short_code'])

    return link
