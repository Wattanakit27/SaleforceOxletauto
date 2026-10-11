"""รูป/ไฟล์ที่ลูกค้าส่งในแชท (LINE OA · Facebook) — ดูสถานะ · โหลดย้อนหลัง · ลบไฟล์ที่หมดอายุ · ★ 11 ต.ค.69

    python manage.py chat_media                       # สถานะ: โหลดแล้ว/รอโหลด/หมดอายุที่ต้นทาง แยก LINE/FB
    python manage.py chat_media --fetch               # โหลดย้อนหลัง 60 วัน (ทั้งหมดที่ยังไม่มี)
    python manage.py chat_media --fetch --days 7 --limit 50
    python manage.py chat_media --cleanup             # ลบไฟล์ของแชทที่ถูกลบไปแล้ว
    python manage.py chat_media --qr                  # อ่าน QR LINE ในรูปที่โหลดไว้แล้ว → เติม ID LINE ให้ลีด
    python manage.py chat_media --out ผล.txt          # เขียนผลลงไฟล์ (console ไทยบน Windows เพี้ยน)

ปกติไม่ต้องรันเอง — รอบ cron ทุกนาทีโหลดไฟล์ 7 วันล่าสุดให้ (chatmedia.sweep_bg) และตอนมีคนเปิดดูก็โหลดให้
ใช้คำสั่งนี้ตอน deploy ครั้งแรก (โหลดของเก่าก่อนที่ LINE จะลบทิ้ง) และตอนอยากรู้ว่าไฟล์เก่าแค่ไหนที่ยังโหลดได้

⚠️ บนเซิร์ฟเวอร์ห้ามรันด้วย root — โฟลเดอร์เก็บไฟล์จะเกิดมาเป็นของ root
   แล้วเว็บ (รันในนาม oxlet) จะเขียนไฟล์ใหม่ไม่ได้อีกเลยแบบเงียบๆ:
       sudo -u oxlet .venv/bin/python manage.py chat_media --fetch
"""
import os
import time
from collections import Counter
from datetime import timedelta
from pathlib import Path

from django.core.management.base import BaseCommand
from django.utils import timezone


def _owner_problem(path: Path) -> str:
    """คนรันไม่ใช่เจ้าของโฟลเดอร์ที่จะเขียน → ข้อความเตือน (ว่าง = ปลอดภัย)"""
    if not hasattr(os, "geteuid"):           # Windows — ไม่มีเรื่องเจ้าของไฟล์แบบนี้
        return ""
    try:
        p = path
        while not p.exists() and p != p.parent:
            p = p.parent                     # ยังไม่มีโฟลเดอร์ = ดูเจ้าของโฟลเดอร์แม่ที่มีอยู่จริง
        owner, me = p.stat().st_uid, os.geteuid()
        if owner == me and me != 0:
            return ""
        import pwd
        nm = pwd.getpwuid(owner).pw_name
        return ("⚠️ กำลังรันในนาม uid %d แต่ %s เป็นของ '%s'\n"
                "   ถ้าสร้างไฟล์ตอนนี้ เว็บ (รันในนาม '%s') จะเขียนไฟล์ใหม่ไม่ได้อีกเลยแบบเงียบๆ\n"
                "   → รันแบบนี้แทน:  sudo -u %s .venv/bin/python manage.py chat_media --fetch"
                % (me, p, nm, nm, nm))
    except Exception:
        return ""


