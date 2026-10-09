# อัดวิดีโอสอนใช้แอป Oxlet (ต้นแบบ) — เซลล์ / แอดมิน
#   python record_tutorial.py <seller|admin|all>
# ใช้ไฟล์ต้นแบบ oxlet-mobile-demo.html (ข้อมูลสมมติทั้งหมด) · ได้ไฟล์ .mp4 ในโฟลเดอร์ out/
import json
import os
import shutil
import time
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
DEMO = os.environ.get("OXLET_DEMO") or os.path.join(HERE, "oxlet-mobile-demo.html")
if not os.path.exists(DEMO):
    DEMO = os.path.join(os.path.dirname(HERE), "oxlet-mobile-demo.html")
OUT = os.path.join(HERE, "videos")
TRIM = 1.2   # ตัดช่วงหน้าเปล่าตอนเริ่มอัด (วินาที)
os.makedirs(OUT, exist_ok=True)
os.environ.pop("PLAYWRIGHT_BROWSERS_PATH", None)
from playwright.sync_api import sync_playwright  # noqa: E402

W, H = 1600, 900
FONT = "C:/Windows/Fonts/LeelawUI.ttf"


def sample_images():
    """รูปตัวอย่างสำหรับอัปโหลดในวิดีโอ (ไม่ใช่รูปคนหรือรถจริง)"""
    f = ImageFont.truetype(FONT, 46)
    car = Image.new("RGB", (900, 675), (237, 233, 254))
    d = ImageDraw.Draw(car)
    d.rounded_rectangle((150, 300, 750, 470), 40, fill=(124, 58, 237))
    d.polygon([(260, 300), (340, 200), (580, 200), (660, 300)], fill=(124, 58, 237))
    d.polygon([(300, 300), (360, 225), (450, 225), (450, 300)], fill=(220, 214, 252))
    d.polygon([(470, 300), (470, 225), (560, 225), (620, 300)], fill=(220, 214, 252))
    for cx in (290, 610):
        d.ellipse((cx - 62, 412, cx + 62, 536), fill=(31, 17, 71))
        d.ellipse((cx - 28, 446, cx + 28, 502), fill=(200, 200, 210))
    d.text((450, 600), "รูปตัวอย่าง", font=f, fill=(107, 100, 136), anchor="mm")
    car.save(os.path.join(HERE, "car.jpg"), quality=85)
    me = Image.new("RGB", (600, 600), (124, 58, 237))
    d = ImageDraw.Draw(me)
    d.ellipse((200, 120, 400, 320), fill=(237, 233, 254))
    d.ellipse((110, 340, 490, 720), fill=(237, 233, 254))
    d.text((300, 560), "รูปตัวอย่าง", font=ImageFont.truetype(FONT, 40), fill=(124, 58, 237), anchor="mm")
    me.save(os.path.join(HERE, "selfie.jpg"), quality=85)


STAGE_CSS = """
body { background: #f1edff !important; overflow: hidden !important; }
.notes { display: none !important; }
.page { position: fixed !important; left: 150px; top: 40px; padding: 0 !important; margin: 0 !important; max-width: none !important; display: block !important; }
.device { position: relative !important; top: 0 !important; width: 390px !important; height: 820px !important; box-shadow: 0 30px 70px -20px rgba(60, 30, 140, .45) !important; }
#cap { position: fixed; left: 660px; top: 0; right: 0; bottom: 0; padding: 60px 90px 60px 30px; display: flex; flex-direction: column; justify-content: center; gap: 20px;
       font-family: "Noto Sans Thai", "Leelawadee UI", sans-serif; color: #1f1147; transition: opacity .35s; }
#cap .ey { font-size: 21px; font-weight: 700; color: #7c3aed; letter-spacing: .03em; }
#cap h1 { font-size: 50px; line-height: 1.25; margin: 0; font-weight: 800; }
#cap p { font-size: 27px; line-height: 1.65; margin: 0; color: #4a4466; }
#cap .do { align-self: flex-start; background: #7c3aed; color: #fff; padding: 8px 18px; border-radius: 10px; font-size: 23px; font-weight: 700; }
#cap .stp { display: flex; gap: 6px; margin-top: 10px; }
#cap .stp i { width: 34px; height: 6px; border-radius: 3px; background: #ddd6fe; }
#cap .stp i.on { background: #7c3aed; }
#cur { position: fixed; left: -100px; top: -100px; width: 28px; height: 28px; margin: -14px 0 0 -14px; border-radius: 50%;
       background: rgba(124, 58, 237, .30); border: 3px solid #7c3aed; pointer-events: none; z-index: 99999; }
.rip { position: fixed; width: 76px; height: 76px; margin: -38px 0 0 -38px; border-radius: 50%; border: 5px solid #7c3aed; pointer-events: none; z-index: 99998;
       animation: rip .65s ease-out forwards; }
@keyframes rip { from { transform: scale(.3); opacity: 1; } to { transform: scale(1.25); opacity: 0; } }
#tcard { position: fixed; inset: 0; z-index: 100000; display: none; flex-direction: column; justify-content: center; align-items: flex-start; gap: 22px;
         padding: 0 160px; background: linear-gradient(135deg, #5b21b6, #7c3aed 55%, #a78bfa); color: #fff; font-family: "Noto Sans Thai", "Leelawadee UI", sans-serif; }
#tcard .ey { font-size: 26px; font-weight: 700; opacity: .85; letter-spacing: .04em; }
#tcard h1 { font-size: 76px; line-height: 1.2; margin: 0; font-weight: 800; }
#tcard p { font-size: 30px; line-height: 1.6; margin: 0; opacity: .92; max-width: 1150px; }
"""

