from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import F
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import generic

from .models import Link, LinkPreview
from .og_parser import OGParserError, fetch_og_data
from .utils import generate_short_code_from_id
from .validators import validate_custom_slug, validate_url_scheme

# 允許的過期時間選項（秒）- 白名單驗證
EXPIRES_IN_CHOICES = {
    '': None,           # 永久
    '3600': 3600,       # 1 小時
    '86400': 86400,     # 1 天
    '604800': 604800,   # 7 天
    '2592000': 2592000, # 30 天
}


def home_view(request):
    context = {}
    if 'latest_short_url' in request.session:
        context['short_url'] = request.session['latest_short_url']
        del request.session['latest_short_url']
    return render(request, 'home.html', context)

@login_required
def dashboard_view(request):
    links = (
        Link.objects.filter(owner=request.user)
        .select_related('preview')  # 預載入 preview
        .order_by('-created_at')
    )
    return render(request, 'dashboard.html', {'links': links})

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

    return redirect(link.original_url)

def shorten_url_view(request):
    if request.method == 'POST':
        if original_url := request.POST.get('original_url'):
            # 驗證 URL 協議
            try:
                validate_url_scheme(original_url)
            except ValidationError as e:
                messages.error(request, e.message)
                return redirect('home')

            owner = request.user if request.user.is_authenticated else None

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

            # 使用 transaction 確保原子性，並捕獲 IntegrityError 處理競態條件
            try:
                with transaction.atomic():
                    if custom_slug:
                        # 樂觀檢查：大多數情況有效
                        if Link.objects.filter(short_code=custom_slug).exists():
                            messages.error(request, f'網址「{custom_slug}」已被使用，請選擇其他名稱')
                            return redirect('home')

                        # 使用自訂 slug
                        link = Link.objects.create(
                            original_url=original_url,
                            short_code=custom_slug,
                            is_custom_slug=True,
                            owner=owner,
                            expires_at=expires_at,
                        )
                    else:
                        # 使用 Sqids 自動生成
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
                # 後備：處理競態條件（兩個請求同時創建相同 slug）
                if custom_slug:
                    messages.error(request, f'網址「{custom_slug}」已被使用，請選擇其他名稱')
                else:
                    # Sqids 生成的短碼理論上不會重複，如果發生表示系統異常
                    messages.error(request, '系統發生錯誤，請稍後再試')
                return redirect('home')

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
    """手動重新抓取 OG 預覽資料"""
    link = get_object_or_404(Link, short_code=short_code)

    # 權限檢查
    if link.owner != request.user:
        messages.error(request, '您沒有權限操作此連結')
        return redirect('dashboard')

    # 抓取 OG 資料
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
        messages.success(request, '預覽資料已更新')
    except OGParserError as e:
        preview.fetch_status = LinkPreview.FetchStatus.FAILED
        preview.fetch_error = str(e)
        messages.warning(request, f'抓取失敗：{e}')

    preview.save()
    return redirect('dashboard')
