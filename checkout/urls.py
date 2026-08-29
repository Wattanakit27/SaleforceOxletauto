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
    # โหมดเฝ้าดู — เก็บ log กลุ่ม LINE ไว้ตรวจว่าระบบตีความตรงไหม (ยังไม่ทำงานจริง)
    path("observe/", views.observe_page, name="checkout_observe"),
    path("api/observe", views.api_observe, name="checkout_observe_api"),
    path("api/observe/verdict", views.api_observe_verdict, name="checkout_observe_verdict"),
    path("api/observe/toggle", views.api_observe_toggle, name="checkout_observe_toggle"),
]
