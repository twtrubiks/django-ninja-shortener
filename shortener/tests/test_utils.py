import pytest
import re
from shortener.utils import generate_short_code

@pytest.mark.django_db
def test_short_code_generator_format():
    """
    目標: 驗證生成的短代碼格式、長度是否符合預期。
    步驟:
    1. 調用 generate_short_code 函數。
    2. 驗證返回的代碼長度是否為預設的 7。
    3. 使用正則表達式驗證代碼是否只包含英文字母和數字。
    4. 測試傳入不同長度參數時，是否能生成對應長度的代碼。
    """
    # 1. 測試預設長度
    default_code = generate_short_code()
    assert len(default_code) == 7
    assert re.match(r'^[a-zA-Z0-9]{7}$', default_code) is not None

    # 2. 測試自訂長度
    custom_length = 10
    custom_code = generate_short_code(length=custom_length)
    assert len(custom_code) == custom_length
    assert re.match(r'^[a-zA-Z0-9]{10}$', custom_code) is not None

    # 3. 測試邊界情況
    short_code = generate_short_code(length=1)
    assert len(short_code) == 1
    assert re.match(r'^[a-zA-Z0-9]{1}$', short_code) is not None
