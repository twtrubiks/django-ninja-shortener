import re
from shortener.utils import generate_short_code_from_id, decode_short_code


def test_generate_short_code_from_id_format():
    """
    測試 Sqids 短碼生成器的格式和長度。

    驗證：
    - 生成的代碼至少 8 個字符（min_length=8）
    - 只包含英文字母和數字
    """
    # 測試基本格式
    code = generate_short_code_from_id(1)
    assert len(code) >= 8
    assert re.match(r'^[a-zA-Z0-9]+$', code) is not None

    # 測試較大的 ID
    code_large = generate_short_code_from_id(999999)
    assert len(code_large) >= 8
    assert re.match(r'^[a-zA-Z0-9]+$', code_large) is not None


def test_generate_short_code_from_id_deterministic():
    """
    測試 Sqids 短碼生成器是確定性的（相同 ID 生成相同碼）。

    驗證：
    - 相同的 ID 每次生成相同的短碼
    """
    code1 = generate_short_code_from_id(12345)
    code2 = generate_short_code_from_id(12345)
    assert code1 == code2


def test_generate_short_code_from_id_unique():
    """
    測試不同 ID 生成不同的短碼。

    驗證：
    - 不同的 ID 生成不同的短碼
    """
    codes = set()
    for i in range(1, 101):
        code = generate_short_code_from_id(i)
        assert code not in codes, f"ID {i} 生成的短碼 {code} 與其他 ID 重複"
        codes.add(code)


def test_decode_short_code_roundtrip():
    """
    測試短碼可以正確解碼回原始 ID。

    驗證：
    - encode -> decode 回傳原始 ID
    """
    test_ids = [1, 10, 100, 1000, 12345, 999999]

    for original_id in test_ids:
        code = generate_short_code_from_id(original_id)
        decoded_id = decode_short_code(code)
        assert decoded_id == original_id, f"ID {original_id} 的短碼 {code} 解碼為 {decoded_id}"


def test_decode_short_code_invalid():
    """
    測試無效短碼的處理。

    驗證：
    - 空字串返回 None
    - 無效格式返回 None 或空列表
    """
    # 空字串
    result = decode_short_code('')
    assert result is None

    # 特殊字符（Sqids 只使用字母數字，所以這應該無效）
    result = decode_short_code('!@#$%')
    assert result is None
