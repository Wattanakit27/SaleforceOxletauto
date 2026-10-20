# ★ 21 ต.ค.69 คำที่ระบบจับจากแชท ย้ายจากโค้ดมาเป็นตาราง (แก้ได้ในหน้า "ระบบอัตโนมัติ" ของ CRM)
#   ใส่ค่าตั้งต้นของระบบ (kw_defaults) + ย้ายกฎแท็กของเราจาก KV `autotag_rules` มาเป็นแถวหมวด custom
from django.db import migrations, models


def seed(apps, schema_editor):
    from checkout import kwdb
    KR = apps.get_model("checkout", "KeywordRule")
    kwdb.sync_defaults(model=KR)
    try:
        KV = apps.get_model("dashboard", "KVStore")
        kv = KV.objects.filter(key="autotag_rules").first()
    except Exception:
        kv = None
    data = (kv.data if kv else {}) or {}
    if isinstance(data, dict) and "rules" not in data and isinstance(data.get("data"), dict):
        data = data["data"]
    for i, r in enumerate((data or {}).get("rules") or []):
        if not isinstance(r, dict) or not r.get("id") or not r.get("tag"):
            continue
        if KR.objects.filter(key=str(r["id"])[:80]).exists():
            continue
        KR.objects.create(key=str(r["id"])[:80], group="custom", name=str(r["tag"])[:60],
                          words=list(r.get("words") or []), not_words=list(r.get("not_words") or []),
                          extra={"scope": r.get("scope") if r.get("scope") in ("in", "all") else "in"},
                          tag=True, active=bool(r.get("on", True)), order=i, system=False,
                          updated_by=str(r.get("by") or "")[:80])


class Migration(migrations.Migration):

    dependencies = [
        ("checkout", "0044_chatlead_ad"),
        ("dashboard", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="KeywordRule",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("key", models.CharField(max_length=80, unique=True, verbose_name="รหัส")),
                ("group", models.CharField(db_index=True, max_length=20, verbose_name="หมวด")),
                ("name", models.CharField(max_length=60, verbose_name="ชื่อ / แท็ก")),
                ("value", models.CharField(blank=True, max_length=120, verbose_name="ค่าที่ลงช่อง / บทบาท")),
                ("parent", models.CharField(blank=True, max_length=60, verbose_name="อยู่ใต้ (ยี่ห้อของรุ่น · หมวดของอาชีพ)")),
                ("words", models.JSONField(blank=True, default=list, verbose_name="คำที่จับ")),
                ("pattern", models.TextField(blank=True, verbose_name="รูปแบบขั้นสูง (regex)")),
                ("not_words", models.JSONField(blank=True, default=list, verbose_name="คำยกเว้น")),
                ("extra", models.JSONField(blank=True, default=dict, verbose_name="ค่าเพิ่มเติม")),
                ("tag", models.BooleanField(default=False, verbose_name="ติดแท็กลูกค้า")),
                ("active", models.BooleanField(default=True, verbose_name="เปิดใช้")),
                ("order", models.IntegerField(default=0, verbose_name="ลำดับ")),
                ("system", models.BooleanField(default=False, verbose_name="ค่าตั้งต้นของระบบ")),
                ("edited", models.BooleanField(default=False, verbose_name="คนแก้แล้ว")),
                ("updated_by", models.CharField(blank=True, max_length=80, verbose_name="แก้ล่าสุดโดย")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="สร้างเมื่อ")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="แก้ล่าสุด")),
            ],
            options={
                "verbose_name": "ระบบอัตโนมัติ — คำที่จับ / แท็ก",
                "verbose_name_plural": "ระบบอัตโนมัติ — คำที่จับ / แท็ก",
                "ordering": ["group", "order", "id"],
            },
        ),
        migrations.RunPython(seed, migrations.RunPython.noop),
    ]
