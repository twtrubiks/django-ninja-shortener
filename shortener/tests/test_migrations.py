"""Model 與 migration 一致性檢查

測試資料庫是由 migration 建立的，Model 欄位定義（max_length、null、unique、
db_index、related_name、預設值…）改了卻忘記產生 migration 時，其餘測試照樣會過，
上線後才發現 schema 不一致。這裡用 makemigrations --check 把關。
"""

import pytest
from django.core.management import call_command


@pytest.mark.django_db
def test_no_missing_migrations():
    """shortener 的 Model 變更都必須有對應的 migration"""
    try:
        call_command('makemigrations', 'shortener', '--check', '--dry-run', verbosity=0)
    except SystemExit:
        pytest.fail('shortener 有尚未產生的 migration，請執行 python manage.py makemigrations')
