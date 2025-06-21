import pytest
import re
from shortener.utils import generate_short_code
from shortener.models import Link


@pytest.mark.django_db
def test_short_code_generator_format():
    """
    測試短代碼生成器的格式和長度。

    驗證：
    - 預設長度為 7 個字符
    - 只包含英文字母和數字
    - 支援自訂長度
    - 邊界情況處理正確
    """
    # 測試預設長度
    default_code = generate_short_code()
    assert len(default_code) == 7
    assert re.match(r'^[a-zA-Z0-9]{7}$', default_code) is not None

    # 測試自訂長度
    custom_length = 10
    custom_code = generate_short_code(length=custom_length)
    assert len(custom_code) == custom_length
    assert re.match(r'^[a-zA-Z0-9]{10}$', custom_code) is not None

    # 測試邊界情況 - 最小長度
    short_code = generate_short_code(length=1)
    assert len(short_code) == 1
    assert re.match(r'^[a-zA-Z0-9]{1}$', short_code) is not None


@pytest.mark.django_db
def test_short_code_generator_uniqueness():
    """
    測試短代碼生成器的唯一性。

    驗證：
    - 生成的代碼不會與資料庫中現有的代碼重複
    - 多次調用生成不同的代碼
    """
    # 先在資料庫中創建一些 Link 記錄
    existing_codes = ['abc123', 'def456', 'ghi789']
    for code in existing_codes:
        Link.objects.create(
            original_url=f"https://example{code}.com",
            short_code=code,
            owner=None
        )

    # 生成新的代碼，應該不會與現有的重複
    new_code = generate_short_code()
    assert new_code not in existing_codes
    assert not Link.objects.filter(short_code=new_code).exists()

    # 測試多次生成的代碼都是唯一的
    generated_codes = set()
    for _ in range(10):
        code = generate_short_code()
        assert code not in generated_codes
        generated_codes.add(code)
