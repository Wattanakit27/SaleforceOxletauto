from django.urls import path
from django.views.generic.base import RedirectView

from . import views

# ยุบเหลือ login เดียว: /track/login/ และ /track/logout/ ส่งต่อไปหน้า login/logout หลักของ sales
# (sales bridge session → Django auth ให้ · ชื่ออื่น car_*/scan/qr_*/kanban ไม่ชนกับ sales)
urlpatterns = [
    path("login/", RedirectView.as_view(url="/login/?next=/track/", query_string=False, permanent=False), name="track_login"),
    path("logout/", RedirectView.as_view(url="/logout/", query_string=False, permanent=False), name="track_logout"),

    # หน้าเว็บ
    path("", views.dashboard, name="track_dashboard"),
    path("kanban/", views.kanban, name="kanban"),

    # จัดการผู้ใช้/บทบาท (Executive/Admin)
    path("users/", views.manage_users, name="manage_users"),
    path("logins/", views.login_log, name="login_log"),

    # JSON API — ให้หน้า sales เรนเดอร์ "สถานะรถ" เองด้วยธีมเดียวกัน (ไม่ใช้ iframe)
    path("api/cars", views.cars_api, name="cars_api"),
    path("api/logins", views.login_log_api, name="login_log_api"),
    path("api/set_stage", views.api_set_stage, name="api_set_stage"),
    path("api/seller_set_stage", views.api_seller_set_stage, name="api_seller_set_stage"),
    path("api/add_car", views.api_add_car, name="api_add_car"),
    path("api/users", views.api_users, name="api_users"),
    path("api/delete_car", views.api_delete_car, name="api_delete_car"),
    path("api/restore_car", views.api_restore_car, name="api_restore_car"),
    path("api/trash", views.api_trash, name="api_trash"),
    path("api/sign_upload", views.api_sign_upload, name="api_sign_upload"),
    path("api/upload", views.api_upload, name="api_upload"),  # อัปรูป/วิดีโอเข้า Google Drive

    # QR
    path("qr/<str:code>.png", views.qr_png, name="qr_png"),
    path("cars/qr-print/", views.qr_print, name="qr_print"),
    path("cars/qr-print/sheet/", views.qr_print_sheet, name="qr_print_sheet"),

    # สแกน (มือถือ)
    path("scan/<str:code>/", views.scan_page, name="scan"),
    path("scan/<str:code>/submit/", views.scan_submit, name="scan_submit"),

    # จัดการรถ
    path("cars/", views.car_list, name="car_list"),
    path("cars/new/", views.car_create, name="car_create"),
    path("cars/<str:code>/edit/", views.car_edit, name="car_edit"),
    path("cars/<str:code>/delete/", views.car_delete, name="car_delete"),
    path("cars/<str:code>/stage/", views.car_stage, name="car_stage"),
    path("cars/<str:code>/json", views.car_json, name="car_json"),
    path("cars/<str:code>/", views.car_detail, name="car_detail"),
]
