#!/usr/bin/env bash
# ════════════════════════════════════════════════════════════════════════════
# ย้าย n8n ทั้งก้อน: srv1102218 (เครื่องเดิม · แพ็กเกจหมด 3 พ.ย.69) → srv1793506 (เครื่อง SaleForce)
# ════════════════════════════════════════════════════════════════════════════
# รันบนเครื่อง SaleForce ด้วย root (hPanel → VPS srv1793506 → Browser terminal) — อ่านขั้นตอนใน README.md
#
#   bash /opt/oxlet/deploy/n8n_move/move.sh check      # ดูเฉยๆ ทั้ง 2 เครื่อง ไม่แก้อะไร
#   bash /opt/oxlet/deploy/n8n_move/move.sh prepare    # เตรียมเครื่องใหม่ (n8n เดิมยังทำงานปกติ ไม่มีช่วงหยุด)
#   bash /opt/oxlet/deploy/n8n_move/move.sh cutover    # ย้ายจริง — n8n หยุด ~10–20 นาที (ทำตอนดึก)
#   bash /opt/oxlet/deploy/n8n_move/move.sh webhooks   # URL ที่ต้องไปแก้ใน LINE Developers / Fireflies ฯลฯ
#   bash /opt/oxlet/deploy/n8n_move/move.sh fixurls    # แก้ URL เครื่องเดิมที่ฝังอยู่ในตัว workflow
#   bash /opt/oxlet/deploy/n8n_move/move.sh rollback   # กลับไปใช้เครื่องเดิม (ใช้ได้จนถึง 3 พ.ย.)
#   bash /opt/oxlet/deploy/n8n_move/move.sh cleanup    # ลบไฟล์สำรองทั้ง 2 เครื่อง หลังใช้งานลงตัวแล้ว
#
# หลักการ
#   - ค่าลับ (กุญแจถอดรหัส credential) ดึงจาก container เดิมตรงๆ ลงไฟล์ /opt/n8n/.env — ไม่พิมพ์ออกจอ
#   - เครื่องเดิมถูกแตะแค่ตอน cutover (หยุด n8n + ปิด restart อัตโนมัติ) — ไม่ลบอะไร → rollback ได้
#   - ไม่แตะ SaleForce: gunicorn / Postgres ของ SaleForce / config nginx ของ SaleForce ไม่ถูกแก้
#     (เพิ่มไฟล์ nginx ใหม่ 1 ไฟล์สำหรับ n8n.srv1793506.hstgr.cloud เท่านั้น)
set -Eeuo pipefail

OLD_IP="${OLD_IP:-72.61.114.81}"                       # srv1102218
OLD_DOMAIN="${OLD_DOMAIN:-n8n.srv1102218.hstgr.cloud}"
NEW_DOMAIN="${NEW_DOMAIN:-n8n.srv1793506.hstgr.cloud}"  # DNS ของ Hostinger ชี้ *.srv1793506 มาเครื่องนี้อยู่แล้ว
OLD_PROJECT="${OLD_PROJECT:-root}"                     # ชื่อ docker compose project บนเครื่องเดิม (/root/docker-compose.yml)
CERT_EMAIL="${CERT_EMAIL:-oxletauto@gmail.com}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DIR=/opt/n8n
WORK=/root/n8n_move          # ไฟล์ย้าย (มีข้อมูลลับ) บนเครื่องนี้
OLD_WORK=/root/n8n_move      # ไฟล์ย้ายบนเครื่องเดิม
SOCK=/root/.ssh/cm-n8nmove   # ใช้การเชื่อมต่อ SSH ซ้ำ → ถามรหัสผ่านเครื่องเดิมครั้งเดียว
SSHO=(-o ControlMaster=auto -o "ControlPath=$SOCK" -o ControlPersist=30m
      -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15 -o ServerAliveInterval=30)

