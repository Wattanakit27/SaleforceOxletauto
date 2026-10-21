#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Auto-deploy (13 ต.ค.69 · เจ้าของถาม "ตั้งให้ redeploy เองได้ไหม")
#   systemd timer เรียกทุก 1 นาที → เช็ค GitHub ว่ามีโค้ดใหม่ไหม → มี = ดึงลงมา
#   → (pip ถ้า requirements เปลี่ยน) → migrate → (collectstatic ถ้า static เปลี่ยน) → restart
#   ไม่มีของใหม่ = ไม่ทำอะไรเลย (แค่ git fetch)
#
# ★ ทำไมใช้ "เซิร์ฟเวอร์ดึงเอง" ไม่ใช่ GitHub Actions/webhook:
#   ไม่ต้องเปิดช่องให้ภายนอกสั่งเซิร์ฟเวอร์ · ไม่ต้องเก็บกุญแจ SSH ไว้ที่ GitHub ·
#   ใช้สิทธิ์ดึงโค้ดของ root ที่เซิร์ฟเวอร์มีอยู่แล้ว (เหมือนตอนพิมพ์ git pull เอง)
#
# ★ กันพัง:
#   - ดึงแบบ fast-forward เท่านั้น — มีไฟล์ถูกแก้ค้างบนเซิร์ฟเวอร์ = ไม่แตะ แล้วจดเหตุผล
#   - ขั้นไหนล้ม (pip/migrate) = ไม่ restart (เว็บรันโค้ดเดิมต่อ) แล้วจดใน log
#   - restart แล้ว service ไม่ขึ้น = จดใน log ว่า "ไม่ขึ้น"
#   - ทั้งไฟล์อยู่ในฟังก์ชัน main → bash อ่านจบก่อนเริ่ม (สคริปต์นี้อาจถูก git pull ทับระหว่างรัน)
#   - flock ใน service กันรันซ้อน
#
# ดู log: tail -50 /var/log/oxlet-autodeploy.log   ·   journalctl -t oxlet-autodeploy
# ปิดชั่วคราว: systemctl stop oxlet-autodeploy.timer   ·   เปิด: systemctl start oxlet-autodeploy.timer
# ─────────────────────────────────────────────────────────────────────────────

