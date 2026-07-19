"""連結擁有者授權檢查。

網頁 view 與 API 端點對非擁有者的回應形式不同（flash 訊息 + redirect
vs JSON 403），故提供兩種 helper；錯誤訊息的動詞由呼叫端指定以維持既有文案。
"""

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect

from .models import Link


def get_owned_link_or_403(request, short_code, action, queryset=None):
    """撈取連結並確認擁有者。

    回傳 (link, None)；非擁有者時回傳 (None, JSON 403 回應)。
    """
    link = get_object_or_404(
        queryset if queryset is not None else Link, short_code=short_code
    )
    if link.owner != request.user:
        return None, JsonResponse({'detail': f'您沒有權限{action}此連結'}, status=403)
    return link, None


def get_owned_link_or_redirect(request, short_code, action):
    """同 get_owned_link_or_403，但非擁有者時回傳帶錯誤訊息的 dashboard redirect。"""
    link = get_object_or_404(Link, short_code=short_code)
    if link.owner != request.user:
        messages.error(request, f'您沒有權限{action}此連結')
        return None, redirect('dashboard')
    return link, None
