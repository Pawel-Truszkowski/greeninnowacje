from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .forms import AdminUserChangeForm, AdminUserCreationForm
from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    form = AdminUserChangeForm
    add_form = AdminUserCreationForm
    ordering = ["email"]
    list_display = ["email", "display_name", "role", "is_active", "created_at"]
    list_filter = ["role", "is_active", "is_staff"]
    search_fields = ["email", "display_name"]
    readonly_fields = ["created_at", "last_login"]
    fieldsets = [
        (None, {"fields": ["email", "password"]}),
        ("Profil", {"fields": ["display_name", "role", "is_active"]}),
        ("Django admin", {"fields": ["is_staff", "is_superuser"]}),
        ("Daty", {"fields": ["last_login", "created_at"]}),
    ]
    add_fieldsets = [
        (
            None,
            {
                "classes": ["wide"],
                "fields": ["email", "display_name", "role", "password1", "password2"],
            },
        ),
    ]
    filter_horizontal = []
