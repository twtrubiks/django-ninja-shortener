import string
import random
from .models import Link

def generate_short_code(length=7):
    """
    生成一個指定長度的、唯一的短代碼。

    Args:
        length (int): 短代碼的長度，預設為 7。

    Returns:
        str: 一個在資料庫中唯一的短代碼。
    """
    characters = string.ascii_letters + string.digits
    while True:
        code = ''.join(random.choice(characters) for _ in range(length))
        # 檢查生成的代碼是否已經存在於資料庫中
        if not Link.objects.filter(short_code=code).exists():
            return code