say()  { printf '%s\n' "$*"; }
ok()   { printf '  [ok] %s\n' "$*"; }
warn() { printf '  [!!] %s\n' "$*"; }
die()  { printf '\n[หยุด] %s\n' "$*" >&2; exit 1; }
need_root() { [ "$(id -u)" = 0 ] || die "ต้องรันด้วย root"; }
confirm() {
  local ans
  read -r -p "$1 — พิมพ์ YES (ตัวใหญ่) เพื่อทำต่อ: " ans
  [ "$ans" = "YES" ] || die "ยกเลิก (ไม่ได้แก้อะไร)"
}

old()    { ssh "${SSHO[@]}" "root@$OLD_IP" "$@"; }
oldcp()  { scp "${SSHO[@]}" -C -q "root@$OLD_IP:$1" "$2"; }
dc()     { docker compose --project-directory "$DIR" -f "$DIR/docker-compose.yml" "$@"; }
psqlnew(){ dc exec -T postgres psql -U n8n -d n8n -v ON_ERROR_STOP=1 -At "$@"; }

connect_old() {
  [ -S "$SOCK" ] && old true 2>/dev/null && return 0
  mkdir -p /root/.ssh && chmod 700 /root/.ssh
  say "  เชื่อมเครื่องเดิม $OLD_IP — ใส่รหัสผ่าน root ของ srv1102218 (พิมพ์แล้วไม่ขึ้นตัวอักษร เป็นปกติ)"
  old true || die "เข้าเครื่องเดิมไม่ได้ — รหัสผ่านผิด/ลืม: hPanel → VPS srv1102218 → Settings → Root password"
}

wait_healthy() {   # $1 = ชื่อ service · $2 = วินาที
  local i
  for ((i = 0; i < $2; i += 3)); do
    [ "$(docker inspect -f '{{.State.Health.Status}}' "$(dc ps -q "$1")" 2>/dev/null)" = healthy ] && return 0
    sleep 3
  done
  return 1
}

wait_n8n() {
  local i
  for ((i = 0; i < 240; i += 4)); do
    curl -fsS -m 5 http://127.0.0.1:5678/healthz >/dev/null 2>&1 && return 0
    sleep 4
  done
  return 1
}

# ── สคริปต์ที่ส่งไปรันบนเครื่องเดิม (ผ่าน ssh · อ่านจาก stdin) ───────────────────────────
# หา container ด้วย label ของ docker compose — ไม่เดาจากชื่อ
REMOTE_LIB='
set -euo pipefail
P="$1"
c() { docker ps -a --filter "label=com.docker.compose.project=$P" --filter "label=com.docker.compose.service=$1" --format "{{.Names}}" | head -1; }
mnt() { docker inspect -f "{{range .Mounts}}{{if eq .Destination \"$2\"}}{{.Source}}{{end}}{{end}}" "$1"; }
N=$(c n8n); R=$(c n8n-runner); PG=$(c postgres)
[ -n "$N" ] && [ -n "$PG" ] || { echo "ERR ไม่เจอ container n8n/postgres ของโปรเจกต์ $P"; exit 3; }
pq() { docker exec "$PG" psql -U n8n -d n8n -At "$@"; }
'

remote() {   # $1 = เนื้อสคริปต์ · ที่เหลือ = อาร์กิวเมนต์
  local body="$1"; shift
  printf '%s\n%s\n' "$REMOTE_LIB" "$body" | old "bash -s -- $OLD_PROJECT $*"
}

