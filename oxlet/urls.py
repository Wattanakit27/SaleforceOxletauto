from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    # Django admin (ใช้โดยแอป cars/ tracking) — ย้ายจาก /admin/ กันชนกับ sales admin (/admin/)
    path("dj-admin/", admin.site.urls),
    # ระบบติดตามรถ (tracking) — แยก prefix /track/ กันชน login/logout/หน้าแรกของ sales
    path("track/", include("cars.urls")),
    # ระบบเบิก-คืนรถส่วนกลาง — แยก prefix /checkout/ (หน้า supervisor ฝังเป็นแท็บใน /dashboard/)
    path("checkout/", include("checkout.urls")),
    # sales dashboard (เดิม) — อ่าน Google Sheets, ไม่ใช้ DB
    path("", include("dashboard.urls")),
]

# dev: เสิร์ฟ media (รูปรถ/สแกน) จากเครื่อง — prod ใช้ Supabase Storage
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
