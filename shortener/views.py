from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import F
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import generic
from ninja.throttling import UserRateThrottle

from .analytics import get_link_stats, record_click
from .auth import generate_api_key, hash_api_key
from .models import ApiKey, Link, LinkPreview
from .services import (
    ShortCodeGenerationError,
    SlugAlreadyExistsError,
    create_short_link,
    enqueue_preview_fetch,
)
from .validators import MAX_URL_LENGTH, validate_custom_slug, validate_url_scheme

# 允許的過期時間選項（秒）- 白名單驗證
EXPIRES_IN_CHOICES = {
    '': None,           # 永久
    '3600': 3600,       # 1 小時
    '86400': 86400,     # 1 天
    '604800': 604800,   # 7 天
    '2592000': 2592000, # 30 天
}

# Dashboard 每頁顯示數量
DASHBOARD_ITEMS_PER_PAGE = 25


class _ShortenWebThrottle(UserRateThrottle):
    """網頁表單建立短網址的速率限制：登入按帳號、匿名按來源 IP。

    獨立 scope 讓 cache key 不與其他 UserRateThrottle 使用處共用計數 bucket。
    IP 取自 X-Forwarded-For：生產環境前層是 Caddy 2.5+，會丟棄 client 自帶的
    X-Forwarded-* 並重寫為真實來源 IP，故無偽造疑慮；若前層改為 nginx 等
    不會 strip 該標頭的代理，需另設 NINJA_NUM_PROXIES 防偽造繞過。
    """

    scope = 'shorten_web'


# 計數存於 Django cache（與 API throttle 同一套，見 settings.CACHES）
_shorten_throttle = _ShortenWebThrottle(getattr(settings, 'SHORTEN_THROTTLE_RATE', '10/min'))


def home_view(request):
    context = {}
    if 'latest_short_url' in request.session:
        context['short_url'] = request.session['latest_short_url']
        del request.session['latest_short_url']
    return render(request, 'home.html', context)

@login_required
def dashboard_view(request):
    links_queryset = (
        Link.objects.filter(owner=request.user)
        .select_related('preview')  # 預載入 preview
        .order_by('-created_at')
    )

    paginator = Paginator(links_queryset, DASHBOARD_ITEMS_PER_PAGE)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    return render(request, 'dashboard.html', {
        'links': page_obj,
        'page_obj': page_obj,
        'max_links': getattr(settings, 'USER_MAX_LINKS', 1000),
    })

def redirect_view(request, short_code):
    link = get_object_or_404(Link, short_code=short_code)

    # 檢查是否過期
    if link.is_expired:
        return render(request, 'expired.html', {'short_code': short_code}, status=410)

    # 使用 F() 表達式進行原子性更新，避免競態條件
    Link.objects.filter(pk=link.pk).update(
        click_count=F('click_count') + 1,
        last_clicked_at=timezone.now()
    )

    # 匿名連結沒有統計頁可看，不留事件
    if link.owner_id:
        record_click(link, request)

    return redirect(link.original_url)

def shorten_url_view(request):
    if request.method == 'POST':
        # 速率限制放在所有處理之前：無效嘗試也計數，超量以最低成本拒絕
        if not _shorten_throttle.allow_request(request):
            messages.error(request, '操作過於頻繁，請稍後再試')
            return redirect('home')

        if original_url := request.POST.get('original_url'):
            # 長度驗證（超過資料庫欄位上限會直接寫入失敗）
            if len(original_url) > MAX_URL_LENGTH:
                messages.error(request, f'網址過長（上限 {MAX_URL_LENGTH} 字元）')
                return redirect('home')

            # 驗證 URL 協議
            try:
                validate_url_scheme(original_url)
            except ValidationError as e:
                messages.error(request, e.message)
                return redirect('home')

            owner = request.user if request.user.is_authenticated else None

            # 檢查用戶連結數量限制（僅登入用戶）
            if owner is not None:
                max_links = getattr(settings, 'USER_MAX_LINKS', 1000)
                current_count = Link.objects.filter(owner=owner).count()

                if current_count >= max_links:
                    messages.error(
                        request,
                        f'您已達到連結上限（{max_links} 個），請刪除部分連結後再試'
                    )
                    return redirect('home')

            # 計算過期時間（僅登入用戶，使用白名單驗證）
            expires_at = None
            if request.user.is_authenticated:
                expires_in = request.POST.get('expires_in', '')
                if expires_in in EXPIRES_IN_CHOICES and EXPIRES_IN_CHOICES[expires_in]:
                    expires_at = timezone.now() + timedelta(seconds=EXPIRES_IN_CHOICES[expires_in])

            # 處理自訂 slug（僅登入用戶）
            custom_slug = None
            if request.user.is_authenticated:
                raw_slug = request.POST.get('custom_slug', '').strip()
                if raw_slug:
                    try:
                        custom_slug = validate_custom_slug(raw_slug)
                    except ValueError as e:
                        messages.error(request, str(e))
                        return redirect('home')

            # 建立短網址（共用核心邏輯）
            try:
                link = create_short_link(
                    original_url=original_url,
                    owner=owner,
                    custom_slug=custom_slug,
                    expires_at=expires_at,
                )
            except SlugAlreadyExistsError as e:
                messages.error(request, f'網址「{e.slug}」已被使用，請選擇其他名稱')
                return redirect('home')
            except ShortCodeGenerationError:
                messages.error(request, '系統發生錯誤，請稍後再試')
                return redirect('home')

            # 將 OG 預覽抓取排入背景（非阻塞）；dashboard 會顯示骨架並輪詢更新
            enqueue_preview_fetch(link)

            full_short_url = request.build_absolute_uri(f'/{link.short_code}')
            messages.success(request, "成功建立短網址！")
            request.session['latest_short_url'] = full_short_url
            return redirect('home')

    return redirect('home')


