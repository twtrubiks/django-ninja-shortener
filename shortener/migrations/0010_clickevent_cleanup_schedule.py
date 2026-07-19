"""建立點擊事件清理的 Django-Q 每日排程。

轉址是無限流的公開端點，ClickEvent 若無清理會無上限增長；
保留天數見 services.CLICK_EVENT_RETENTION_DAYS。
"""

from django.db import migrations

CLEANUP_FUNC = 'shortener.services.cleanup_old_click_events'


def create_cleanup_schedule(apps, schema_editor):
    Schedule = apps.get_model('django_q', 'Schedule')
    Schedule.objects.get_or_create(
        func=CLEANUP_FUNC,
        defaults={
            'name': '清理過期點擊事件',
            'schedule_type': 'D',  # 每日
        },
    )


def delete_cleanup_schedule(apps, schema_editor):
    Schedule = apps.get_model('django_q', 'Schedule')
    Schedule.objects.filter(func=CLEANUP_FUNC).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('shortener', '0009_clickevent'),
        ('django_q', '0019_alter_task_options_alter_ormq_key_alter_ormq_lock_and_more'),
    ]

    operations = [
        migrations.RunPython(create_cleanup_schedule, delete_cleanup_schedule),
    ]
