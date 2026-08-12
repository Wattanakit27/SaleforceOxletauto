@echo off
REM ── รัน dev server บนเครื่อง (Windows) ──
REM DB_HOST ว่าง = ใช้ SQLite (ไม่ต้องมี Postgres) · DEBUG=True = โหมด dev (cookie ไม่ต้อง https)
REM เปิดเว็บที่  http://127.0.0.1:8000/login/?bg=1   (admin / 1234)
cd /d "%~dp0"
set DB_HOST=
set DEBUG=True
set SECURE_SSL_REDIRECT=False
python manage.py runserver 127.0.0.1:8000 --noreload
pause
