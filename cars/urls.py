from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

# หมายเหตุ: ไม่ใช้ app_namespace — แต่ rename ชื่อที่ชนกับ sales (login/logout/dashboard)
# เป็น track_login / track_logout / track_dashboard · ชื่ออื่น (car_*/scan/qr_*/kanban) ไม่ชน
urlpatterns = [
    # auth (ของ tracking เอง — แยกจาก LINE login ของ sales)
    path("login/", auth_views.LoginView.as_view(template_name="login.html"), name="track_login"),
    path("logout/", auth_views.LogoutView.as_view(), name="track_logout"),

    # หน้าเว็บ
    path("", views.dashboard, name="track_dashboard"),
    path("kanban/", views.kanban, name="kanban"),

    # จัดการผู้ใช้/บทบาท (Executive/Admin)
    path("users/", views.manage_users, name="manage_users"),

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
    path("cars/<str:code>/", views.car_detail, name="car_detail"),
]
