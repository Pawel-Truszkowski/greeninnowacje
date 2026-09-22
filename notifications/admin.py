from django.contrib import admin

from .models import EmailLog


@admin.register(EmailLog)
class EmailLogAdmin(admin.ModelAdmin):
    list_display = ["sent_at", "user", "subject", "ok"]
    list_filter = ["ok"]
    readonly_fields = ["sent_at", "user", "subject", "ok"]
