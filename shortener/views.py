from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.contrib import messages
from django.urls import reverse_lazy
from django.views import generic
from .models import Link
import shortuuid

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
    link.click_count += 1
    link.last_clicked_at = timezone.now()
    link.save()
    return redirect(link.original_url)

def shorten_url_view(request):
    if request.method == 'POST':
        if original_url := request.POST.get('original_url'):
            # 產生不重複的 short_code
            while True:
                short_code = shortuuid.uuid()[:8]
                if not Link.objects.filter(short_code=short_code).exists():
                    break

            owner = request.user if request.user.is_authenticated else None

            link = Link.objects.create(
                original_url=original_url,
                short_code=short_code,
                owner=owner
            )

            full_short_url = request.build_absolute_uri(f'/{link.short_code}')
            messages.success(request, "成功建立短網址！")
            request.session['latest_short_url'] = full_short_url
            return redirect('home')

    return redirect('home')


class RegisterView(generic.CreateView):
    form_class = UserCreationForm
    success_url = reverse_lazy('login')
    template_name = 'registration/register.html'