STAGE_JS = """
(function(){
  var st = document.createElement('style'); st.textContent = %s; document.head.appendChild(st);
  var cap = document.createElement('div'); cap.id = 'cap'; document.body.appendChild(cap);
  var cur = document.createElement('div'); cur.id = 'cur'; document.body.appendChild(cur);
  var tc = document.createElement('div'); tc.id = 'tcard'; document.body.appendChild(tc);
  document.addEventListener('mousemove', function(e){ cur.style.left = e.clientX + 'px'; cur.style.top = e.clientY + 'px'; }, true);
  window.__rip = function(x, y){ var r = document.createElement('div'); r.className = 'rip'; r.style.left = x + 'px'; r.style.top = y + 'px';
    document.body.appendChild(r); setTimeout(function(){ r.remove(); }, 700); };
  document.addEventListener('mousedown', function(e){ window.__rip(e.clientX, e.clientY); }, true);
  window.__cap = function(n, total, ey, title, text, act){
    cap.style.opacity = 0;
    setTimeout(function(){
      var bar = ''; for (var i = 1; i <= total; i++) bar += '<i class="' + (i <= n ? 'on' : '') + '"></i>';
      cap.innerHTML = '<div class="ey">' + ey + '</div><h1>' + title + '</h1><p>' + text + '</p>' + (act ? '<div class="do">' + act + '</div>' : '') + '<div class="stp">' + bar + '</div>';
      cap.style.opacity = 1;
    }, 200);
  };
  window.__card = function(ey, title, text){
    if (!title) { tc.style.display = 'none'; return; }
    tc.innerHTML = '<div class="ey">' + ey + '</div><h1>' + title + '</h1><p>' + text + '</p>'; tc.style.display = 'flex';
  };
})();
"""


def page_html():
    html = open(DEMO, encoding="utf-8").read()
    # ปิดแจ้งเตือนอัตโนมัติหลัง login — ในวิดีโอสั่งเองตอนถึงขั้นแจ้งเตือน
    html = html.replace('if (S.screen === "main" && !S.D._pushed)', "if (false)")
    head = ("<!doctype html><html lang='th'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'></head><body>")
    path = os.path.join(HERE, "_stage.html")
    open(path, "w", encoding="utf-8").write(head + html + "</body></html>")
    return path


