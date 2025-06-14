import pytest
from django.contrib.auth.models import User
from django.db.utils import IntegrityError

from shortener.models import Link

# 使用 @pytest.mark.django_db 標記來確保測試函式可以存取資料庫
@pytest.mark.django_db
def test_link_model_creation():
    """
    目標: 驗證 Link 模型是否能成功創建。
    步驟:
    1. 創建一個 User 實例。
    2. 創建一個 Link 實例，並將其與 User 關聯。
    3. Link 實例的 original_url, short_code, owner 等欄位值是否正確。
    """
    # 1. 創建 User
    user = User.objects.create_user(username="testuser", password="password123")

    # 2. 創建 Link
    original_url = "https://www.google.com"
    short_code = "googl"
    link = Link.objects.create(
        original_url=original_url,
        short_code=short_code,
        owner=user,
    )

    # 3.
    assert link.original_url == original_url
    assert link.short_code == short_code
    assert link.owner == user
    assert link.click_count == 0  # 預設應為 0
    assert str(link) == f"{short_code} for {user.username}"

@pytest.mark.django_db
def test_short_code_uniqueness():
    """
    目標: 驗證 short_code 欄位的唯一性約束 (unique=True) 是否生效。
    步驟:
    1. 創建一個 User 和一個 Link 實例。
    2. 嘗試創建第二個 Link 實例，使用完全相同的 short_code。
    3. 預期第二次創建時會拋出 django.db.utils.IntegrityError。
    """
    user = User.objects.create_user(username="testuser2", password="password123")
    Link.objects.create(
        original_url="https://www.google.com",
        short_code="unique_code",
        owner=user,
    )

    # 嘗試創建一個具有相同 short_code 的 Link
    with pytest.raises(IntegrityError):
        Link.objects.create(
            original_url="https://www.yahoo.com",
            short_code="unique_code", # 相同的 short_code
            owner=user,
        )

@pytest.mark.django_db
def test_link_model_string_representation():
    """
    目標: 驗證 Link 模型的 __str__ 方法是否返回預期的格式。
    步驟:
    1. 創建一個 User 和一個 Link 實例。
    2. str(link_instance) 的結果是否為 "original_url -> short_code"。
    """
    user = User.objects.create_user(username="testuser3", password="password123")
    link = Link.objects.create(
        original_url="https://docs.djangoproject.com",
        short_code="django-docs",
        owner=user,
    )
    expected_str = f"{link.short_code} for {user.username}"
    assert str(link) == expected_str
