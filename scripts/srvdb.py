"""ต่อฐานข้อมูลบนเซิร์ฟเวอร์แบบ "อ่านอย่างเดียว" จากเครื่องนี้

ค่าต่อฐานข้อมูลอ่านจาก `.env.serverdb` (ข้าง manage.py · อยู่ใน .gitignore) — เปลี่ยนรหัสแก้ที่ไฟล์นั้นที่เดียว
ไม่พิมพ์รหัสออกมาที่ไหนเลย

    python scripts/srvdb.py --ping                    # ลองต่อ
    python scripts/srvdb.py "SELECT count(*) FROM checkout_chatowner"
    python scripts/srvdb.py --out ผล.txt "SELECT ..."  # เขียนลงไฟล์ (console ไทยของ Windows เพี้ยน)

ใช้ในสคริปต์อื่น: `from srvdb import connect` → `conn = connect()`
"""
import argparse
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_FILE = os.path.join(BASE, ".env.serverdb")
KEYS = ("SRV_DB_HOST", "SRV_DB_PORT", "SRV_DB_NAME", "SRV_DB_USER", "SRV_DB_SSLMODE", "SRV_DB_PASSWORD")


class ConfigError(Exception):
    pass


def load() -> dict:
    """ค่าจากไฟล์ .env.serverdb (ตัวแปรสภาพแวดล้อมชื่อเดียวกันชนะไฟล์)"""
    from dotenv import dotenv_values
    if not os.path.exists(ENV_FILE):
        raise ConfigError("ไม่พบไฟล์ %s" % ENV_FILE)
    vals = dotenv_values(ENV_FILE)
    cfg = {k: (os.environ.get(k) or vals.get(k) or "").strip() for k in KEYS}
    missing = [k for k in KEYS if k != "SRV_DB_PASSWORD" and not cfg[k]]
    if missing:
        raise ConfigError("ไฟล์ .env.serverdb ขาด: %s" % ", ".join(missing))
    if not cfg["SRV_DB_PASSWORD"]:
        raise ConfigError("ยังไม่ได้ใส่รหัส — เติม SRV_DB_PASSWORD= ในไฟล์ %s" % ENV_FILE)
    return cfg


def connect(timeout_sec: int = 30):
    """เปิดการเชื่อมต่อแบบอ่านอย่างเดียว (Postgres ปฏิเสธคำสั่งเขียนทุกชนิด)"""
    import psycopg2
    c = load()
    conn = psycopg2.connect(host=c["SRV_DB_HOST"], port=int(c["SRV_DB_PORT"]), dbname=c["SRV_DB_NAME"],
                            user=c["SRV_DB_USER"], password=c["SRV_DB_PASSWORD"], sslmode=c["SRV_DB_SSLMODE"],
                            connect_timeout=20, application_name="srvdb-readonly",
                            options="-c statement_timeout=%d" % (timeout_sec * 1000))
    conn.set_session(readonly=True, autocommit=True)
    return conn


def main():
    ap = argparse.ArgumentParser(description="อ่านฐานข้อมูลบนเซิร์ฟเวอร์ (อ่านอย่างเดียว)")
    ap.add_argument("sql", nargs="?", help="คำสั่ง SELECT")
    ap.add_argument("--ping", action="store_true", help="แค่ลองต่อ")
    ap.add_argument("--out", help="เขียนผลลงไฟล์ UTF-8")
    a = ap.parse_args()
    if not a.ping and not a.sql:
        ap.error("ใส่คำสั่ง SQL หรือ --ping")

    lines = []
    try:
        conn = connect()
    except ConfigError as e:
        print("ตั้งค่าไม่ครบ: %s" % e)
        return 2
    except Exception as e:
        print("ต่อไม่ได้: %s" % str(e).strip().splitlines()[0])
        return 1
    with conn, conn.cursor() as cur:
        if a.ping:
            cur.execute("select current_user, now() at time zone 'Asia/Bangkok', "
                        "current_setting('transaction_read_only')")
            who, at, ro = cur.fetchone()
            lines.append("ต่อได้ · บัญชี %s · เวลาเซิร์ฟเวอร์ (ไทย) %s · อ่านอย่างเดียว=%s" % (who, str(at)[:19], ro))
        if a.sql:
            cur.execute(a.sql)
            if cur.description:
                cols = [d[0] for d in cur.description]
                lines.append(" | ".join(cols))
                for r in cur.fetchall():
                    lines.append(" | ".join("" if v is None else str(v) for v in r))
            else:
                lines.append("(ไม่มีผลลัพธ์)")
    text = "\n".join(lines)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        print("เขียนลง %s (%d บรรทัด)" % (a.out, len(lines)))
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