class Rec:
    def __init__(self, pg, total, ey):
        self.pg, self.total, self.ey, self.n = pg, total, ey, 0
        self.t0, self.marks = time.time(), []

    def wait(self, s):
        self.pg.wait_for_timeout(int(s * 1000))

    def cap(self, title, text, act="", hold=0.0):
        self.n += 1
        self.marks.append({"n": self.n, "t": round(max(0.0, time.time() - self.t0 - TRIM), 1), "title": title})
        self.pg.evaluate("([n,t,e,a,b,c]) => window.__cap(n,t,e,a,b,c)", [self.n, self.total, self.ey, title, text, act])
        self.wait(0.6 + hold)

    def card(self, ey, title, text, hold):
        self.pg.evaluate("([a,b,c]) => window.__card(a,b,c)", [ey, title, text])
        self.wait(hold)
        self.pg.evaluate("() => window.__card()")

    def _center(self, sel):
        loc = self.pg.locator("#app " + sel).first
        loc.evaluate("el => el.scrollIntoView({behavior: 'smooth', block: 'center'})")
        self.wait(0.7)
        bb = loc.bounding_box()
        return loc, bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] / 2

    def tap(self, sel, after=1.0):
        _, x, y = self._center(sel)
        self.pg.mouse.move(x, y, steps=22)
        self.wait(0.35)
        self.pg.mouse.down()
        self.pg.mouse.up()
        self.wait(after)

    def fake_tap(self, sel, after=0.6):
        """ชี้ + วงกระเพื่อม แต่ไม่คลิกจริง (ปุ่มเลือกไฟล์ — เลือกไฟล์ด้วย set_input_files แทน)"""
        _, x, y = self._center(sel)
        self.pg.mouse.move(x, y, steps=22)
        self.wait(0.35)
        self.pg.evaluate("([x,y]) => window.__rip(x,y)", [x, y])
        self.wait(after)

    def type(self, sel, text, after=0.8):
        self.tap(sel, after=0.3)
        self.pg.keyboard.type(text, delay=70)
        self.wait(after)

    def scroll(self, px, dur=1.2):
        self.pg.evaluate("(px) => { var b = document.getElementById('body'); if (b) b.scrollBy({top: px, behavior: 'smooth'}); }", px)
        self.wait(dur)

    def js_click(self, sel):
        self.pg.evaluate("(s) => document.querySelector(s).click()", sel)


