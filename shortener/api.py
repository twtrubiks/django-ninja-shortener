import re
from datetime import datetime
from typing import Optional

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from ninja import ModelSchema, Query, Router, Schema
from ninja_jwt.authentication import JWTAuth
from pydantic import HttpUrl, field_validator

from .models import Link, LinkPreview
from .qr_utils import generate_qr_code
from .services import (
    ShortCodeGenerationError,
    SlugAlreadyExistsError,
    create_short_link,
    fetch_and_save_preview,
)
from .validators import validate_custom_slug

router = Router(tags=['shorteners'])


# ========== Input Schemas ==========


class ShortenRequest(Schema):
    original_url: HttpUrl
    custom_slug: Optional[str] = None
    expires_at: Optional[datetime] = None

    @field_validator('custom_slug')
    @classmethod
    def validate_slug(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v.strip() == '':
            return None
        return validate_custom_slug(v)


class QRCodeParams(Schema):
    """QR Code 生成參數"""

    size: int = 256
    dark: str = "#000000"
    light: str = "#FFFFFF"

    @field_validator('size')
    @classmethod
    def validate_size(cls, v):
        if v not in (128, 256, 512):
            raise ValueError('尺寸必須是 128, 256 或 512')
        return v

    @field_validator('dark', 'light')
    @classmethod
    def validate_color(cls, v):
        if not re.match(r'^#[0-9A-Fa-f]{6}$', v):
            raise ValueError('顏色必須是有效的十六進位格式，例如 #FF0000')
        return v


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
    is_custom_slug: bool
    owner: Optional[int]
    created_at: datetime
    click_count: int
    last_clicked_at: Optional[datetime]
    expires_at: Optional[datetime]
    preview: Optional[LinkPreviewSchema]


class ErrorSchema(Schema):
    """錯誤回應格式"""

    detail: str


class LinkLimitExceededSchema(Schema):
    """連結數量超出限制回應"""

    detail: str
    current_count: int
    max_links: int


class SlugAvailabilityResponse(Schema):
    """Slug 可用性檢查回應"""

    slug: str
    available: bool
    message: str


# ========== Helper Functions ==========


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
        'is_custom_slug': link.is_custom_slug,
        'owner': link.owner_id,
        'created_at': link.created_at,
        'click_count': link.click_count,
        'last_clicked_at': link.last_clicked_at,
        'expires_at': link.expires_at,
        'preview': preview_data,
    }


# ========== API Endpoints ==========


@router.post(
    '/shorten',
    response={200: LinkWithPreviewSchema, 403: LinkLimitExceededSchema, 409: ErrorSchema, 500: ErrorSchema},
    auth=JWTAuth(),
)
def shorten_url(request, payload: ShortenRequest):
    """
    建立短網址並同步抓取 OG 預覽資料

    - 需要 JWT 認證
    - 每位用戶最多可建立 1000 個連結
    - 可選擇自訂 slug 或使用自動生成
    - 同步抓取目標網址的 Open Graph 資料
    - 如果抓取失敗，仍會建立短網址，但 preview.fetch_status 為 failed
    """
    owner = request.user

    # 檢查用戶連結數量限制
    max_links = getattr(settings, 'USER_MAX_LINKS', 1000)
    current_count = Link.objects.filter(owner=owner).count()

    if current_count >= max_links:
        return 403, {
            'detail': f'您已達到連結上限（{max_links} 個），請刪除部分連結後再試',
            'current_count': current_count,
            'max_links': max_links,
        }

    try:
        link = create_short_link(
            original_url=str(payload.original_url),
            owner=owner,
            custom_slug=payload.custom_slug,
            expires_at=payload.expires_at,
        )
    except SlugAlreadyExistsError as e:
        return 409, {'detail': f'網址「{e.slug}」已被使用，請選擇其他名稱'}
    except ShortCodeGenerationError:
        return 500, {'detail': '系統發生錯誤，請稍後再試'}

    # TODO: 異步化優化點
    # 目前 OG 資料同步抓取，若目標網站響應慢（>10秒）會阻塞 API 響應
    # 優化建議：
    # 1. Celery + Redis：生產環境推薦，需增加 Redis 和 Worker 服務
    # 2. Huey：輕量替代方案
    # 3. Django Q：與 Django 整合更緊密
    # 4. 立即返回 + 前端輪詢：先返回 pending 狀態，前端輪詢 preview 結果
    fetch_and_save_preview(link)

    # 重新載入 link 以取得 preview 關聯
    link.refresh_from_db()

    return 200, _link_to_response(link)


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
    fetch_and_save_preview(link)
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


@router.get('/links/{short_code}/qr')
def get_qr_code(request, short_code: str, params: QRCodeParams = Query(...)):
    """
    生成短網址的 QR Code

    - 不需認證（短網址是公開的）
    - 支援尺寸：128 / 256 / 512
    - 支援自訂前景色和背景色
    """
    link = get_object_or_404(Link, short_code=short_code)

    if link.is_expired:
        return JsonResponse({'detail': '連結已過期'}, status=410)

    full_url = f"{request.scheme}://{request.get_host()}/{short_code}"
    buffer = generate_qr_code(
        url=full_url,
        size=params.size,
        dark=params.dark,
        light=params.light,
    )

    return HttpResponse(buffer, content_type='image/png')


@router.get('/check-slug/{slug}', response=SlugAvailabilityResponse, auth=JWTAuth())
def check_slug_availability(request, slug: str):
    """
    即時檢查 slug 是否可用

    - 需要 JWT 認證
    - 檢查格式、保留字和唯一性
    """
    # 格式和保留字驗證
    try:
        validated_slug = validate_custom_slug(slug)
    except ValueError as e:
        return {
            'slug': slug,
            'available': False,
            'message': str(e),
        }

    # 資料庫唯一性檢查
    if Link.objects.filter(short_code=validated_slug).exists():
        return {
            'slug': validated_slug,
            'available': False,
            'message': f'網址「{validated_slug}」已被使用',
        }

    return {
        'slug': validated_slug,
        'available': True,
        'message': '此網址可以使用',
    }


@router.delete(
    '/links/{short_code}',
    response={200: dict, 403: ErrorSchema, 404: ErrorSchema},
    auth=JWTAuth(),
)
def delete_link(request, short_code: str):
    """
    刪除指定的短網址

    - 需要 JWT 認證
    - 只有連結擁有者可以刪除
    """
    link = get_object_or_404(Link, short_code=short_code)

    # 權限檢查：只有擁有者可以刪除
    if link.owner != request.user:
        return JsonResponse({'detail': '您沒有權限刪除此連結'}, status=403)

    link.delete()
    return 200, {'detail': '連結已成功刪除', 'short_code': short_code}