# ════════════════════════════════════════════════════════════════════════════
cmd_check() {
  need_root
  say "== เครื่องนี้ ($(hostname)) =="
  free -m | awk '/^Mem:/{printf "  แรม: ใช้ %d / %d MB · ว่างจริง %d MB\n", $3, $2, $7}'
  free -m | awk '/^Swap:/{ if ($2 == 0) print "  [!!] ไม่มี swap — แนะนำเพิ่ม 4 GB กันแรมพุ่งชั่วขณะ (README หัวข้อทรัพยากร)"; else printf "  swap: %d MB\n", $2 }'
  df -h / | awk 'NR==2{printf "  ดิสก์: ใช้ %s / %s · เหลือ %s\n", $3, $2, $4}'
  if command -v docker >/dev/null; then ok "มี docker แล้ว ($(docker --version | cut -d, -f1))"
  else warn "ยังไม่มี docker (prepare จะลงให้)"; fi
  command -v nginx >/dev/null && ok "มี nginx" || die "ไม่มี nginx — เครื่องนี้ไม่ใช่เครื่อง SaleForce?"
  command -v certbot >/dev/null && ok "มี certbot" || warn "ไม่มี certbot (prepare จะลงให้)"
  if ss -ltnH 2>/dev/null | awk '{print $4}' | grep -qE '[:.]5678$'; then warn "พอร์ต 5678 มีโปรแกรมใช้อยู่แล้ว"
  else ok "พอร์ต 5678 ว่าง"; fi
  local dnsip; dnsip=$(getent ahostsv4 "$NEW_DOMAIN" | awk 'NR==1{print $1}')
  if [ -n "$dnsip" ] && hostname -I | tr ' ' '\n' | grep -qx "$dnsip"; then ok "$NEW_DOMAIN ชี้มาเครื่องนี้ ($dnsip)"
  else warn "$NEW_DOMAIN ชี้ไป '${dnsip:-ไม่มี}' ไม่ตรงกับ IP เครื่องนี้"; fi
  [ -f "$DIR/.env" ] && warn "มี $DIR/.env อยู่แล้ว (เคยรัน prepare)"

  say ""; say "== เครื่องเดิม $OLD_IP (อ่านอย่างเดียว) =="
  connect_old
  remote '
echo "  container: n8n=$N · runner=${R:-ไม่มี} · postgres=$PG"
echo "  สถานะ n8n: $(docker inspect -f "{{.State.Status}} · restart={{.HostConfig.RestartPolicy.Name}}" "$N")"
echo "  เวอร์ชัน n8n: $(docker exec "$N" n8n --version 2>/dev/null | tail -1)"
[ -n "$R" ] && echo "  image runner: $(docker inspect -f "{{.Config.Image}}" "$R")"
echo "  timezone: $(docker exec "$N" printenv GENERIC_TIMEZONE || echo ไม่ได้ตั้ง)"
if [ -n "$(docker exec "$N" printenv N8N_ENCRYPTION_KEY 2>/dev/null)" ]; then echo "  กุญแจถอดรหัส: ตั้งใน env (จะคัดไปให้)"; else echo "  กุญแจถอดรหัส: อยู่ในไฟล์ config ของ n8n"; fi
echo "  ฐานข้อมูล n8n: $(pq -c "select pg_size_pretty(pg_database_size(current_database()))")"
echo "  workflow: $(pq -c "select count(*) from workflow_entity") ตัว · webhook ที่ลงทะเบียน: $(pq -c "select count(*) from webhook_entity")"
echo "  ตารางใหญ่สุด:"; pq -F " · " -c "select relname, pg_size_pretty(pg_total_relation_size(oid)) from pg_class where relkind = '"'"'r'"'"' order by pg_total_relation_size(oid) desc limit 5" | sed "s/^/     /"
S=$(mnt "$N" /home/node/.n8n); F=$(mnt "$N" /files)
echo "  โฟลเดอร์ข้อมูล n8n: $(du -sh "$S" 2>/dev/null | cut -f1) ($S)"
[ -n "$F" ] && echo "  โฟลเดอร์ /files: $(du -sh "$F" 2>/dev/null | cut -f1) ($F)"
echo "  ดิสก์เครื่องเดิม: $(df -h / | awk "NR==2{print \$3\" / \"\$2}")"
echo "  docker:"; docker system df --format "{{.Type}}: {{.Size}} (เอาคืนได้ {{.Reclaimable}})" | sed "s/^/     /"
'
  say ""
  say "ดูเสร็จแล้ว — ไม่ได้แก้อะไรทั้ง 2 เครื่อง · ขั้นต่อไป: prepare"
}

