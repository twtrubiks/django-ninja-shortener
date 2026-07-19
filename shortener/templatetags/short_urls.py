from django import template

from ..utils import build_short_url

register = template.Library()


@register.simple_tag(takes_context=True)
def short_url(context, link):
    """完整短網址（scheme://host/code），與 API 回傳的 full_url 同一來源"""
    return build_short_url(context['request'], link.short_code)
