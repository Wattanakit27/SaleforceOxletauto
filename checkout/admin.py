from django.contrib import admin

from .models import (
    CarMovement, MovementPhoto, ChecklistConfig, ChecklistItem,
    ViolationLog, EquipmentIssue, LineEventLog,
)


class ChecklistItemInline(admin.TabularInline):
    model = ChecklistItem
    extra = 0


@admin.register(ChecklistConfig)
class ChecklistConfigAdmin(admin.ModelAdmin):
    list_display = ("name", "room_line_group_id", "active")
    inlines = [ChecklistItemInline]


class MovementPhotoInline(admin.TabularInline):
    model = MovementPhoto
    extra = 0
    readonly_fields = ("created_at",)


@admin.register(CarMovement)
class CarMovementAdmin(admin.ModelAdmin):
    list_display = ("__str__", "borrower_name", "status", "checked_out_at", "returned_at", "damage_reported")
    list_filter = ("status", "damage_reported")
    search_fields = ("plate_text", "borrower_name")
    inlines = [MovementPhotoInline]


@admin.register(ViolationLog)
class ViolationLogAdmin(admin.ModelAdmin):
    list_display = ("person", "type", "detail", "created_at")
    list_filter = ("type",)


@admin.register(EquipmentIssue)
class EquipmentIssueAdmin(admin.ModelAdmin):
    list_display = ("car", "reporter", "issue", "status", "approved_by")
    list_filter = ("status",)


@admin.register(LineEventLog)
class LineEventLogAdmin(admin.ModelAdmin):
    list_display = ("line_message_id", "event_type", "group_id", "status", "attempts", "created_at")
    list_filter = ("status", "event_type")
