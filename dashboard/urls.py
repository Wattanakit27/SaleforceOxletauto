from django.urls import path
from . import views

urlpatterns = [
    path("", views.index),
    path("dashboard/", views.dashboard_page, name="dashboard"),
    path("api/dashboard", views.api_dashboard, name="api_dashboard"),
    path("api/auth", views.api_auth, name="api_auth"),
    path("u/<str:token>/", views.magic_link, name="magic_link"),
    path("s/<str:token>/", views.seller_dashboard, name="seller_dashboard"),
]
