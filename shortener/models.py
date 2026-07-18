from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone

from .validators import MAX_URL_LENGTH, validate_url_scheme


class Link(models.Model):
    original_url = models.URLField(max_length=MAX_URL_LENGTH, validators=[validate_url_scheme])
    short_code = models.CharField(max_length=50, unique=True, db_index=True, null=True, blank=True)
    is_custom_slug = models.BooleanField(default=False)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    click_count = models.IntegerField(default=0)
    last_clicked_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['owner', '-created_at']),
            models.Index(fields=['-click_count']),
            models.Index(fields=['expires_at']),
        ]

    def __str__(self):
        if self.owner:
            return f'{self.short_code} for {self.owner.username}'
        return f'{self.short_code} (anonymous)'

    @property
    def is_expired(self) -> bool:
        """檢查連結是否已過期"""
        if self.expires_at is None:
            return False
        return self.expires_at < timezone.now()


class ApiKey(models.Model):
    """長效 API Key（Personal Access Token），供程式化串接與瀏覽器擴充套件使用。

    只儲存金鑰的 SHA-256 雜湊（見 shortener/auth.py），明文僅在建立當下顯示一次；
    資料庫外洩時攻擊者拿不到可用的金鑰明文。
    """

    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='api_keys')
    name = models.CharField(max_length=100)
    key_hash = models.CharField(max_length=64, unique=True)
    prefix = models.CharField(max_length=16)  # 明文開頭數字元，供列表辨識用
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['owner', '-created_at']),
        ]

    def __str__(self):
        return f'{self.name} ({self.prefix}…) for {self.owner.username}'


class LinkPreview(models.Model):
    """儲存 Open Graph 預覽資料"""

    class FetchStatus(models.TextChoices):
        PENDING = 'pending', '待處理'
        SUCCESS = 'success', '成功'
        FAILED = 'failed', '失敗'

    link = models.OneToOneField(
        Link,
        on_delete=models.CASCADE,
        related_name='preview',
        primary_key=True,
    )

    # OG 核心欄位
    og_title = models.CharField(max_length=500, blank=True, default='')
    og_description = models.TextField(blank=True, default='')
    og_image = models.URLField(max_length=2000, blank=True, default='')
    og_site_name = models.CharField(max_length=200, blank=True, default='')
    og_type = models.CharField(max_length=100, blank=True, default='')

    # 抓取狀態
    fetch_status = models.CharField(
        max_length=20,
        choices=FetchStatus.choices,
        default=FetchStatus.PENDING,
        db_index=True,
    )
    fetch_error = models.TextField(blank=True, default='')
    fetched_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['fetch_status', '-fetched_at']),
        ]

    def __str__(self):
        return f'Preview for {self.link.short_code}: {self.fetch_status}'

    @property
    def has_preview_data(self) -> bool:
        """檢查是否有有效的預覽資料"""
        return bool(self.og_title or self.og_description or self.og_image)
