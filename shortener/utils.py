from sqids import Sqids

# 初始化 Sqids，設定最小長度為 8
_sqids = Sqids(min_length=8)


def generate_short_code_from_id(record_id: int) -> str:
    """
    從資料庫 ID 生成短碼（零碰撞）。

    Args:
        record_id: 資料庫記錄的主鍵 ID

    Returns:
        8+ 字元的短碼字串
    """
    return _sqids.encode([record_id])


def decode_short_code(short_code: str) -> int | None:
    """
    從短碼解碼回資料庫 ID。

    Args:
        short_code: 短碼字串

    Returns:
        資料庫 ID，若無效則返回 None
    """
    numbers = _sqids.decode(short_code)
    return numbers[0] if numbers else None


def build_short_url(request, short_code: str) -> str:
    """
    組出完整短網址（scheme://host/code）。

    模板 tag 與 API 共用的單一來源。
    """
    return f'{request.scheme}://{request.get_host()}/{short_code}'
