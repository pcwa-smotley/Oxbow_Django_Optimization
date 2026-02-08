# admin.py
from django.contrib import admin
from django.utils import timezone
from .models import UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'is_online_now', 'last_login', 'days_since_login']

    def is_online_now(self, obj):
        return obj.is_online()

    is_online_now.boolean = True
    is_online_now.short_description = 'Online Now'

    def days_since_login(self, obj):
        if obj.last_login:
            days = (timezone.now() - obj.last_login).days
            return f"{days} days ago"
        return "Never"

    days_since_login.short_description = 'Last Login'
