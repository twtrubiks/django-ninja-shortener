from django.db import models
from django.contrib.auth.models import User

class Link(models.Model):
    original_url = models.URLField()
    short_code = models.CharField(max_length=15, unique=True, db_index=True)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    click_count = models.IntegerField(default=0)
    last_clicked_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        if self.owner:
            return f'{self.short_code} for {self.owner.username}'
        return f'{self.short_code} (anonymous)'
