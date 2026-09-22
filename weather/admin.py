from django.contrib import admin

from .models import WeatherDaily


@admin.register(WeatherDaily)
class WeatherDailyAdmin(admin.ModelAdmin):
    list_display = ["day", "locality", "precip_mm", "temp_max_c", "source"]
    list_filter = ["locality", "source"]
    date_hierarchy = "day"
