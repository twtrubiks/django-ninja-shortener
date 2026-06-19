#!/bin/sh

# 如果任何指令失敗，立即退出
set -e

# 只套用已存在的 migration；不在開機產生（makemigrations 應在開發時執行並提交進版控，
# 開機才產生會讓正式環境的 schema 取決於當下程式碼，且 migration 不進版控、難以追蹤回溯）。
echo 'Run migration'
python manage.py migrate

# 建立 DatabaseCache 用的快取資料表（throttling 計數存放處；可重複執行不影響既有表）
echo 'Create cache table'
python manage.py createcachetable

# echo 'Create Super User'
# python3 manage.py createsuperuser --noinput || echo "Super user already created"
# echo 'Collect Static'
# python3 manage.py collectstatic --noinput

# 執行傳遞給此腳本的任何指令
# "$@" 會獲取 Docker CMD 或 docker-compose command 中的指令
exec "$@"


