from django.urls import path

from . import views

urlpatterns = [
    path("", views.supervisor, name="checkout_supervisor"),
    path("api/movements", views.api_movements, name="checkout_movements"),
    path("api/add", views.api_add, name="checkout_add"),
    path("api/action", views.api_action, name="checkout_action"),
    # เบิก/คืน จากหน้าสแกน QR (คนงาน — ไม่ใช่แอดมิน)
    path("api/car_out", views.api_car_out, name="checkout_car_out"),
    path("api/car_return", views.api_car_return, name="checkout_car_return"),
]
