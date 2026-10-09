# เสียงพากย์ภาษาไทยด้วย Gemini TTS (คีย์ GEMINI_API_KEY ตัวเดิมของบริษัท)
# เก็บไฟล์ที่สร้างแล้วไว้ใน voice_cache/ — รันซ้ำไม่เสียเงินซ้ำ (ข้อความเดิม = ไฟล์เดิม)
import base64
import hashlib
import io
import os
import time
import wave

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "voice_cache")
MODEL = "gemini-3.8-flash-tts"
VOICE = os.environ.get("OXLET_TTS_VOICE", "Sulafat")       # Warm · เปลี่ยนเสียงได้ด้วยตัวแปรนี้
STYLE = "อบอุ่น เป็นกันเอง ชัดเจน จังหวะสบายๆ เหมือนพนักงานรุ่นพี่สอนน้องใช้แอป"
URL = "https://generativelanguage.googleapis.com/v1beta/interactions"


def _key():
    k = os.environ.get("GEMINI_API_KEY", "")
    if not k:
        try:
            # อ่านเฉพาะคีย์ ไม่โหลดทั้งไฟล์เข้า environment — .env ตั้ง PLAYWRIGHT_BROWSERS_PATH เป็น path ของเซิร์ฟเวอร์
            # ถ้าโหลดทั้งไฟล์ ตัวอัดวิดีโอจะหา Chromium ในเครื่องไม่เจอ
            from dotenv import dotenv_values
            k = dotenv_values(os.path.join(HERE, "..", "..", ".env")).get("GEMINI_API_KEY") or ""
        except Exception:
            pass
    if not k:
        raise SystemExit("ไม่มี GEMINI_API_KEY")
    return k


def _find_audio(obj):
    """หา base64 ของเสียงในคำตอบ (steps[].content[] ที่ type = audio)"""
    if isinstance(obj, dict):
        if obj.get("type") == "audio" and obj.get("data"):
            return obj["data"]
        for v in obj.values():
            r = _find_audio(v)
            if r:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = _find_audio(v)
            if r:
                return r
    return None


def synth(text, voice=VOICE, style=STYLE):
    """ข้อความ → path ไฟล์ WAV (24 kHz · mono · 16-bit)"""
    os.makedirs(CACHE, exist_ok=True)
    h = hashlib.sha1(("%s|%s|%s|%s" % (MODEL, voice, style, text)).encode("utf-8")).hexdigest()[:16]
    path = os.path.join(CACHE, h + ".wav")
    if os.path.exists(path):
        return path
    body = {
        "model": MODEL,
        "input": [{"type": "user_input", "content": [{"type": "text", "text": text,
                                                      "annotations": [{"type": "speech_metadata", "style": style}]}]}],
        "response_format": {"type": "audio"},
        "generation_config": {"speech_config": [{"voice": voice}]},
    }
    last = ""
    for attempt in range(4):
        r = requests.post(URL, params={"key": _key()}, json=body, timeout=120)
        if r.status_code == 200:
            data = _find_audio(r.json())
            if data:
                raw = base64.b64decode(data)
                if raw[:4] != b"RIFF":             # เผื่อได้ PCM ดิบ → ใส่หัว WAV ให้
                    buf = io.BytesIO()
                    with wave.open(buf, "wb") as w:
                        w.setnchannels(1)
                        w.setsampwidth(2)
                        w.setframerate(24000)
                        w.writeframes(raw)
                    raw = buf.getvalue()
                open(path, "wb").write(raw)
                return path
            last = "ไม่มีเสียงในคำตอบ: " + r.text[:300]
        else:
            last = "%s %s" % (r.status_code, r.text[:300])
        time.sleep(2 + attempt * 3)
    raise SystemExit("สร้างเสียงไม่สำเร็จ: " + last)


def duration(path):
    with wave.open(path, "rb") as w:
        return w.getnframes() / float(w.getframerate())


if __name__ == "__main__":
    import sys
    p = synth(sys.argv[1] if len(sys.argv) > 1 else "สวัสดีค่ะ วิดีโอนี้จะพาเซลล์ใช้งานแอปอ๊อกเล็ต")
    print(p, round(duration(p), 2), "วินาที")
