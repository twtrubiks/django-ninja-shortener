from django.contrib import admin

from .models import Link


@admin.register(Link)
class LinkAdmin(admin.ModelAdmin):
    list_display = ('short_code', 'owner', 'click_count', 'created_at', 'expires_at')
    list_filter = ('created_at', 'owner')
    search_fields = ('original_url', 'short_code')
    readonly_fields = ('created_at', 'last_clicked_at', 'click_count')
    date_hierarchy = 'created_at'
