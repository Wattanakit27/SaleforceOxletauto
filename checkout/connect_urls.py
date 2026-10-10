"""/connect/ — ห้องแชทลูกค้ารวม (แอดมิน + เซลล์) · ดู connect.py / connect_views.py"""
from django.urls import path

from . import connect_views as V

urlpatterns = [
    path("", V.page, name="connect"),
    path("api/summary", V.api_summary, name="connect_summary"),
    path("api/inbox", V.api_inbox, name="connect_inbox"),
    path("api/chat", V.api_chat, name="connect_chat"),
    path("api/claim", V.api_claim, name="connect_claim"),
    path("api/reply", V.api_reply, name="connect_reply"),
    path("api/assign", V.api_assign, name="connect_assign"),
    path("api/dismiss", V.api_dismiss, name="connect_dismiss"),
    path("api/lead", V.api_lead, name="connect_lead"),            # แก้ข้อมูลลีด 1 ช่อง
    path("api/assign_lead", V.api_assign_lead, name="connect_assign_lead"),   # ปุ่มจ่ายเบอร์ (ทดลอง)
    path("api/park_assign", V.api_park_assign, name="connect_park_assign"),   # จ่ายเบอร์ลีดภายนอก (ห้องพัก Lead)
    path("api/leadflow", V.api_leadflow, name="connect_leadflow"),   # งานจ่ายเบอร์: นาฬิกาโทร/จ่ายวน/ไม้ 2 (แอดมิน)
    path("api/leaddb", V.api_leaddb, name="connect_leaddb"),         # ฐานข้อมูล Lead (ชีตลีด · แอดมิน)
    path("api/pipeline", V.api_pipeline, name="connect_pipeline"),   # ไปป์ไลน์เคสจอง (แอดมิน)
    path("api/team", V.api_team, name="connect_team"),               # แดชบอร์ดทีม (แอดมิน)
    path("api/fb_test", V.api_fb_test, name="connect_fb_test"),     # แชททดสอบการตอบ Facebook (แอดมิน)
    path("api/fb_webhook", V.api_fb_webhook, name="connect_fb_webhook"),   # ผูกเพจกับ Messenger webhook (แอดมิน)
    path("api/config", V.api_config, name="connect_config"),
    path("api/stats", V.api_stats, name="connect_stats"),
    path("api/test", V.api_test, name="connect_test"),     # โหมดทดสอบ (แอดมิน): บัญชีเซลล์/ลูกค้าจำลอง
]
