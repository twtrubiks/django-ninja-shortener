from io import BytesIO

import segno


def generate_qr_code(
    url: str,
    size: int = 256,
    dark: str = "#000000",
    light: str = "#FFFFFF",
) -> BytesIO:
    """
    生成 QR Code PNG 圖片

    Args:
        url: 要編碼的 URL
        size: 圖片尺寸（128/256/512）
        dark: 前景色（十六進位）
        light: 背景色（十六進位）

    Returns:
        包含 PNG 圖片的 BytesIO
    """
    qr = segno.make(url, error='M')

    # 計算 scale（segno 的 module 大小約 29x29）
    scale = max(1, size // 29)

    buffer = BytesIO()
    qr.save(buffer, kind='png', scale=scale, dark=dark, light=light)
    buffer.seek(0)
    return buffer