class Command(BaseCommand):
    help = "รูป/ไฟล์ที่ลูกค้าส่งในแชท — สถานะ · โหลดย้อนหลัง · ลบไฟล์หมดอายุ"

    def add_arguments(self, p):
        p.add_argument("--fetch", action="store_true", help="โหลดไฟล์ที่ยังไม่มี (ย้อนหลังตาม --days)")
        p.add_argument("--days", type=int, default=60, help="ย้อนหลังกี่วัน (ค่าตั้งต้น 60 = อายุแชทลูกค้า)")
        p.add_argument("--limit", type=int, default=0, help="โหลดแค่ N ข้อความ (0 = ทั้งหมด)")
        p.add_argument("--cleanup", action="store_true", help="ลบไฟล์ของแชทที่ถูกลบไปแล้ว")
        p.add_argument("--qr", action="store_true",
                       help="อ่าน QR LINE ในรูปที่โหลดไว้แล้ว → เติม ID LINE ให้ลีด (ครั้งเดียวตอน deploy · ไม่เขียนไฟล์)")
        p.add_argument("--out", help="เขียนผลลงไฟล์")

    def handle(self, *a, **o):
        from checkout import chatmedia as CM

        L = []
        add = L.append
        add("ที่เก็บไฟล์: %s" % CM.root())
        if (o["fetch"] or o["cleanup"]):
            warn = _owner_problem(CM.root())
            if warn:
                add(warn)
                add("(ไม่ได้ทำอะไร)")
                self._emit(L, o)
                return

        if o["cleanup"]:
            res = CM.cleanup_files()
            add("ลบไฟล์ของแชทที่หมดอายุ: %d ไฟล์ · เก็บไว้ %d ไฟล์" % (res["deleted"], res["kept"]))

        if o["fetch"]:
            self._fetch(CM, o, add)

        if o["qr"]:
            from checkout import lead_qr
            r = lead_qr.scan_existing(max(1, o["days"]), max(0, o["limit"]))
            add("")
            if not r["lib"]:
                add("อ่าน QR ไม่ได้ — ยังไม่ได้ติดตั้ง zxing-cpp (pip install -r requirements.txt)")
            else:
                add("อ่าน QR LINE ย้อนหลัง %d วัน: %d ข้อความที่มีไฟล์ · อ่านรูป %d รูป · ข้าม (มี ID LINE อยู่แล้ว) %d"
                    % (max(1, o["days"]), r["rows"], r["images"], r["had"]))
                add("  เติม ID LINE จากรูป QR: %d ราย%s" % (r["filled"], (" · แถวแชท " + ", ".join(r["values"][:20])) if r["values"] else ""))

        self._status(CM, o["days"], add)
        self._emit(L, o)

    # ─────────────────────────────────────────────────────
    def _fetch(self, CM, o, add):
        days, limit = max(1, o["days"]), max(0, o["limit"])
        rows = CM.pending(days, limit or 100000)
        if limit:
            rows = rows[:limit]
        add("")
        add("โหลดย้อนหลัง %d วัน: %d ข้อความที่ยังไม่มีไฟล์" % (days, len(rows)))
        t0, now = time.time(), time.time()
        cnt = Counter()
        by_age = {}                           # อายุข้อความ (วัน) → ผล — ใช้ดูว่า LINE เก็บไฟล์ไว้นานแค่ไหน
        for i, (src, row) in enumerate(rows, 1):
            try:
                # ignore พักลองใหม่ 10 นาที — สั่งเองแล้วควรลองจริงทุกแถว
                if CM.parse(row.media_token)[0] == "err":
                    row.media_token = ""
                tok = CM.ensure(src, row, refresh=True, now=now)
                st = CM.parse(tok)[0] or "err"
            except Exception as e:
                st = "err"
                cnt["exc:" + type(e).__name__] += 1
            cnt[("LINE " if src == CM.LINE else "FB ") + st] += 1
            age = (timezone.now() - row.sent_at).days if row.sent_at else -1
            by_age.setdefault((src, age), Counter())[st] += 1
            if i % 25 == 0:
                self.stdout.write("  …%d/%d (%ds)" % (i, len(rows), time.time() - t0))
        add("ใช้เวลา %d วินาที" % (time.time() - t0))
        for k, v in sorted(cnt.items()):
            add("  %-14s %d" % (k, v))
        if by_age:
            add("")
            add("ผลตามอายุข้อความ (วัน) — บอกว่าต้นทางยังเก็บไฟล์ไว้นานแค่ไหน:")
            for (src, age), c in sorted(by_age.items(), key=lambda x: (x[0][0], x[0][1])):
                add("  %s %3d วัน: %s" % ("LINE" if src == CM.LINE else "FB  ", age,
                                          " · ".join("%s %d" % kv for kv in sorted(c.items()))))

    def _status(self, CM, days, add):
        from checkout.models import FbChat, GroupChat
        since = timezone.now() - timedelta(days=max(1, days))
        add("")
        add("สถานะไฟล์ในแชทลูกค้า %d วันล่าสุด (เฉพาะข้อความที่ลูกค้าส่งมา):" % days)
        for name, src, qs in (
            ("LINE", CM.LINE, GroupChat.objects.filter(has_media=True, direction=GroupChat.IN, sent_at__gte=since)
                                              .exclude(chat_type=GroupChat.GROUP)),
            ("FB", CM.FB, FbChat.objects.filter(has_media=True, direction=FbChat.IN, sent_at__gte=since)),
        ):
            c = Counter()
            for tok in qs.values_list("media_token", flat=True).iterator():
                c[CM.parse(tok)[0] or "ยังไม่เคยลอง"] += 1
            total = sum(c.values())
            label = {"ok": "โหลดแล้ว", "err": "พลาดชั่วคราว (จะลองใหม่)", "gone": "หมดอายุที่ต้นทาง",
                     "big": "ใหญ่เกิน", "none": "ไม่มีไฟล์ให้โหลด"}
            add("  %s: %d ข้อความ" % (name, total))
            for k, v in sorted(c.items(), key=lambda x: -x[1]):
                add("     %-26s %d" % (label.get(k, k), v))
        try:
            from dashboard.services import cache_store
            last = (cache_store.get_kv(CM.LAST_KEY) or {}).get("data") or {}
            if last:
                add("")
                add("รอบโหลดอัตโนมัติล่าสุด: %s" % {k: v for k, v in last.items() if k != "cleanup"})
        except Exception:
            pass

    def _emit(self, L, o):
        report = "\n".join(L)
        if o.get("out"):
            with open(o["out"], "w", encoding="utf-8") as f:
                f.write(report)
            self.stdout.write("wrote -> %s" % o["out"])
        else:
            self.stdout.write(report)