def seller(r, pg):
    up = os.path.join(HERE, "car.jpg")
    r.card("คู่มือแอป Oxlet · ต้นแบบ", "สอนใช้แอปสำหรับเซลล์",
           "งานวันนี้ · เช็คชื่อ · โทรตาม · แชทลูกค้า · สแกนรถ — ทั้งหมดในมือถือเครื่องเดียว<br>"
           "<span style='font-size:24px;opacity:.8'>ชื่อลูกค้า เบอร์ และรถในวิดีโอนี้เป็นข้อมูลสมมติ</span>", 4.5)
    r.cap("เข้าสู่ระบบ", "กดปุ่มสีเขียว <b>เข้าสู่ระบบด้วย LINE</b><br>ใช้บัญชีเดียวกับเว็บ เข้าครั้งเดียวอยู่ได้ 30 วัน", "แตะ เข้าสู่ระบบด้วย LINE", 1.8)
    r.tap("[data-act=login] >> nth=0", 1.2)
    r.cap("หน้าแรก: งานวันนี้", "ตัวเลขเดือนนี้ของเรา: ลีด · จอง · ปล่อยเทียบเป้า · คะแนนและอันดับ<br>ด้านล่างเรียงงานที่ต้องทำให้แล้ว", "", 3.0)
    r.scroll(520, 2.0)
    r.scroll(520, 2.0)
    r.scroll(-1100, 1.6)
    r.cap("เช็คชื่อเข้างาน", "ถ้ายังไม่เช็คชื่อ จะมีแถบเตือนสีเหลืองบนสุด<br>ถ่ายเซลฟีหน้าร้าน ระบบบอกตำแหน่งและตัดสินตรงเวลา/สายให้เอง", "แตะ เช็คชื่อ", 1.6)
    r.tap("[data-go=checkin]", 1.2)
    r.fake_tap(".selfie", 0.4)
    pg.set_input_files("#ckimg", os.path.join(HERE, "selfie.jpg"))
    r.wait(1.6)
    r.tap("[data-act=docheckin]", 2.2)
    r.cap("ตามด่วน: โทรใครก่อน", "ระบบเรียงลูกค้าให้: ยังไม่โทร · ลูกค้าฮอตที่ค้างนาน · สนใจมาก<br>แตะชื่อเพื่อดูเบอร์โทร", "แตะลูกค้าคนแรก", 1.0)
    r.tap("[data-act=lead] >> nth=0", 1.6)
    r.cap("โทรแล้วบันทึกผล", "เลือกผลการคุยปุ่มเดียว แล้วกดบันทึก<br>ระบบเขียนกลับชีตลีดให้เอง ไม่ต้องเปิดชีต", "เลือก สนใจมาก → บันทึกผล", 1.2)
    r.tap("[data-act=leadz] >> nth=0", 0.8)
    r.tap("[data-act=leadsave]", 2.2)
    r.cap("ดีลค้าง: ดันต่อ", "เคสจองที่ค้างนาน แตะแล้วอัปเดตสถานะได้เลย<br>เช่น รอผล → รอปล่อย", "แตะดีล → เลือกสถานะ → บันทึก", 1.0)
    r.tap("[data-act=deal] >> nth=0", 1.4)
    r.tap("[data-act=dealz] >> nth=3", 0.8)
    r.tap("[data-act=dealsave]", 2.2)
    r.cap("แชทลูกค้า", "คิวรอรับ = ลูกค้าใหม่ที่ทักเข้ามาในวันเวรของทีม · ใครกดรับก่อนได้ลูกค้า<br>ตัวเลขแดงบนแท็บ = ลูกค้ารอเราตอบ", "แตะแท็บ แชท", 1.2)
    r.tap("[data-t=chat]", 1.6)
    r.tap(".row >> nth=0", 1.6)
    r.cap("รับลูกค้า", "ในคิวจะเห็นแค่ข้อความล่าสุดของลูกค้า<br>กด <b>รับลูกค้าคนนี้</b> แล้วลูกค้าเป็นของเรา เห็นแชททั้งหมด", "แตะ รับลูกค้าคนนี้", 1.4)
    r.tap("[data-act=claim]", 2.0)
    r.cap("ตอบลูกค้า", "ใช้ข้อความสำเร็จรูป หรือพิมพ์เองก็ได้ ส่งรูปได้ด้วย<br>ครั้งแรกของแต่ละแชท ระบบถามยืนยันก่อนส่ง", "แตะข้อความสำเร็จรูป → ส่ง", 1.0)
    r.tap("[data-act=quick] >> nth=0", 1.0)
    r.tap("#sendb", 1.4)
    r.tap("[data-act=sendok]", 1.0)
    r.cap("ลูกค้าตอบกลับ", "ข้อความใหม่ขึ้นเองภายในไม่กี่วินาที ไม่ต้องกดรีเฟรช", "", 3.8)
    r.cap("ข้อมูลลูกค้า", "เบอร์โทร / ID LINE ที่ลูกค้าให้ ระบบจับจากแชทให้เอง<br>เลือกสถานะลูกค้าได้ในแตะเดียว", "แตะ ข้อมูล", 0.8)
    r.tap("[data-go=custinfo]", 1.6)
    r.tap("[data-act=zset] >> nth=0", 2.0)
    r.tap("[data-act=back]", 0.8)
    r.tap("[data-act=back]", 1.0)
    r.cap("รถ: สแกน QR ที่รถ", "ที่ลานรถ แตะปุ่มสแกน แล้วเล็งกล้องไปที่ QR บนรถ<br>(ในวิดีโอนี้ใช้ปุ่มจำลองแทนกล้อง)", "แตะแท็บ รถ → สแกน QR", 1.0)
    r.tap("[data-t=cars]", 1.0)
    r.tap("[data-go=scan]", 1.6)
    r.tap("[data-code=CS0011]", 1.6)
    r.cap("หน้ารถ", "เห็นสเตปปัจจุบัน วันที่ค้าง ประวัติ และใครเบิกรถออกไปอยู่<br>ส่งรายละเอียดรถเข้าแชทลูกค้าได้ในแตะเดียว", "แตะ ส่งให้ลูกค้า", 1.4)
    r.tap("[data-s=sendcar]", 1.4)
    r.tap("[data-act=sendcarto] >> nth=0", 2.6)
    r.tap("[data-act=back]", 0.8)
    r.tap("[data-t=cars]", 0.8)
    r.tap("[data-go=scan]", 1.0)
    r.tap("[data-code=CS0011]", 1.4)
    r.cap("เปลี่ยนสเตปรถ", "เลือกสเตป เช่น <b>จอง</b> · ทุกครั้งต้องแนบรูปและใส่หมายเหตุ<br>เพื่อให้ตามย้อนหลังได้ว่าใครทำอะไร เมื่อไหร่", "แตะ จอง", 1.0)
    r.tap("[data-k=reserve]", 1.2)
    r.fake_tap("[data-up=st] >> nth=0", 0.3)
    pg.set_input_files("#app [data-up=st] >> nth=0", up)
    r.wait(1.4)
    r.type("#note", "ลูกค้าวางมัดจำ 5,000", 0.8)
    r.tap("#confb", 2.4)
    r.scroll(900, 2.0)
    r.cap("แจ้งเตือนเข้ามือถือ", "ลูกค้าใหม่ทัก · ลูกค้ารอเกิน 5 นาที · ตามด่วน 9:00 / 13:00<br>แตะแจ้งเตือนแล้วพาไปหน้านั้นเลย", "", 0.6)
    r.js_click("#simpush")
    r.wait(2.0)
    r.tap(".push", 3.0)
    r.card("สรุป", "วันนี้ → แชท → รถ",
           "เช็คชื่อ · โทรตามแล้วบันทึกผล · รับและตอบลูกค้า · เปลี่ยนสเตปรถพร้อมรูป<br>ทุกอย่างบันทึกเข้าระบบเดียวกับเว็บ", 4.5)


