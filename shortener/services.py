"""
共用業務邏輯層：供 API（ninja）與 Web view 共同呼叫。

這層只處理核心領域邏輯（建立連結、抓取 OG 預覽），
不負責輸入驗證、數量限制、HTTP 回應格式或使用者訊息——
那些屬於各自呼叫端（api.py / views.py）的邊界責任。
"""

from typing import Optional

from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.utils import timezone
from django_q.tasks import async_task

from .models import Link, LinkPreview
from .og_parser import OGParserError, fetch_og_data
from .utils import generate_short_code_from_id


class SlugAlreadyExistsError(Exception):
    """自訂 slug 已被其他連結使用。"""

    def __init__(self, slug: str):
        self.slug = slug
        super().__init__(f'網址「{slug}」已被使用')


class ShortCodeGenerationError(Exception):
    """短碼生成失敗。

    Sqids 以資料庫 ID 生成的短碼理論上不會重複，
    若仍發生唯一約束衝突即代表系統異常。
    """


def create_short_link(
    *,
    original_url: str,
    owner: Optional[User] = None,
    custom_slug: Optional[str] = None,
    expires_at=None,
) -> Link:
    """
    原子性建立短網址。

    呼叫端必須已完成輸入驗證（URL 協議、custom_slug 格式、數量限制）。
    本函式只負責建立：custom_slug 直接寫入並依賴 DB 唯一約束避免 TOCTOU 競態，
    否則以資料庫 ID 經 Sqids 生成零碰撞短碼。

    Args:
        original_url: 已驗證的目標網址字串
        owner: 連結擁有者，匿名建立時為 None
        custom_slug: 已驗證、正規化後的自訂 slug；None 表示自動生成
        expires_at: 過期時間，None 表示永久

    Returns:
        建立完成的 Link 實例

    Raises:
        SlugAlreadyExistsError: custom_slug 與既有連結衝突
        ShortCodeGenerationError: 自動短碼生成發生非預期的唯一約束衝突
    """
    try:
        with transaction.atomic():
            if custom_slug:
                link = Link.objects.create(
                    original_url=original_url,
                    short_code=custom_slug,
                    is_custom_slug=True,
                    owner=owner,
                    expires_at=expires_at,
                )
            else:
                link = Link.objects.create(
                    original_url=original_url,
                    is_custom_slug=False,
                    owner=owner,
                    expires_at=expires_at,
                )
                # 使用資料庫 ID 生成短碼（零碰撞）
                link.short_code = generate_short_code_from_id(link.id)
                link.save(update_fields=['short_code'])
    except IntegrityError:
        if custom_slug:
            raise SlugAlreadyExistsError(custom_slug)
        raise ShortCodeGenerationError()

    return link


def fetch_and_save_preview(link: Link) -> LinkPreview:
    """
    抓取 OG 資料並儲存到 LinkPreview。

    抓取失敗不會拋出例外，而是把失敗狀態記錄在 preview 上，
    讓呼叫端依 fetch_status 決定後續處理（例如顯示訊息）。

    Args:
        link: Link 實例

    Returns:
        建立或更新後的 LinkPreview 實例
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


def enqueue_preview_fetch(link: Link) -> None:
    """
    將 OG 抓取排入背景佇列（非阻塞）。

    先把 preview 標記為 PENDING（前端據此顯示骨架載入），再交給
    Django-Q worker 非同步執行實際抓取，呼叫端可立即回應、不被目標網站拖慢。

    Args:
        link: 目標 Link 實例
    """
    LinkPreview.objects.update_or_create(
        link=link,
        defaults={
            'fetch_status': LinkPreview.FetchStatus.PENDING,
            'fetch_error': '',
        },
    )
    async_task('shortener.services.run_preview_fetch', link.id)


def run_preview_fetch(link_id: int) -> None:
    """
    Django-Q 背景任務：依 link_id 載入 Link 並抓取 OG 預覽。

    以主鍵（而非 Link 物件）作為參數，避免序列化整個 model 實例；
    連結若在排程後才被刪除則安全略過。

    Args:
        link_id: Link 主鍵
    """
    try:
        link = Link.objects.get(id=link_id)
    except Link.DoesNotExist:
        return

    fetch_and_save_preview(link)
