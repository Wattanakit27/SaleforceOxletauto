from django.urls import path
from . import views

urlpatterns = [
    path("", views.index),
    path("dashboard/", views.dashboard_page, name="dashboard"),
    path("admin/", views.admin_page, name="admin"),
    path("api/dashboard", views.api_dashboard, name="api_dashboard"),
    path("api/auth", views.api_auth, name="api_auth"),
    path("u/<str:token>/", views.magic_link, name="magic_link"),
    path("s/<str:token>/", views.seller_dashboard, name="seller_dashboard"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("api/admin/send_line", views.admin_send_line, name="admin_send_line"),
    path("api/admin/seller_config", views.admin_seller_config, name="admin_seller_config"),
    path("api/admin/schedule_config", views.admin_schedule_config, name="admin_schedule_config"),
    path("api/admin/diagnostics", views.admin_diagnostics, name="admin_diagnostics"),
    path("api/admin/export_leadscore", views.admin_export_leadscore, name="admin_export_leadscore"),
    path("api/cron/send_line", views.cron_send_line, name="cron_send_line"),
    path("api/cron/tick", views.cron_tick, name="cron_tick"),
]
