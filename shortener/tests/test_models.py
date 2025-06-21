import pytest
from django.contrib.auth.models import User
from django.db.utils import IntegrityError
from django.utils import timezone

from shortener.models import Link


@pytest.mark.django_db
def test_link_model_creation():
    """
    測試 Link 模型的基本創建功能。

    驗證：
    - Link 實例能成功創建
    - 所有欄位值正確設置
    - 預設值正確設置
    """
    # 創建測試用戶
    user = User.objects.create_user(username="testuser", password="password123")

    # 創建 Link 實例
    original_url = "https://www.google.com"
    short_code = "googl"
    link = Link.objects.create(
        original_url=original_url,
        short_code=short_code,
        owner=user,
    )

    # 驗證欄位值
    assert link.original_url == original_url
    assert link.short_code == short_code
    assert link.owner == user
    assert link.click_count == 0  # 預設值應為 0
    assert link.last_clicked_at is None  # 初始應為 None
    assert link.created_at is not None  # 應自動設置創建時間
    assert str(link) == f"{short_code} for {user.username}"

@pytest.mark.django_db
def test_short_code_uniqueness():
    """
    測試 short_code 欄位的唯一性約束。

    驗證：
    - 相同的 short_code 不能重複創建
    - 違反唯一性約束時拋出 IntegrityError
    """
    user = User.objects.create_user(username="testuser2", password="password123")

    # 創建第一個 Link
    Link.objects.create(
        original_url="https://www.google.com",
        short_code="unique_code",
        owner=user,
    )

    # 嘗試創建具有相同 short_code 的 Link，應該拋出 IntegrityError
    with pytest.raises(IntegrityError):
        Link.objects.create(
            original_url="https://www.yahoo.com",
            short_code="unique_code",  # 相同的 short_code
            owner=user,
        )

@pytest.mark.django_db
def test_link_model_string_representation_with_owner():
    """
    測試有擁有者的 Link 模型的 __str__ 方法。

    驗證：
    - 當 Link 有擁有者時，__str__ 返回 "short_code for username" 格式
    """
    user = User.objects.create_user(username="testuser3", password="password123")
    link = Link.objects.create(
        original_url="https://docs.djangoproject.com",
        short_code="django-docs",
        owner=user,
    )
    expected_str = f"{link.short_code} for {user.username}"
    assert str(link) == expected_str


@pytest.mark.django_db
def test_link_model_string_representation_anonymous():
    """
    測試匿名用戶的 Link 模型的 __str__ 方法。

    驗證：
    - 當 Link 沒有擁有者時，__str__ 返回 "short_code (anonymous)" 格式
    """
    link = Link.objects.create(
        original_url="https://example.com",
        short_code="anon-link",
        owner=None,
    )
    expected_str = f"{link.short_code} (anonymous)"
    assert str(link) == expected_str
