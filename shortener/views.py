import uuid

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import generic

from .models import Link
from .utils import generate_short_code_from_id
from .validators import validate_url_scheme

def home_view(request):
    context = {}
    if 'latest_short_url' in request.session:
        context['short_url'] = request.session['latest_short_url']
        del request.session['latest_short_url']
    return render(request, 'home.html', context)

@login_required
def dashboard_view(request):
    links = Link.objects.filter(owner=request.user).order_by('-created_at')
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

            # 使用 transaction 確保原子性
            with transaction.atomic():
                # 先建立記錄（使用 UUID 作為暫時值，避免 unique 約束衝突）
                link = Link.objects.create(
                    original_url=original_url,
                    short_code=str(uuid.uuid4())[:15],
                    owner=owner
                )

                # 使用資料庫 ID 生成短碼（零碰撞）
                link.short_code = generate_short_code_from_id(link.id)
                link.save(update_fields=['short_code'])

            full_short_url = request.build_absolute_uri(f'/{link.short_code}')
            messages.success(request, "成功建立短網址！")
            request.session['latest_short_url'] = full_short_url
            return redirect('home')

    return redirect('home')


class RegisterView(generic.CreateView):
    form_class = UserCreationForm
    success_url = reverse_lazy('login')
    template_name = 'registration/register.html'