def admin(r, pg):
    r.card("คู่มือแอป Oxlet · ต้นแบบ", "สอนใช้แอปสำหรับแอดมิน",
           "ภาพรวมวันนี้ · ห้องพัก Lead และจ่ายเบอร์ · ดูแลแชทลูกค้า · โอนลูกค้า<br>"
           "<span style='font-size:24px;opacity:.8'>ชื่อลูกค้า เบอร์ และรถในวิดีโอนี้เป็นข้อมูลสมมติ</span>", 4.5)
    r.js_click(".roles [data-role=admin]")
    r.wait(0.6)
    r.cap("ภาพรวมวันนี้", "ลีด · จอง · ปล่อยวันนี้ และแชทที่รอรับ / เลยเวลา<br>ไล่ลงมาเป็นห้องพัก Lead · ใครยังไม่เช็คชื่อ · รถค้างนาน", "", 3.0)
    r.scroll(480, 2.0)
    r.scroll(480, 2.0)
    r.scroll(-1000, 1.4)
    r.cap("ห้องพัก Lead", "ลีดทุกช่องทาง (LINE · Facebook · TikTok · เบอร์กลาง) ที่ให้เบอร์แล้ว<br>เรียงรอนานสุดก่อน เกิน 30 นาทีขึ้นสีแดง", "แตะแท็บ ห้องพัก", 1.0)
    r.tap("[data-t=hub]", 2.0)
    r.cap("กรองตามช่องทาง", "อยากดูเฉพาะ TikTok หรือ Facebook แตะปุ่มด้านบน", "แตะ TikTok", 0.6)
    r.tap("[data-act=hubsrc][data-v=tt]", 1.8)
    r.tap("[data-act=hubsrc][data-v=all]", 1.0)
    r.cap("จ่ายเบอร์", "แตะลีดเพื่อเปิด · ระบบแนะนำตัวหน้าให้ (TikTokAds = TALD)<br>เลือกเซลล์ มีป้ายบอกทีมและใครอยู่เวรวันนี้", "แตะลีด → เลือกเซลล์", 0.8)
    r.tap(".hcard >> nth=0", 1.8)
    r.scroll(420, 1.4)
    r.tap("[data-act=hwho][data-v=มัท]", 1.4)
    r.cap("ใบจ่ายลีด", "เห็นเลขที่จะได้และห้องที่จะส่งก่อนกด<br>ใบหน้าตาเดียวกับที่ทีมใช้ในกลุ่มห้องจ่ายเบอร์ คัดลอกได้", "", 1.6)
    r.scroll(380, 2.0)
    r.cap("ส่งเข้ากลุ่ม + แท็กเซลล์", "ยืนยันครั้งเดียว ระบบส่งใบเข้าห้องจ่ายเบอร์และแท็กเซลล์ให้<br>ถ้าเป็นลูกค้าจากแชท ระบบโอนแชทให้เซลล์ด้วย", "แตะ จ่ายเบอร์ + ส่งเข้ากลุ่ม", 1.0)
    r.tap("[data-act=hassign]", 1.6)
    r.tap("[data-act=hdo]", 2.0)
    r.cap("จ่ายแล้ววันนี้", "ดูว่าวันนี้จ่ายให้ใคร โดยใคร ทางไหน<br>แตะชื่อเซลล์เพื่อดูเฉพาะคนนั้น", "แตะ @มัท", 1.0)
    r.tap("[data-act=hubwho] >> nth=0", 2.2)
    r.tap("[data-act=hubwho] >> nth=0", 0.8)
    r.cap("ไม่ใช่ลีดขาย", "ลีดซ้ำ หรือลูกค้าแค่ถามศูนย์บริการ<br>กด <b>ไม่ต้องจ่ายเบอร์</b> ลีดหายจากรายการ เอากลับได้", "", 0.6)
    r.tap("[data-act=hubseg][data-v=wait]", 1.0)
    r.tap(".hcard >> nth=-1", 1.4)
    r.tap("[data-act=hskip]", 2.2)
    r.cap("ดูแลแชทลูกค้า", "แอดมินเห็นทุกแชท: รอรับ · มีเจ้าของ · ทั้งหมด", "แตะแท็บ แชท → ทั้งหมด", 0.8)
    r.tap("[data-t=chat]", 1.2)
    r.tap("[data-act=view][data-v=all]", 1.4)
    r.tap(".row >> nth=2", 1.6)
    r.cap("โอนลูกค้าให้เซลล์", "เปิด <b>ข้อมูล</b> แล้วเลือกโอนให้เซลล์คนอื่น<br>เช่น เจ้าของเดิมลาหรือเข้าไม่ทัน", "แตะ ข้อมูล → โอนให้เซลล์", 0.8)
    r.tap("[data-go=custinfo]", 1.4)
    r.scroll(500, 1.2)
    r.tap("[data-s=transfer]", 1.2)
    r.tap("[data-act=tsave] >> nth=1", 2.2)
    r.tap("[data-act=back]", 0.6)
    r.tap("[data-act=back]", 0.8)
    r.cap("ลีดใหม่เด้งเข้ามือถือ", "มีลีดใหม่เข้าห้องพัก แอดมินได้แจ้งเตือนทันที<br>แตะแล้วเข้าหน้าจ่ายเบอร์ของลีดนั้นเลย", "", 0.4)
    r.js_click("#simpush")
    r.wait(2.0)
    r.tap(".push", 1.8)
    r.scroll(420, 1.2)
    r.tap("[data-act=hwho][data-v=นวล]", 1.0)
    r.scroll(380, 1.2)
    r.tap("[data-act=hassign]", 1.2)
    r.tap("[data-act=hdo]", 2.2)
    r.cap("รถค้างนาน", "จากหน้าภาพรวม แตะรถที่ค้างนาน ดูว่าค้างสเตปไหน ใครทำล่าสุด", "แตะแท็บ ภาพรวม → รถค้างนาน", 0.6)
    r.tap("[data-t=home]", 1.0)
    r.tap("[data-act=car] >> nth=0", 2.0)
    r.scroll(900, 2.2)
    r.card("สรุป", "ภาพรวม → ห้องพัก → แชท",
           "รู้ทันทีว่ามีลีดรอเท่าไหร่ จ่ายเบอร์ให้เซลล์ได้จากมือถือ<br>ดูแลแชทและโอนลูกค้าได้ ไม่ต้องรอเปิดคอม", 4.5)