class RegisterView(generic.CreateView):
    form_class = UserCreationForm
    success_url = reverse_lazy('login')
    template_name = 'registration/register.html'


@login_required
def refresh_preview_view(request, short_code):
    """手動將 OG 預覽重新排入背景抓取"""
    link = get_object_or_404(Link, short_code=short_code)

    # 權限檢查
    if link.owner != request.user:
        messages.error(request, '您沒有權限操作此連結')
        return redirect('dashboard')

    # 重新排入背景抓取（前端會輪詢骨架直到完成）
    enqueue_preview_fetch(link)
    messages.success(request, '已開始重新抓取預覽，稍候會自動更新')

    return redirect('dashboard')


@login_required
def preview_status_view(request, short_code):
    """
    回傳單一連結 OG 預覽的目前狀態與卡片 HTML（供 dashboard 前端輪詢局部更新）。

    - 需登入且為連結擁有者
    - 回傳 {status, html}；html 是與 dashboard 共用的 _preview_card 局部模板
    """
    link = get_object_or_404(
        Link.objects.select_related('preview'),
        short_code=short_code,
    )

    if link.owner != request.user:
        return JsonResponse({'detail': '您沒有權限查看此連結'}, status=403)

    try:
        status = link.preview.fetch_status
    except LinkPreview.DoesNotExist:
        status = 'none'

    html = render_to_string(
        'partials/_preview_card.html',
        {'link': link},
        request=request,
    )
    return JsonResponse({'status': status, 'html': html})


@login_required
def link_stats_view(request, short_code):
    """連結統計頁：近 30 天每日點擊、Top referrers 與裝置分佈（不含 bot）"""
    link = get_object_or_404(Link, short_code=short_code)

    if link.owner != request.user:
        messages.error(request, '您沒有權限查看此連結')
        return redirect('dashboard')

    return render(request, 'stats.html', {
        'link': link,
        'stats': get_link_stats(link),
    })


@login_required
def api_keys_view(request):
    """API Key 管理頁：列出金鑰與建立表單

    剛建立的金鑰明文透過 session 傳遞、只顯示這一次（同 home 頁
    latest_short_url 的模式），之後只能看到 prefix。
    """
    context = {
        'api_keys': ApiKey.objects.filter(owner=request.user).order_by('-created_at'),
        'max_api_keys': getattr(settings, 'USER_MAX_API_KEYS', 10),
    }
    if 'new_api_key' in request.session:
        context['new_api_key'] = request.session['new_api_key']
        del request.session['new_api_key']
    return render(request, 'api_keys.html', context)


@login_required
def create_api_key_view(request):
    """建立 API Key，明文放進 session 供管理頁一次性顯示"""
    if request.method != 'POST':
        return redirect('api_keys')

    max_keys = getattr(settings, 'USER_MAX_API_KEYS', 10)
    if ApiKey.objects.filter(owner=request.user).count() >= max_keys:
        messages.error(request, f'您已達到 API Key 上限（{max_keys} 個），請先撤銷不用的金鑰')
        return redirect('api_keys')

    name = request.POST.get('name', '').strip()[:100] or '未命名'
    raw_key = generate_api_key()
    ApiKey.objects.create(
        owner=request.user,
        name=name,
        key_hash=hash_api_key(raw_key),
        prefix=raw_key[:8],
    )
    request.session['new_api_key'] = raw_key
    messages.success(request, 'API Key 已建立，請立即複製保存——它只會顯示這一次')
    return redirect('api_keys')


@login_required
def delete_api_key_view(request, key_id):
    """撤銷（刪除）API Key"""
    if request.method != 'POST':
        return redirect('api_keys')

    api_key = get_object_or_404(ApiKey, pk=key_id, owner=request.user)
    api_key.delete()
    messages.success(request, 'API Key 已撤銷')
    return redirect('api_keys')


@login_required
def delete_link_view(request, short_code):
    """刪除連結"""
    if request.method != 'POST':
        return redirect('dashboard')

    link = get_object_or_404(Link, short_code=short_code)

    # 權限檢查
    if link.owner != request.user:
        messages.error(request, '您沒有權限刪除此連結')
        return redirect('dashboard')

    link.delete()
    messages.success(request, '連結已成功刪除')
    return redirect('dashboard')
