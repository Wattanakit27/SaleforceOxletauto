"""ใช้: python scripts/record_tiktok_demo.py <ไฟล์ปลายทาง.mp4>
อัดหน้าสาธิต TikTok เป็นวิดีโอ: เปิดโหมดเล่นอัตโนมัติ → เก็บเฟรมผ่าน CDP screencast → ต่อเป็น MP4 ด้วย ffmpeg"""
import asyncio, base64, os, shutil, subprocess, sys
os.environ.pop("PLAYWRIGHT_BROWSERS_PATH", None)
from playwright.async_api import async_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
URL = "file:///" + os.path.join(ROOT, "deploy", "tiktok_review_demo.html").replace("\\", "/") + "?auto=1"
W, H = 1600, 900
import tempfile
REC = os.path.join(tempfile.gettempdir(), "tiktok_demo_rec")
OUT = sys.argv[1]
FFMPEG = shutil.which("ffmpeg") or r"C:\Users\watta\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-9.0-full_build\bin\ffmpeg.exe"

frames = []  # (timestamp, path)
errors = []


async def main():
    shutil.rmtree(REC, ignore_errors=True)
    os.makedirs(REC)
    async with async_playwright() as p:
        b = await p.chromium.launch()
        ctx = await b.new_context(viewport={"width": W, "height": H}, device_scale_factor=1)
        page = await ctx.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        await page.goto(URL)
        await page.evaluate("document.fonts.ready.then(() => true)")
        await page.wait_for_timeout(1200)
        cdp = await ctx.new_cdp_session(page)

        async def on_frame(e):
            n = len(frames) + 1
            path = os.path.join(REC, f"f{n:05d}.jpg")
            with open(path, "wb") as fh:
                fh.write(base64.b64decode(e["data"]))
            frames.append((e["metadata"]["timestamp"], path))
            try:
                await cdp.send("Page.screencastFrameAck", {"sessionId": e["sessionId"]})
            except Exception:
                pass

        cdp.on("Page.screencastFrame", lambda e: asyncio.ensure_future(on_frame(e)))
        await cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 95, "maxWidth": W, "maxHeight": H, "everyNthFrame": 1})
        await page.wait_for_timeout(600)
        await page.evaluate("play()")
        for _ in range(400):
            if await page.evaluate("window.__done === true"):
                break
            await page.wait_for_timeout(1000)
        await page.wait_for_timeout(500)
        await cdp.send("Page.stopScreencast")
        await page.wait_for_timeout(300)
        await b.close()


asyncio.run(main())
frames.sort()
print("frames:", len(frames), "span: %.1fs" % (frames[-1][0] - frames[0][0]), "errors:", errors)

lst = os.path.join(REC, "list.txt")
with open(lst, "w", encoding="utf-8") as fh:
    fh.write("ffconcat version 1.0\n")
    for i, (ts, path) in enumerate(frames):
        d = (frames[i + 1][0] - ts) if i + 1 < len(frames) else 1.5
        fh.write(f"file '{os.path.basename(path)}'\nduration {max(d, 0.001):.4f}\n")
    fh.write(f"file '{os.path.basename(frames[-1][1])}'\n")

cmd = [FFMPEG, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst,
       "-vf", f"fps=30,scale={W}:{H}:in_range=pc:out_range=tv:flags=lanczos,format=yuv420p",
       "-c:v", "libx264", "-preset", "slow", "-crf", "20", "-color_range", "tv", "-movflags", "+faststart", OUT]
subprocess.run(cmd, check=True, cwd=REC)
print("saved:", OUT, os.path.getsize(OUT) // 1024, "KB")
