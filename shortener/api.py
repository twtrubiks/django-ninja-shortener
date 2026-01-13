import uuid
from datetime import datetime
from typing import Optional

from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import ModelSchema, Router, Schema
from ninja_jwt.authentication import JWTAuth
from pydantic import HttpUrl

from .models import Link, LinkPreview
from .og_parser import OGParserError, fetch_og_data
from .utils import generate_short_code_from_id

router = Router(tags=['shorteners'])


# ========== Input Schemas ==========


class ShortenRequest(Schema):
    original_url: HttpUrl
    expires_at: Optional[datetime] = None


# ========== Output Schemas ==========


class LinkPreviewSchema(Schema):
    """OG 預覽資料輸出"""

    og_title: str
    og_description: str
    og_image: str
    og_site_name: str
    og_type: str
    fetch_status: str
    fetch_error: str
    fetched_at: Optional[datetime]

    class Config:
        from_attributes = True


class LinkSchema(ModelSchema):
    """Link 輸出 Schema（不含預覽）"""

    class Meta:
        model = Link
        exclude = ['id']


class LinkWithPreviewSchema(Schema):
    """Link + 預覽資料的完整輸出"""

    original_url: str
    short_code: str
    owner: Optional[int]
    created_at: datetime
    click_count: int
    last_clicked_at: Optional[datetime]
    expires_at: Optional[datetime]
    preview: Optional[LinkPreviewSchema]


# ========== Helper Functions ==========


def _fetch_and_save_preview(link: Link) -> LinkPreview:
    """
    抓取 OG 資料並儲存到 LinkPreview

    Args:
        link: Link 實例

    Returns:
        LinkPreview: 建立或更新後的預覽實例
    """
    preview, _ = LinkPreview.objects.get_or_create(link=link)

    try:
        og_data = fetch_og_data(link.original_url)

        preview.og_title = og_data.title
        preview.og_description = og_data.description
        preview.og_image = og_data.image
        preview.og_site_name = og_data.site_name
        preview.og_type = og_data.og_type
        preview.fetch_status = LinkPreview.FetchStatus.SUCCESS
        preview.fetch_error = ''
        preview.fetched_at = timezone.now()

    except OGParserError as e:
        preview.fetch_status = LinkPreview.FetchStatus.FAILED
        preview.fetch_error = str(e)

    preview.save()
    return preview


def _link_to_response(link: Link) -> dict:
    """將 Link 轉換為 API 回應格式"""
    preview_data = None
    try:
        preview = link.preview
        preview_data = {
            'og_title': preview.og_title,
            'og_description': preview.og_description,
            'og_image': preview.og_image,
            'og_site_name': preview.og_site_name,
            'og_type': preview.og_type,
            'fetch_status': preview.fetch_status,
            'fetch_error': preview.fetch_error,
            'fetched_at': preview.fetched_at,
        }
    except LinkPreview.DoesNotExist:
        pass

    return {
        'original_url': link.original_url,
        'short_code': link.short_code,
        'owner': link.owner_id,
        'created_at': link.created_at,
        'click_count': link.click_count,
        'last_clicked_at': link.last_clicked_at,
        'expires_at': link.expires_at,
        'preview': preview_data,
    }


# ========== API Endpoints ==========


@router.post('/shorten', response=LinkWithPreviewSchema, auth=JWTAuth())
def shorten_url(request, payload: ShortenRequest):
    """
    建立短網址並同步抓取 OG 預覽資料

    - 需要 JWT 認證
    - 同步抓取目標網址的 Open Graph 資料
    - 如果抓取失敗，仍會建立短網址，但 preview.fetch_status 為 failed
    """
    owner = request.user

    with transaction.atomic():
        # 先建立記錄（使用 UUID 作為暫時值，避免 unique 約束衝突）
        link = Link.objects.create(
            original_url=str(payload.original_url),
            short_code=str(uuid.uuid4())[:15],
            owner=owner,
            expires_at=payload.expires_at,
        )

        # 使用資料庫 ID 生成短碼（零碰撞）
        link.short_code = generate_short_code_from_id(link.id)
        link.save(update_fields=['short_code'])

    # 同步抓取 OG 資料（在 transaction 外執行）
    _fetch_and_save_preview(link)

    # 重新載入 link 以取得 preview 關聯
    link.refresh_from_db()

    return _link_to_response(link)


@router.post(
    '/links/{short_code}/refresh-preview',
    response=LinkWithPreviewSchema,
    auth=JWTAuth(),
)
def refresh_link_preview(request, short_code: str):
    """
    手動重新抓取指定短網址的 OG 預覽資料

    - 需要 JWT 認證
    - 只有連結擁有者可以重新抓取
    - 會覆蓋現有的預覽資料
    """
    link = get_object_or_404(Link, short_code=short_code)

    # 權限檢查：只有擁有者可以刷新
    if link.owner != request.user:
        return JsonResponse({'detail': '您沒有權限操作此連結'}, status=403)

    # 重新抓取 OG 資料
    _fetch_and_save_preview(link)
    link.refresh_from_db()

    return _link_to_response(link)


@router.get(
    '/links/{short_code}',
    response=LinkWithPreviewSchema,
    auth=JWTAuth(),
)
def get_link_detail(request, short_code: str):
    """
    取得指定短網址的詳細資訊（含預覽）

    - 需要 JWT 認證
    - 只有連結擁有者可以查看
    """
    link = get_object_or_404(
        Link.objects.select_related('preview'),
        short_code=short_code,
    )

    if link.owner != request.user:
        return JsonResponse({'detail': '您沒有權限查看此連結'}, status=403)

    return _link_to_response(link)
