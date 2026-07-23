from django.urls import path

from . import views

urlpatterns = [
    path("", views.supervisor, name="checkout_supervisor"),
    path("api/movements", views.api_movements, name="checkout_movements"),
    path("api/add", views.api_add, name="checkout_add"),
    path("api/action", views.api_action, name="checkout_action"),
]