main() {
  set -u
  local LOG="${AUTODEPLOY_LOG:-/var/log/oxlet-autodeploy.log}"
  local SYSTEMCTL="${AUTODEPLOY_SYSTEMCTL:-systemctl}"
  # ชื่อ|โฟลเดอร์|branch|service — เพิ่มเว็บใหม่ = เติมบรรทัด (หรือตั้ง AUTODEPLOY_PROJECTS คั่นด้วย ;)
  local -a PROJECTS
  if [ -n "${AUTODEPLOY_PROJECTS:-}" ]; then
    IFS=';' read -r -a PROJECTS <<<"$AUTODEPLOY_PROJECTS"
  else
    PROJECTS=(
      "SaleForce|/opt/oxlet|main|oxlet"
      "Showroom|/opt/oxletauto_web|feat/plates-postgres|oxletauto"
    )
  fi

  log() {
    local line; line="$(date '+%F %T') $*"
    echo "$line" >>"$LOG"
    command -v logger >/dev/null 2>&1 && logger -t oxlet-autodeploy -- "$*"
    return 0
  }

  deploy_one() {
    local name=$1 dir=$2 branch=$3 svc=$4
    cd "$dir" 2>/dev/null || { log "$name: ไม่พบโฟลเดอร์ $dir"; return 1; }
    git fetch -q origin "$branch" 2>>"$LOG" || { log "$name: ดึงข้อมูลจาก GitHub ไม่ได้ (git fetch)"; return 1; }
    local old new cur
    old=$(git rev-parse HEAD) || return 1
    new=$(git rev-parse "origin/$branch") || return 1
    [ "$old" = "$new" ] && return 0                      # ไม่มีของใหม่ — ปกติที่สุด ไม่จด log
    cur=$(git rev-parse --abbrev-ref HEAD)
    if [ "$cur" != "$branch" ]; then
      log "$name: เซิร์ฟเวอร์อยู่ branch $cur ไม่ใช่ $branch — ข้าม (สลับ branch เองก่อน)"
      return 1
    fi
    if ! git merge-base --is-ancestor "$old" "$new"; then
      log "$name: โค้ดบนเซิร์ฟเวอร์มี commit ที่ GitHub ไม่มี — ไม่ deploy (ต้องดูเอง)"
      return 1
    fi
    log "$name: พบโค้ดใหม่ ${old:0:7} → ${new:0:7} ($(git log -1 --format=%s "$new" | cut -c1-80))"
    if ! git merge -q --ff-only "origin/$branch" >>"$LOG" 2>&1; then
      log "$name: ดึงโค้ดไม่ได้ (น่าจะมีไฟล์ถูกแก้ค้างบนเซิร์ฟเวอร์ ดูด้วย git status) — ไม่ deploy"
      return 1
    fi
    local changed py
    changed=$(git diff --name-only "$old" "$new")
    py="$dir/.venv/bin/python"

    if grep -qx 'requirements.txt' <<<"$changed"; then
      local pw_old pw_new
      pw_old=$("$py" -m pip show playwright 2>/dev/null | awk '/^Version:/{print $2}')
      if ! "$py" -m pip install -q -r requirements.txt >>"$LOG" 2>&1; then
        log "$name: pip install ไม่สำเร็จ — ไม่ restart (เว็บรันโค้ดเดิมต่อ)"
        return 1
      fi
      pw_new=$("$py" -m pip show playwright 2>/dev/null | awk '/^Version:/{print $2}')
      # Playwright แต่ละเวอร์ชันผูก Chromium คนละ build — อัปเกรดแล้วไม่ลงใหม่ = แคปรูปรายงานพังเงียบ (DEPLOY.md)
      if [ -n "$pw_new" ] && [ "$pw_old" != "$pw_new" ]; then
        local pwpath; pwpath=$(grep -m1 '^PLAYWRIGHT_BROWSERS_PATH=' .env 2>/dev/null | cut -d= -f2-)
        if PLAYWRIGHT_BROWSERS_PATH="${pwpath:-}" "$py" -m playwright install chromium >>"$LOG" 2>&1; then
          [ -n "$pwpath" ] && chown -R --reference="$dir" "$pwpath" 2>/dev/null
          log "$name: Playwright $pw_old → $pw_new ลง Chromium ใหม่แล้ว"
        else
          log "$name: Playwright $pw_old → $pw_new แต่ลง Chromium ไม่สำเร็จ — รายงานเข้าไลน์อาจแคปรูปไม่ได้"
        fi
      fi
    fi

    if ! "$py" manage.py migrate --noinput >>"$LOG" 2>&1; then
      log "$name: migrate ไม่สำเร็จ — ไม่ restart (ดูรายละเอียดใน $LOG)"
      return 1
    fi
    if grep -q 'static/' <<<"$changed"; then
      "$py" manage.py collectstatic --noinput >>"$LOG" 2>&1 || log "$name: collectstatic ไม่สำเร็จ (หน้าเว็บอาจได้ CSS/JS เก่า)"
    fi

    if ! $SYSTEMCTL restart "$svc" >>"$LOG" 2>&1; then
      log "$name: restart $svc ไม่สำเร็จ"
      return 1
    fi
    sleep "${AUTODEPLOY_WAIT:-4}"
    if $SYSTEMCTL is-active --quiet "$svc"; then
      log "$name: deploy ${new:0:7} สำเร็จ"
    else
      log "$name: ⚠ restart แล้ว $svc ไม่ขึ้น — ดู journalctl -u $svc -n 50"
      return 1
    fi
  }

  local p rc=0
  for p in "${PROJECTS[@]}"; do
    [ -z "$p" ] && continue
    IFS='|' read -r n d b s <<<"$p"
    ( deploy_one "$n" "$d" "$b" "$s" ) || rc=1           # subshell: cd ของเว็บหนึ่งไม่ลากอีกเว็บ
  done
  return $rc
}

main "$@"
