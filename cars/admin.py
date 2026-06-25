from django.contrib import admin
from django.utils.html import format_html

from .models import Branch, Car, LoginEvent, Presence, ScanLog


class ScanLogInline(admin.TabularInline):
    model = ScanLog
    extra = 0
    fields = ("stage", "worker_name", "note", "created_at")
    readonly_fields = ("created_at",)


@admin.register(Car)
class CarAdmin(admin.ModelAdmin):
    list_display = ("code", "branch", "brand", "model", "stage", "status", "flag", "date_in")
    list_filter = ("branch", "stage", "status")
    search_fields = ("code", "plate", "brand", "model")
    readonly_fields = ("code", "stage_since", "frontline_at", "qr_link", "created_at", "updated_at")
    inlines = [ScanLogInline]

    @admin.display(description="QR")
    def qr_link(self, obj):
        if not obj.code:
            return "—"
        return format_html('<a href="/track/qr/{}.png" target="_blank">เปิด QR</a>', obj.code)


@admin.register(ScanLog)
class ScanLogAdmin(admin.ModelAdmin):
    list_display = ("car", "stage", "worker_name", "created_at")
    list_filter = ("stage",)
    search_fields = ("car__code", "worker_name")


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "active")


@admin.register(LoginEvent)
class LoginEventAdmin(admin.ModelAdmin):
    list_display = ("created_at", "identity", "name", "method", "success", "role", "ip")
    list_filter = ("success", "method")
    search_fields = ("identity", "name", "ip")
    readonly_fields = ("created_at",)


@admin.register(Presence)
class PresenceAdmin(admin.ModelAdmin):
    list_display = ("identity", "name", "role", "page", "last_seen")
    search_fields = ("identity", "name")
