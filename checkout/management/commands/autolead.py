# -*- coding: utf-8 -*-
"""เก็บลีดอัตโนมัติ → จองเลขรัน → ส่งใบลงกลุ่ม ADMIN เก็บ Lead (checkout/autolead.py · ไม่จ่ายเซลล์)

    manage.py autolead                       สถานะ + รอบล่าสุด
    manage.py autolead --off / --on          ปิด / เปิดทั้งหมด (เปิด = เริ่มนับจากตอนนี้ ไม่ส่งย้อนหลัง)
    manage.py autolead --drafts on|off       บอทรันเลขใบร่างที่แอดมินพักในกลุ่ม ADMIN เก็บ Lead
    manage.py autolead --warn on|off         บอทเตือนในห้องจ่ายเบอร์ (เลขชน / ออกเลขใหม่ให้ลูกค้าที่มีเลขแล้ว)
    manage.py autolead --after 0             รอกี่นาทีหลังลูกค้าให้เบอร์ก่อนส่งใบ (0 = ส่งทันที)
    manage.py autolead --update on|off       ลูกค้าพิมพ์ข้อมูลเพิ่มหลังส่งใบ → บอทอ้างใบเดิมแล้วส่งใบอัปเดต (กลุ่มจริง)
    manage.py autolead --test-group TestBot  กลุ่มทดสอบ (ชื่อกลุ่ม หรือ group id · off = เลิกใช้)
    manage.py autolead --test-chat 2213,2231 แชทของบัญชีทดสอบ (เลข ChatOwner · ใบไปกลุ่มทดสอบ · off = ล้าง)
    manage.py autolead --test-reset          ล้างเลขทดสอบทั้งหมด (= พิมพ์ "ล้างทดสอบ" ในกลุ่มทดสอบ)
    manage.py autolead --show on|off         ซ้อม: ตอนพักการรันเลข ลูกค้าจริงที่ให้เบอร์ = ใบไม่มีเลข (NLD10-) เข้ากลุ่มทดสอบเท่านั้น
    manage.py autolead --show-resend         ส่งใบซ้อมของทุกเคสวันนี้ใหม่ (ตัวจับล่าสุด) เข้ากลุ่มทดสอบ · --dry = ดูอย่างเดียว
                                             · --since "2026-10-20 00:00" = นับตั้งแต่เวลานั้น
    manage.py autolead --preview             แชทไหนจะได้เลขอะไร (ไม่จองเลข ไม่ส่ง LINE)
    manage.py autolead --run                 ทำรอบเดียวเดี๋ยวนี้ (แชท + ข้อความกลุ่มที่ค้าง + ใบอัปเดต)
"""
import io
import json

from django.core.management.base import BaseCommand, CommandError

from checkout import autolead as AL


def _onoff(v):
    v = (v or "").strip().lower()
    if v not in ("on", "off"):
        raise CommandError("ใส่ on หรือ off")
    return v == "on"


def _resolve_group(arg: str) -> tuple:
    """ชื่อกลุ่ม/group id → (id, ชื่อ) — เฉพาะกลุ่มที่บอทตัวส่งอยู่ (ส่งข้อความเข้าได้จริง)"""
    from checkout.slippost import _kv_groups
    from dashboard.services.line_channels import group_visible_to_push
    groups = _kv_groups()
    a = (arg or "").strip()
    if a in groups:
        x = groups[a] or {}
        if not group_visible_to_push(x):
            raise CommandError("กลุ่ม %s ไม่มีบอทตัวส่งอยู่ — เชิญบอท @693tyhah เข้ากลุ่มแล้วพิมพ์อะไรก็ได้ 1 ครั้งก่อน" % a)
        return a, (x.get("name") or "")
    hits = [(gid, (x or {}).get("name") or "") for gid, x in groups.items()
            if ((x or {}).get("name") or "").strip().lower() == a.lower() and group_visible_to_push(x or {})]
    if not hits:
        raise CommandError("ไม่พบกลุ่มชื่อ \"%s\" ที่บอทตัวส่งอยู่ — เชิญบอทเข้ากลุ่มแล้วพิมพ์อะไรก็ได้ 1 ครั้ง (บอทต้องได้ยินก่อน)" % a)
    if len(hits) > 1:
        raise CommandError("ชื่อ \"%s\" ซ้ำกัน %d กลุ่ม — ใส่ group id แทน: %s" % (a, len(hits), ", ".join(h[0] for h in hits)))
    return hits[0]