def record(which):
    stage = page_html()
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        tmp = os.path.join(HERE, "_raw_" + which)
        shutil.rmtree(tmp, ignore_errors=True)
        ctx = b.new_context(viewport={"width": W, "height": H}, color_scheme="light",
                            record_video_dir=tmp, record_video_size={"width": W, "height": H})
        pg = ctx.new_page()
        t_start = time.time()
        import datetime as _dt
        pg.clock.set_fixed_time(_dt.datetime(2026, 10, 9, 9, 42))   # เวลาในแชทตรงกับนาฬิกาบนจอ (9:41)
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto("file:///" + stage.replace("\\", "/"))
        pg.evaluate(STAGE_JS % repr(STAGE_CSS))
        pg.evaluate("() => document.fonts.ready")
        pg.wait_for_timeout(800)
        pg.mouse.move(W / 2, H / 2)
        r = Rec(pg, 15 if which == "seller" else 12, "เซลล์" if which == "seller" else "แอดมิน")
        r.t0 = t_start
        (seller if which == "seller" else admin)(r, pg)
        ctx.close()
        raw = pg.video.path()
        b.close()
    print(which, "steps:", r.n, "errors:", errs)
    mp4 = os.path.join(OUT, "oxlet-%s.mp4" % which)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(TRIM), "-i", raw, "-c:v", "libx264", "-preset", "slow", "-crf", "24",
                    "-pix_fmt", "yuv420p", "-movflags", "+faststart", mp4], check=True)
    print("->", mp4, round(os.path.getsize(mp4) / 1e6, 1), "MB")
    json.dump(r.marks, open(os.path.join(OUT, "oxlet-%s.steps.json" % which), "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    sample_images()
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    for w in (["seller", "admin"] if which == "all" else [which]):
        record(w)