# ════════════════════════════════════════════════════════════════════════════
cmd_prepare() {
  need_root
  if [ -f "$DIR/docker-compose.yml" ] && command -v docker >/dev/null \
     && [ -n "$(dc ps -q n8n 2>/dev/null)" ] && [ "$(docker inspect -f '{{.State.Running}}' "$(dc ps -q n8n)")" = true ]; then
    die "n8n บนเครื่องนี้ทำงานอยู่แล้ว — prepare ไม่ต้องรันซ้ำ"
  fi

  say "== 1/6 docker =="
  if ! command -v docker >/dev/null || ! docker compose version >/dev/null 2>&1; then
    apt-get update -qq
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq docker.io docker-compose-v2 >/dev/null \
      || die "ลง docker ไม่สำเร็จ (apt) — ส่งข้อความบนจอให้ Claude ดู"
    systemctl enable --now docker >/dev/null
  fi
  docker compose version >/dev/null || die "docker compose ใช้ไม่ได้"
  ok "$(docker --version | cut -d, -f1) · $(docker compose version --short 2>/dev/null || echo compose)"

  say "== 2/6 อ่านค่าจากเครื่องเดิม (ไม่พิมพ์ค่าลับออกจอ) =="
  connect_old
  local info; info=$(remote '
V=$(docker exec "$N" n8n --version 2>/dev/null | tail -1 | tr -d "\r ")
echo "VERSION=$V"
[ -n "$R" ] && echo "RUNNER_IMAGE=$(docker inspect -f "{{.Config.Image}}" "$R")"
echo "TZ=$(docker exec "$N" printenv GENERIC_TIMEZONE 2>/dev/null || true)"
K=$(docker exec "$N" printenv N8N_ENCRYPTION_KEY 2>/dev/null || true)
if [ -z "$K" ]; then
  K=$(docker exec "$N" cat /home/node/.n8n/config 2>/dev/null | sed -n "s/.*\"encryptionKey\"[[:space:]]*:[[:space:]]*\"\([^\"]*\)\".*/\1/p" | head -1)
fi
echo "KEY=$K"
')
  local VERSION RUNNER_IMAGE TZV KEY
  VERSION=$(sed -n 's/^VERSION=//p' <<<"$info")
  RUNNER_IMAGE=$(sed -n 's/^RUNNER_IMAGE=//p' <<<"$info")
  TZV=$(sed -n 's/^TZ=//p' <<<"$info")
  KEY=$(sed -n 's/^KEY=//p' <<<"$info")
  [[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "อ่านเวอร์ชัน n8n เครื่องเดิมไม่ได้ ('$VERSION')"
  [ -n "$KEY" ] || die "อ่านกุญแจถอดรหัสของ n8n เครื่องเดิมไม่ได้ — ห้ามย้ายต่อ (credential ทุกตัวจะเปิดไม่ได้)"
  [ -n "$RUNNER_IMAGE" ] || RUNNER_IMAGE="n8nio/runners:$VERSION"
  ok "n8n $VERSION · runner $RUNNER_IMAGE · timezone ${TZV:-ไม่ได้ตั้ง (ใช้ค่าตั้งต้นของ n8n)}"

  say "== 3/6 ไฟล์ตั้งค่า $DIR =="
  mkdir -p "$DIR/n8n_data" "$DIR/files"
  chmod 750 "$DIR"
  install -m 644 "$HERE/docker-compose.yml" "$DIR/docker-compose.yml"
  # รหัสฐานข้อมูล/โทเคน runner: ของใหม่สุ่มได้ (ย้ายข้อมูลด้วย pg_dump ไม่ได้ย้ายบัญชี) · รันซ้ำ = ใช้ของเดิม
  local DBPW RTOK
  DBPW=$(sed -n 's/^N8N_DB_PASSWORD=//p' "$DIR/.env" 2>/dev/null || true)
  RTOK=$(sed -n 's/^N8N_RUNNERS_AUTH_TOKEN=//p' "$DIR/.env" 2>/dev/null || true)
  [ -n "$DBPW" ] || DBPW=$(openssl rand -hex 16)
  [ -n "$RTOK" ] || RTOK=$(openssl rand -hex 24)
  ( umask 077
    cat > "$DIR/.env" <<EOF
# สร้างโดย deploy/n8n_move/move.sh prepare — มีค่าลับ ห้ามก๊อปออกนอกเครื่อง
N8N_IMAGE=docker.n8n.io/n8nio/n8n:$VERSION
RUNNER_IMAGE=$RUNNER_IMAGE
N8N_DOMAIN=$NEW_DOMAIN
GENERIC_TIMEZONE=$TZV
N8N_ENCRYPTION_KEY=$KEY
N8N_DB_PASSWORD=$DBPW
N8N_RUNNERS_AUTH_TOKEN=$RTOK
EOF
  )
  chown -R 1000:1000 "$DIR/n8n_data" "$DIR/files"   # n8n ใน container รันเป็น uid 1000 (node)
  ok "$DIR/.env (สิทธิ์ 600) · docker-compose.yml"

  say "== 4/6 โหลด image + เปิดฐานข้อมูลเปล่า (ยังไม่เปิด n8n) =="
  dc pull -q
  dc up -d postgres
  wait_healthy postgres 90 || die "ฐานข้อมูล n8n เปิดไม่ขึ้น — ดู: docker compose -f $DIR/docker-compose.yml logs postgres"
  ok "ฐานข้อมูล n8n พร้อม (ว่างเปล่า รอข้อมูลตอน cutover)"

  say "== 5/6 nginx สำหรับ $NEW_DOMAIN =="
  local site=/etc/nginx/sites-available/n8n
  sed "s/__DOMAIN__/$NEW_DOMAIN/g" "$HERE/nginx-n8n.conf" > "$site.new"
  if [ -f "$site" ] && grep -q "managed by Certbot" "$site"; then
    rm -f "$site.new"; ok "มีไฟล์ nginx + ใบรับรองแล้ว (ไม่ทับ)"
  else
    mv "$site.new" "$site"
    ln -sf "$site" /etc/nginx/sites-enabled/n8n
    if ! nginx -t >/dev/null 2>&1; then
      rm -f /etc/nginx/sites-enabled/n8n
      nginx -t || true
      die "config nginx ไม่ผ่าน — ถอดไฟล์ n8n ออกแล้ว SaleForce ไม่กระทบ"
    fi
    systemctl reload nginx
    ok "เพิ่ม $site แล้ว (ไฟล์ของ SaleForce ไม่ถูกแตะ)"
  fi

  say "== 6/6 ใบรับรอง https =="
  command -v certbot >/dev/null || DEBIAN_FRONTEND=noninteractive apt-get install -y -qq certbot python3-certbot-nginx >/dev/null
  if [ -d "/etc/letsencrypt/live/$NEW_DOMAIN" ]; then
    ok "มีใบรับรองของ $NEW_DOMAIN แล้ว"
  else
    certbot --nginx -d "$NEW_DOMAIN" --redirect --non-interactive --agree-tos -m "$CERT_EMAIL" \
      || die "ขอใบรับรองไม่สำเร็จ — n8n ยังไม่ได้เปิด ไม่มีอะไรเสีย · ส่งข้อความบนจอให้ Claude ดู"
    ok "ได้ใบรับรองแล้ว (ต่ออายุเองพร้อมของเว็บ)"
  fi
  nginx -t >/dev/null 2>&1 && systemctl reload nginx

  say ""
  say "เตรียมเสร็จ — n8n บนเครื่องเดิมยังทำงานตามปกติ · ขั้นต่อไป: cutover (ทำตอนดึก นอกช่วง 06:00–10:00)"
}

# ════════════════════════════════════════════════════════════════════════════
cmd_cutover() {
  need_root
  [ -f "$DIR/.env" ] && [ -f "$DIR/docker-compose.yml" ] || die "ยังไม่ได้รัน prepare"
  [ -n "$(dc ps -q postgres)" ] && wait_healthy postgres 30 || die "ฐานข้อมูล n8n เครื่องนี้ไม่ทำงาน — รัน prepare ใหม่"
  if [ "$(psqlnew -c "select to_regclass('public.workflow_entity') is not null")" = t ] && [ "${FORCE:-}" != 1 ]; then
    die "ฐานข้อมูล n8n เครื่องนี้มีข้อมูลแล้ว (เคย cutover?) — ไม่ทับให้ · ถ้าตั้งใจจริงให้ล้างก่อน (ถาม Claude)"
  fi
  connect_old
  say ""
  say "จะทำ: หยุด n8n เครื่องเดิม → สำรองฐานข้อมูล+ไฟล์ → ย้ายมาเครื่องนี้ → เปิด n8n ที่นี่"
  say "ระหว่างนี้ (~10–20 นาที) workflow ทุกตัวหยุด · ข้อความ LINE ที่ส่งเข้า n8n ช่วงนี้จะไม่ถูกประมวลผล"
  confirm "ย้าย n8n จริง"
  trap 'say ""; warn "ล้มกลางทาง — n8n เครื่องเดิมอาจหยุดอยู่ · กลับไปใช้เครื่องเดิมได้ด้วย: bash $0 rollback"' ERR

  say "== 1/5 เครื่องเดิม: หยุด n8n + สำรองข้อมูล =="
  remote '
W="$2"
mkdir -p "$W"; rm -f "$W"/*
docker update --restart=no "$N" ${R:+"$R"} >/dev/null      # กันเครื่องเดิมรีบูตแล้ว n8n ฟื้นมาทำงานซ้อน
docker stop -t 60 ${R:+"$R"} "$N" >/dev/null
echo "  [ok] หยุด n8n เครื่องเดิมแล้ว (ฐานข้อมูลยังเปิดไว้ให้สำรอง)"
docker exec "$PG" pg_dump -U n8n -d n8n -Fc -f /tmp/n8n_move.dump
docker cp "$PG":/tmp/n8n_move.dump "$W/n8n.dump" && docker exec "$PG" rm -f /tmp/n8n_move.dump
pq -c "select count(*) from workflow_entity" > "$W/workflow_count"
S=$(mnt "$N" /home/node/.n8n); tar -C "$S" -czf "$W/n8n_data.tgz" .
F=$(mnt "$N" /files); if [ -n "$F" ] && [ -d "$F" ]; then tar -C "$F" -czf "$W/files.tgz" .; fi
(cd "$W" && sha256sum * > SHA256SUMS)
echo "  [ok] สำรองแล้ว: $(du -sh "$W" | cut -f1)"
' "$OLD_WORK"

  say "== 2/5 ดึงไฟล์มาเครื่องนี้ =="
  mkdir -p "$WORK" && chmod 700 "$WORK" && rm -f "$WORK"/*
  oldcp "$OLD_WORK/*" "$WORK/"
  ( cd "$WORK" && sha256sum -c --quiet SHA256SUMS ) || die "ไฟล์ที่ดึงมาไม่ครบ/เสีย"
  ok "ได้ครบ $(du -sh "$WORK" | cut -f1) · ตรวจ checksum ผ่าน"

  say "== 3/5 ใส่ข้อมูลเข้าเครื่องนี้ =="
  local pgc; pgc=$(dc ps -q postgres)
  docker cp "$WORK/n8n.dump" "$pgc:/tmp/n8n.dump"
  # pg_restore อาจเตือนเรื่องเจ้าของ/คอมเมนต์ (ไม่กระทบข้อมูล) — ตัดสินจากจำนวน workflow ข้างล่างแทน exit code
  dc exec -T postgres pg_restore -U n8n -d n8n --no-owner --role=n8n /tmp/n8n.dump 2> "$WORK/pg_restore.log" || true
  dc exec -T postgres rm -f /tmp/n8n.dump
  local want got
  want=$(tr -d '[:space:]' < "$WORK/workflow_count")
  got=$(psqlnew -c "select count(*) from workflow_entity" 2>/dev/null || echo 0)
  [ "$want" = "$got" ] || die "workflow เครื่องเดิม $want ตัว แต่ย้ายมาได้ $got ตัว — ดู $WORK/pg_restore.log"
  ok "ฐานข้อมูล: workflow $got ตัว ครบ"
  find "$DIR/n8n_data" -mindepth 1 -delete
  tar -xzf "$WORK/n8n_data.tgz" -C "$DIR/n8n_data"
  [ -f "$WORK/files.tgz" ] && tar -xzf "$WORK/files.tgz" -C "$DIR/files"
  chown -R 1000:1000 "$DIR/n8n_data" "$DIR/files"
  ok "ไฟล์ข้อมูล n8n + /files"

  say "== 4/5 เปิด n8n เครื่องนี้ =="
  dc up -d
  if ! wait_n8n; then
    dc logs --tail 60 n8n || true
    die "n8n ไม่ขึ้นภายใน 4 นาที (log ด้านบน) — กลับเครื่องเดิมได้ด้วย: bash $0 rollback"
  fi
  ok "n8n ทำงานแล้ว (ในเครื่อง)"
  if curl -fsS -m 10 "https://$NEW_DOMAIN/healthz" >/dev/null 2>&1; then ok "เปิดจากข้างนอกได้: https://$NEW_DOMAIN"
  else warn "https://$NEW_DOMAIN/healthz ยังเปิดไม่ได้ — เช็ค nginx/ใบรับรอง"; fi
  trap - ERR

  say "== 5/5 URL ที่ต้องไปแก้ =="
  cmd_webhooks
  say ""
  say "ย้ายเสร็จ — เครื่องเดิมหยุด n8n ไว้ (ไม่ได้ลบ) ใช้ rollback ได้จนแพ็กเกจหมด 3 พ.ย."
}

# ════════════════════════════════════════════════════════════════════════════
cmd_webhooks() {
  need_root
  say "webhook ที่ลงทะเบียนอยู่ (เปลี่ยนแค่ชื่อเครื่อง — path เหมือนเดิม):"
  psqlnew -F '|' -c "select w.name, we.method, we.\"webhookPath\" from webhook_entity we
                     join workflow_entity w on w.id = we.\"workflowId\" order by w.name, we.\"webhookPath\"" |
  while IFS='|' read -r name method path; do
    printf '  %-6s https://%s/webhook/%s\n         ← %s\n' "$method" "$NEW_DOMAIN" "$path" "$name"
  done
  say "  → URL เดิมเหมือนกันทุกตัว แค่ขึ้นต้นด้วย https://$OLD_DOMAIN/ — ไปแก้ที่ LINE Developers (Webhook URL ของแต่ละ channel)"
  say "    · Fireflies (webhook ของ WF0) · และบริการอื่นที่ยิงเข้า n8n"
  say ""
  say "workflow ที่ยังฝังชื่อเครื่องเดิม ($OLD_DOMAIN) ไว้ข้างใน:"
  local n; n=$(psqlnew -c "select count(*) from workflow_entity where nodes::text like '%$OLD_DOMAIN%'")
  if [ "$n" = 0 ]; then ok "ไม่มี"
  else
    psqlnew -c "select name from workflow_entity where nodes::text like '%$OLD_DOMAIN%' order by name" | sed 's/^/  - /'
    say "  → แก้ให้อัตโนมัติด้วย: bash $0 fixurls"
  fi
}

# ════════════════════════════════════════════════════════════════════════════
cmd_fixurls() {
  need_root
  local tables=() t typ n
  for t in workflow_entity workflow_history; do
    [ "$(psqlnew -c "select to_regclass('public.$t') is not null")" = t ] || continue
    n=$(psqlnew -c "select count(*) from $t where nodes::text like '%$OLD_DOMAIN%'")
    say "  $t: $n แถวมี $OLD_DOMAIN"
    [ "$n" = 0 ] || tables+=("$t")
  done
  [ ${#tables[@]} -gt 0 ] || { ok "ไม่มีอะไรต้องแก้"; return 0; }
  confirm "แทน $OLD_DOMAIN ด้วย $NEW_DOMAIN ในตัว workflow (สำรองฐานข้อมูลก่อน)"
  mkdir -p "$WORK" && chmod 700 "$WORK"
  dc exec -T postgres pg_dump -U n8n -d n8n -Fc -f /tmp/before_fixurls.dump
  docker cp "$(dc ps -q postgres):/tmp/before_fixurls.dump" "$WORK/before_fixurls.dump"
  ok "สำรองไว้ที่ $WORK/before_fixurls.dump"
  dc stop n8n-runner n8n
  for t in "${tables[@]}"; do
    typ=$(psqlnew -c "select data_type from information_schema.columns where table_name = '$t' and column_name = 'nodes'")
    psqlnew -c "update $t set nodes = replace(nodes::text, '$OLD_DOMAIN', '$NEW_DOMAIN')::$typ
                where nodes::text like '%$OLD_DOMAIN%'" >/dev/null
    ok "$t แก้แล้ว"
  done
  dc up -d
  wait_n8n && ok "n8n กลับมาทำงานแล้ว" || die "n8n ไม่ขึ้น — ดู: docker compose -f $DIR/docker-compose.yml logs n8n"
}

# ════════════════════════════════════════════════════════════════════════════
cmd_rollback() {
  need_root
  connect_old
  confirm "หยุด n8n เครื่องนี้ แล้วเปิด n8n เครื่องเดิมกลับมา"
  if [ -f "$DIR/docker-compose.yml" ] && command -v docker >/dev/null; then
    dc stop n8n-runner n8n 2>/dev/null || true
    ok "หยุด n8n เครื่องนี้แล้ว (ข้อมูลยังอยู่)"
  fi
  remote '
docker update --restart=always "$N" ${R:+"$R"} >/dev/null
docker start "$N" ${R:+"$R"} >/dev/null
echo "  [ok] เปิด n8n เครื่องเดิมแล้ว: $(docker inspect -f "{{.State.Status}}" "$N")"
'
  say "ถ้าแก้ Webhook URL ใน LINE/Fireflies ไปแล้ว ให้เปลี่ยนกลับเป็น https://$OLD_DOMAIN/..."
}

# ════════════════════════════════════════════════════════════════════════════
cmd_cleanup() {
  need_root
  confirm "ลบไฟล์สำรองการย้าย ($WORK และ $OLD_WORK บนเครื่องเดิม) — ทำหลังใช้งานเครื่องใหม่ลงตัวแล้วเท่านั้น"
  rm -rf "$WORK"
  ok "ลบ $WORK แล้ว"
  # ( ) = die ใน connect_old ออกแค่ subshell — เครื่องเดิมหมดอายุไปแล้วก็ยังลบฝั่งนี้ได้
  if ( connect_old ); then old "rm -rf $OLD_WORK" && ok "ลบ $OLD_WORK บนเครื่องเดิมแล้ว"
  else warn "เข้าเครื่องเดิมไม่ได้ — ข้ามการลบฝั่งนั้น"; fi
  ssh -o "ControlPath=$SOCK" -O exit "root@$OLD_IP" 2>/dev/null || true
}

case "${1:-}" in
  check)    cmd_check ;;
  prepare)  cmd_prepare ;;
  cutover)  cmd_cutover ;;
  webhooks) cmd_webhooks ;;
  fixurls)  cmd_fixurls ;;
  rollback) cmd_rollback ;;
  cleanup)  cmd_cleanup ;;
  *) sed -n '2,16p' "$0"; exit 1 ;;
esac