class Command(BaseCommand):
    help = "เก็บลีดอัตโนมัติ (ส่งใบลงกลุ่ม ADMIN เก็บ Lead · ไม่จ่ายเซลล์)"

    def add_arguments(self, p):
        p.add_argument("--on", action="store_true")
        p.add_argument("--off", action="store_true")
        p.add_argument("--drafts", default="")
        p.add_argument("--warn", default="")
        p.add_argument("--update", default="")
        p.add_argument("--after", default="")
        p.add_argument("--test-group", dest="test_group", default="")
        p.add_argument("--test-chat", dest="test_chat", default="")
        p.add_argument("--test-reset", dest="test_reset", action="store_true")
        p.add_argument("--show", default="")
        p.add_argument("--show-resend", dest="show_resend", action="store_true")
        p.add_argument("--dry", action="store_true")
        p.add_argument("--since", default="")
        p.add_argument("--preview", action="store_true")
        p.add_argument("--run", action="store_true")
        p.add_argument("--out", default="")

    def handle(self, *a, **o):
        lines = []
        if o["on"] or o["off"]:
            AL.set_enabled(bool(o["on"]))
        for name in ("drafts", "warn", "update"):
            if o[name]:
                AL.set_switch(name, _onoff(o[name]))
        if o["after"] != "":
            try:
                AL.set_after(int(o["after"]))
            except ValueError:
                raise CommandError("--after ใส่เป็นตัวเลขนาที (0–60)")
        if o["test_group"] or o["test_chat"]:
            c = AL.cfg()
            if o["test_group"]:
                if o["test_group"].strip().lower() == "off":
                    c["test_group"], c["test_group_name"] = "", ""
                else:
                    c["test_group"], c["test_group_name"] = _resolve_group(o["test_group"])
            if o["test_chat"]:
                if o["test_chat"].strip().lower() == "off":
                    c["test_chats"] = []
                else:
                    try:
                        ids = [int(x) for x in o["test_chat"].replace(" ", "").split(",") if x]
                    except ValueError:
                        raise CommandError("--test-chat ใส่เลขแชท (ChatOwner) คั่นด้วย , เช่น 2213,2231")
                    from checkout.models import ChatOwner
                    miss = [i for i in ids if not ChatOwner.objects.filter(pk=i).exists()]
                    if miss:
                        raise CommandError("ไม่พบแชท %s" % ", ".join(map(str, miss)))
                    c["test_chats"] = ids
            AL.save_cfg(c)
        if o["test_reset"]:
            lines.append("ล้างเลขทดสอบแล้ว %d รายการ" % AL.test_reset())
        if o["show"]:
            AL.set_show(_onoff(o["show"]))
        c = AL.cfg()
        lines.append("เก็บลีดอัตโนมัติ: %s · เริ่มนับ %s · %s"
                     % ("เปิด" if c["enabled"] else "ปิด", c["since"] or "-",
                        "ส่งทันทีที่ลูกค้าให้เบอร์" if not c["after_min"] else "รอหลังให้เบอร์ %d นาที" % c["after_min"]))
        lines.append("  บอทรันเลขใบร่างในกลุ่ม ADMIN เก็บ Lead: %s · เตือนในห้องจ่ายเบอร์: %s · ใบอัปเดต (ลูกค้าพิมพ์เพิ่ม): %s"
                     % ("เปิด" if c["drafts"] else "ปิด", "เปิด" if c["warn"] else "ปิด", "เปิด" if c["update"] else "ปิด"))
        if c["test_group"]:
            st = AL._test_state()
            lines.append("  กลุ่มทดสอบ: %s (%s) · แชทบัญชีทดสอบ: %s · เลขทดสอบใช้ไป %d · รายการ %d"
                         % (c["test_group_name"] or "-", c["test_group"], ", ".join(map(str, c["test_chats"])) or "-",
                            st["seq"], len(st["items"])))
        else:
            lines.append("  กลุ่มทดสอบ: ยังไม่ได้ตั้ง (--test-group TestBot)")
        if c["show"]:
            lines.append("  ซ้อม (ใบไม่มีเลขลงกลุ่มทดสอบ): %s · ตั้งแต่ %s"
                         % ("ทำงาน" if AL.show_on(c) else
                            ("ไม่ทำงาน — เปิดรันเลขจริงอยู่" if c["enabled"] else "ไม่ทำงาน — ยังไม่ได้ตั้งกลุ่มทดสอบ"),
                            c["show_since"] or "-"))
        else:
            lines.append("  ซ้อม (ใบไม่มีเลขลงกลุ่มทดสอบ): ปิด (--show on)")
        ptr = AL._kv(AL.PTR_KEY)
        lines.append("  อ่านข้อความกลุ่มถึง: %s" % (("#%s (%s)" % (ptr.get("last_id"), ptr.get("at") or "-"))
                                                 if ptr else "ยังไม่เริ่ม (เริ่มจากข้อความล่าสุดตอนรอบแรก)"))
        if o["show_resend"]:
            since = None
            if o["since"]:
                from django.utils import timezone
                from django.utils.dateparse import parse_datetime
                since = parse_datetime(o["since"].strip().replace(" ", "T"))
                if not since:
                    raise CommandError("--since ใส่แบบ \"2026-10-20 00:00\"")
                if timezone.is_naive(since):
                    since = timezone.make_aware(since)
            r = AL.show_resend(since=since, dry=o["dry"])
            if r.get("error"):
                raise CommandError(r["error"])
            lines.append("%s ตั้งแต่ %s: ส่ง %d · ไม่สำเร็จ %d · จะส่ง %d" % ("ดูอย่างเดียว" if o["dry"] else "ส่งใบซ้อมใหม่",
                         r["since"], r["sent"], r["failed"], r["would"]))
            for x in r["rows"]:
                lines.append("  แชท #%s · %s · %s%s" % (x["chat"], x.get("code") or "-", x["d"],
                             (" · เบอร์ %s · ไอดีไลน์ %s · เพิ่มเติม %s" % tuple("มี" if x.get(k) else "-" for k in ("phone", "lineId", "notes")))
                             if "code" in x else (" · " + x.get("why", ""))))
        if o["preview"]:
            r = AL.run(dry=True)
            lines.append("ดูก่อน (ไม่จองเลข ไม่ส่ง): %s" % json.dumps(r, ensure_ascii=False))
        elif o["run"]:
            r = AL.run()
            lines.append("รอบนี้: %s" % json.dumps(r, ensure_ascii=False))
        for key, title in (("autolead_last", "รอบล่าสุด (แชท)"), (AL.LAST_GROUP_KEY, "รอบล่าสุด (ข้อความกลุ่ม)")):
            last = AL._kv(key)
            if last:
                lines.append("%s: %s" % (title, json.dumps(last, ensure_ascii=False)[:1500]))
        text = "\n".join(lines)
        if o["out"]:
            io.open(o["out"], "w", encoding="utf-8").write(text + "\n")
            self.stdout.write("เขียนลง %s แล้ว" % o["out"])
        else:
            self.stdout.write(text)
