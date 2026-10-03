#!/usr/bin/env bash
# =============================================================================
#  เปิดฐานข้อมูล oxlet ให้คนภายนอกต่อตรงผ่านอินเทอร์เน็ต — อ่านอย่างเดียว
#
#  เจ้าของสั่ง 3 ต.ค.69: "เปิดทุกอย่างให้คนภายนอกอ่านได้ อ่านเท่านั้น · เปิดพอร์ต ·
#  ตั้งไม่ให้ยิงเยอะเกินไป · ทุกตาราง รวมข้อมูลส่วนบุคคล"
#
#  วิธีใช้ (บนเซิร์ฟเวอร์ Hostinger ด้วย root):
#    sudo bash deploy/postgres_online.sh setup          ตั้งค่าครั้งเดียว (รันซ้ำได้ ไม่พัง)
#    sudo bash deploy/postgres_online.sh add <ชื่อ>      เพิ่มบัญชีให้ 1 คน (พิมพ์รหัสให้ครั้งเดียว)
#    sudo bash deploy/postgres_online.sh reset <ชื่อ>    ออกรหัสใหม่ (รหัสเดิมใช้ไม่ได้ทันที)
#    sudo bash deploy/postgres_online.sh remove <ชื่อ>   ถอนสิทธิ์ทันที + ตัดสายที่ต่ออยู่
#    sudo bash deploy/postgres_online.sh list           ใครมีบัญชี · ใครต่ออยู่ตอนนี้ จาก IP ไหน
#    sudo bash deploy/postgres_online.sh close          ปิดพอร์ตกลับเหมือนเดิม
#
#  กันอะไรไว้บ้าง
#    อ่านอย่างเดียว   — ให้แค่ GRANT SELECT (ชั้นที่กันได้จริง) + default_transaction_read_only
#    ไม่ให้ยิงถี่      — ไฟร์วอลล์ ufw limit: IP เดียวกันต่อใหม่ได้ไม่เกิน 6 ครั้ง/30 วินาที
#                      ต่อพร้อมกันได้ 3 สาย/บัญชี · คำสั่งเกิน 30 วิถูกตัด · ไฟล์ชั่วคราวไม่เกิน 1 GB
#    ช่องทาง           — ต้องเข้ารหัส SSL + รหัสผ่าน · เฉพาะบัญชีในกลุ่ม ext_online เท่านั้น
#                      ที่ต่อจากข้างนอกได้ (บัญชีของแอป/postgres/n8n ต่อจากข้างนอกไม่ได้)
#    กุญแจเข้าระบบ     — ซ่อน 4 คอลัมน์ที่เป็นรหัส ไม่ใช่ข้อมูล: auth_user.password ·
#                      dash_tiktok_account.access_token/refresh_token · django_session.session_data
#                      (ถ้าหลุด คนนอกเอาไปแกะรหัสพนักงานแล้ว login เข้าระบบเราได้)
# =============================================================================
set -euo pipefail

DB=oxlet
GROUP=ext_online
PORT=5432
MARK_BEGIN="# >>> oxlet-online (deploy/postgres_online.sh) >>>"
MARK_END="# <<< oxlet-online <<<"
RESERVED="postgres oxlet oxletauto claude n8n ro_all ro_safe $GROUP"

say()  { printf '%s\n' "$*"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m⚠\033[0m %s\n' "$*"; }
die()  { printf '\033[31m✗ %s\033[0m\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "ต้องรันด้วย root: sudo bash $0 $*"

pq() { runuser -u postgres -- psql -d "$DB" -v ON_ERROR_STOP=1 -qAtX "$@"; }

# เช็คจากข้อความเต็มในตัวแปร ไม่ใช้ `| grep -q` — กับ pipefail ถ้า grep เจอแล้วปิดท่อก่อน
# ตัวหน้าจะโดน SIGPIPE แล้วทั้งท่อถูกนับว่าล้ม (ได้คำตอบผิดแบบสุ่ม)
listening_outside() {
  local out re
  out=$(ss -ltn)
  re="(0\.0\.0\.0|\*|\[::\]):${PORT}[[:space:]]"
  [[ $out =~ $re ]]
}

ufw_active() {
  command -v ufw >/dev/null 2>&1 || return 1
  local st; st=$(ufw status 2>/dev/null || true)
  [[ $st == *"Status: active"* ]]
}

restart_pg() {
  if [ -d /run/systemd/system ]; then
    systemctl restart postgresql
  else
    local ver; ver=$(pq -c "show server_version_num"); ver=${ver:0:2}
    pg_ctlcluster "$ver" main restart
  fi
}

# ชื่อเครื่องที่ตรงกับใบรับรอง SSL (คนนอกต้องต่อด้วยชื่อนี้)
server_host() {
  local fq d
  fq=$(hostname -f)
  if [ -d "/etc/letsencrypt/live/$fq" ]; then printf '%s' "$fq"; return; fi
  for d in /etc/letsencrypt/live/*/; do
    [ -d "$d" ] || continue
    d=${d%/}; printf '%s' "${d##*/}"; return
  done
  printf '%s' "$fq"
}

check_name() {
  local n="$1" r
  [[ "$n" =~ ^[a-z][a-z0-9_]{1,30}$ ]] || die "ชื่อบัญชีต้องเป็นอังกฤษตัวเล็ก/ตัวเลข/_ ขึ้นต้นด้วยตัวอักษร 2-31 ตัว (เช่น somchai)"
  for r in $RESERVED; do [ "$n" != "$r" ] || die "ใช้ชื่อ '$n' ไม่ได้ — เป็นบัญชีของระบบ"; done
}

# บัญชีนี้ต้องเป็นบัญชีคนนอกที่สคริปต์นี้สร้าง — กัน reset/remove ไปโดนบัญชีของแอป
check_ext_member() {
  local n="$1" m
  m=$(pq -c "select pg_has_role('$n', '$GROUP', 'member') from pg_roles where rolname = '$n'")
  [ -n "$m" ] || die "ไม่มีบัญชีชื่อ '$n'"
  [ "$m" = "t" ] || die "'$n' ไม่ใช่บัญชีคนนอก (ไม่ได้อยู่ในกลุ่ม $GROUP) — สคริปต์นี้ไม่แตะ"
}

gen_pw() {
  local p
  p=$(openssl rand -base64 64 | tr -dc 'A-Za-z0-9')
  printf '%s' "${p:0:32}"
}

print_conn() {
  local n="$1" pw="$2" host
  host=$(server_host)
  say ""
  say "  ┌─ ส่งให้เจ้าตัว (รหัสแสดงครั้งนี้ครั้งเดียว ระบบไม่ได้เก็บไว้) ─────────────"
  say "  │ Host      $host"
  say "  │ Port      $PORT"
  say "  │ Database  $DB"
  say "  │ User      $n"
  say "  │ Password  $pw"
  say "  │ SSL       require (บังคับ)"
  say "  │"
  say "  │ psql \"host=$host port=$PORT dbname=$DB user=$n sslmode=require\""
  say "  └──────────────────────────────────────────────────────────────────"
  say "  ★ ส่งรหัสคนละช่องทางกับชื่อบัญชี (เช่น ชื่อบัญชีทางอีเมล รหัสทาง LINE)"
}

# -----------------------------------------------------------------------------
cmd_setup() {
  say "== 1/6 กลุ่มสิทธิ์ $GROUP (อ่านได้ทุกตาราง ยกเว้นคอลัมน์รหัส) =="
  pq <<'SQL'
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ext_online') THEN
    CREATE ROLE ext_online NOLOGIN;
  END IF;
END $$;
GRANT CONNECT ON DATABASE oxlet TO ext_online;
GRANT USAGE ON SCHEMA public TO ext_online;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO ext_online;           -- ตาราง + view ทั้งหมด
ALTER DEFAULT PRIVILEGES FOR ROLE oxlet    IN SCHEMA public GRANT SELECT ON TABLES TO ext_online;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT SELECT ON TABLES TO ext_online;

-- คอลัมน์ที่เป็น "กุญแจเข้าระบบ" ไม่ใช่ข้อมูล → ตัดสิทธิ์ทั้งตาราง แล้วคืนให้ทีละคอลัมน์ยกเว้นตัวที่ซ่อน
DO $$
DECLARE r record; cols text;
BEGIN
  FOR r IN SELECT * FROM (VALUES
      ('auth_user',           ARRAY['password']),
      ('dash_tiktok_account', ARRAY['access_token', 'refresh_token']),
      ('django_session',      ARRAY['session_data'])) v(t, hide)
  LOOP
    CONTINUE WHEN to_regclass('public.' || r.t) IS NULL;
    EXECUTE format('REVOKE SELECT ON public.%I FROM ext_online', r.t);
    SELECT string_agg(quote_ident(column_name), ', ' ORDER BY ordinal_position) INTO cols
      FROM information_schema.columns
     WHERE table_schema = 'public' AND table_name = r.t AND column_name <> ALL (r.hide);
    EXECUTE format('GRANT SELECT (%s) ON public.%I TO ext_online', cols, r.t);
  END LOOP;
END $$;
SQL
  local nread nwrite leak
  nread=$(pq -c "select count(*) from pg_class c join pg_namespace n on n.oid=c.relnamespace
                 where n.nspname='public' and c.relkind in ('r','v','m','p')
                   and (has_table_privilege('$GROUP', c.oid, 'SELECT') or has_any_column_privilege('$GROUP', c.oid, 'SELECT'))")
  nwrite=$(pq -c "select count(*) from pg_class c join pg_namespace n on n.oid=c.relnamespace
                  where n.nspname='public' and c.relkind in ('r','v','m','p')
                    and has_table_privilege('$GROUP', c.oid, 'INSERT,UPDATE,DELETE,TRUNCATE')")
  leak=$(pq -c "select count(*) from (values ('auth_user','password'),('dash_tiktok_account','access_token'),
                  ('dash_tiktok_account','refresh_token'),('django_session','session_data')) v(t,c)
                where to_regclass('public.'||t) is not null and has_column_privilege('$GROUP', t, c, 'SELECT')")
  [ "$nwrite" = "0" ] || die "กลุ่ม $GROUP เขียนได้ $nwrite ตาราง — ผิดปกติ หยุดก่อน (ห้าม GRANT INSERT/UPDATE/DELETE)"
  [ "$leak" = "0" ]   || die "คอลัมน์รหัสยังอ่านได้ $leak ช่อง — หยุดก่อน"
  ok "อ่านได้ $nread ตาราง/view · เขียนได้ 0 · คอลัมน์รหัสซ่อนครบ"

  say "== 2/6 ใบรับรอง SSL =="
  local conf_dir le host
  conf_dir=$(dirname "$(pq -c 'show config_file')")
  host=$(server_host)
  le="/etc/letsencrypt/live/$host"
  if [ -f "$le/fullchain.pem" ] && [ -f "$le/privkey.pem" ]; then
    install -o postgres -g postgres -m 0644 "$le/fullchain.pem" "$conf_dir/oxlet-online.crt"
    install -o postgres -g postgres -m 0600 "$le/privkey.pem"   "$conf_dir/oxlet-online.key"
    pq -c "ALTER SYSTEM SET ssl = on"
    pq -c "ALTER SYSTEM SET ssl_cert_file = '$conf_dir/oxlet-online.crt'"
    pq -c "ALTER SYSTEM SET ssl_key_file = '$conf_dir/oxlet-online.key'"
    if [ -d /etc/letsencrypt/renewal-hooks/deploy ]; then
      cat > /etc/letsencrypt/renewal-hooks/deploy/oxlet-postgres.sh <<HOOK
#!/bin/sh
# ต่ออายุใบรับรอง HTTPS แล้ว ก๊อปให้ Postgres ใช้ด้วย (สร้างโดย deploy/postgres_online.sh)
install -o postgres -g postgres -m 0644 $le/fullchain.pem $conf_dir/oxlet-online.crt
install -o postgres -g postgres -m 0600 $le/privkey.pem   $conf_dir/oxlet-online.key
systemctl reload postgresql || true
HOOK
      chmod 755 /etc/letsencrypt/renewal-hooks/deploy/oxlet-postgres.sh
    fi
    ok "ใช้ใบรับรองจริงของ $host (ตัวเดียวกับเว็บ · ต่ออายุเองพร้อมเว็บ)"
  else
    pq -c "ALTER SYSTEM SET ssl = on"
    warn "ไม่เจอใบรับรอง Let's Encrypt — ใช้ใบรับรองชั่วคราวของเครื่อง (ยังเข้ารหัสอยู่ แต่บางโปรแกรมเช่น Power BI อาจเตือน)"
  fi

  say "== 3/6 ฟังจากอินเทอร์เน็ต =="
  pq -c "ALTER SYSTEM SET listen_addresses = '*'"
  ok "listen_addresses = '*' (มีผลหลังรีสตาร์ต)"

  say "== 4/6 กฎใครต่อจากข้างนอกได้ (pg_hba.conf) =="
  local hba bak bad
  hba=$(pq -c "show hba_file")
  if grep -qF "$MARK_BEGIN" "$hba"; then
    ok "มีกฎอยู่แล้ว ไม่แก้ซ้ำ"
  else
    bak="$hba.bak-$(date +%Y%m%d-%H%M%S)"
    cp -p "$hba" "$bak"
    cat >> "$hba" <<HBA

$MARK_BEGIN
# คนภายนอก (สมาชิกกลุ่ม $GROUP) ต่อจากอินเทอร์เน็ตได้ — บังคับ SSL + รหัสผ่าน
hostssl  $DB  +$GROUP  0.0.0.0/0  scram-sha-256
hostssl  $DB  +$GROUP  ::/0       scram-sha-256
# บัญชีอื่นทุกบัญชี (แอป · postgres · n8n) ห้ามต่อจากข้างนอก
host     all  all      0.0.0.0/0  reject
host     all  all      ::/0       reject
$MARK_END
HBA
    if [ "$(pq -c "select count(*) from pg_hba_file_rules where error is not null")" != "0" ]; then
      cp -p "$bak" "$hba"
      die "pg_hba.conf อ่านไม่ผ่าน — คืนไฟล์เดิมแล้ว ไม่มีอะไรเปลี่ยน"
    fi
    ok "เพิ่มกฎแล้ว (สำรองไฟล์เดิมไว้ที่ $bak)"
  fi
  # กฎเก่าที่อยู่ "ก่อน" ของเรา และเปิดให้ทุก IP → จะชนะกฎของเรา ต้องให้คนดู
  bad=$(pq -c "select string_agg(line_number::text || ': ' || type || ' ' || array_to_string(database, ',')
                       || ' ' || array_to_string(user_name, ',') || ' ' || coalesce(address, '') || ' ' || auth_method, E'\n')
               from pg_hba_file_rules
               where type like 'host%' and line_number < (select min(line_number) from pg_hba_file_rules
                                                         where '+$GROUP' = any(user_name))
                 and (address in ('0.0.0.0', '::', 'all', 'samenet') or netmask in ('0.0.0.0', '::'))")
  if [ -n "$bad" ]; then
    warn "มีกฎเก่าที่เปิดให้ทุก IP อยู่ก่อนกฎของเรา (จะชนะกฎของเรา) — ตรวจ/ลบเองใน $hba:"
    printf '      %s\n' "$bad"
  fi

  say "== 5/6 ไฟร์วอลล์ (จำกัดความถี่) =="
  if ufw_active; then
    ufw limit "$PORT/tcp" >/dev/null
    ok "ufw limit $PORT/tcp — IP เดียวกันต่อใหม่เกิน 6 ครั้งใน 30 วินาที = ถูกบล็อกชั่วคราว"
  else
    warn "ufw ไม่ได้เปิดใช้ — ไม่ได้ตั้งตัวจำกัดความถี่ (เปิดเองด้วย: ufw limit $PORT/tcp)"
  fi

  say "== 6/6 รีสตาร์ต Postgres (เว็บสะดุด 2-3 วินาที) =="
  restart_pg
  sleep 3
  listening_outside || die "Postgres ยังไม่ฟังจากภายนอก — ดู: journalctl -u postgresql -n 50"
  ok "Postgres ฟังพอร์ต $PORT จากภายนอกแล้ว"
  [ "$(pq -c 'show ssl')" = "on" ] && ok "SSL เปิดอยู่"

  say ""
  say "เสร็จแล้ว ✓  ต่อไป: sudo bash $0 add <ชื่อคน>"
  say "★ ถ้าคนนอกต่อไม่ติด ให้เช็ค Firewall ในหน้า hPanel ของ Hostinger ว่าเปิดพอร์ต $PORT ด้วย"
}

cmd_add() {
  local n="${1:-}"; [ -n "$n" ] || die "ใส่ชื่อด้วย: $0 add <ชื่อ>"
  check_name "$n"
  [ -n "$(pq -c "select 1 from pg_roles where rolname = '$GROUP'")" ] || die "ยังไม่ได้ setup — รัน: sudo bash $0 setup ก่อน"
  [ -z "$(pq -c "select 1 from pg_roles where rolname = '$n'")" ] || die "มีบัญชี '$n' แล้ว — ออกรหัสใหม่ใช้: $0 reset $n"
  local pw; pw=$(gen_pw)
  pq <<SQL
CREATE ROLE "$n" LOGIN PASSWORD '$pw' IN ROLE $GROUP CONNECTION LIMIT 3;
ALTER ROLE "$n" SET default_transaction_read_only = on;
ALTER ROLE "$n" SET statement_timeout = '30s';
ALTER ROLE "$n" SET idle_in_transaction_session_timeout = '60s';
ALTER ROLE "$n" SET idle_session_timeout = '15min';
ALTER ROLE "$n" SET temp_file_limit = '1GB';
ALTER ROLE "$n" SET timezone = 'Asia/Bangkok';
SQL
  ok "สร้างบัญชี $n แล้ว — อ่านอย่างเดียว · ต่อพร้อมกัน 3 สาย · คำสั่งเกิน 30 วิถูกตัด · เวลาเป็นโซนไทย"
  print_conn "$n" "$pw"
}

cmd_reset() {
  local n="${1:-}"; [ -n "$n" ] || die "ใส่ชื่อด้วย: $0 reset <ชื่อ>"
  check_name "$n"; check_ext_member "$n"
  local pw; pw=$(gen_pw)
  pq >/dev/null <<SQL
ALTER ROLE "$n" PASSWORD '$pw';
SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE usename = '$n';
SQL
  ok "ออกรหัสใหม่ให้ $n แล้ว (รหัสเดิมใช้ไม่ได้ · สายที่ต่ออยู่ถูกตัด)"
  print_conn "$n" "$pw"
}

cmd_remove() {
  local n="${1:-}"; [ -n "$n" ] || die "ใส่ชื่อด้วย: $0 remove <ชื่อ>"
  check_name "$n"; check_ext_member "$n"
  pq >/dev/null <<SQL
ALTER ROLE "$n" NOLOGIN;
SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE usename = '$n';
DROP ROLE "$n";
SQL
  ok "ถอนสิทธิ์ $n แล้ว — ต่อเข้ามาไม่ได้อีก"
}

cmd_list() {
  say "บัญชีคนนอก (กลุ่ม $GROUP):"
  pq -F ' | ' <<SQL
SELECT rpad(r.rolname, 20), CASE WHEN r.rolcanlogin THEN 'ใช้ได้' ELSE 'ปิด' END,
       'ต่ออยู่ ' || (SELECT count(*) FROM pg_stat_activity a WHERE a.usename = r.rolname) || '/' || r.rolconnlimit || ' สาย'
  FROM pg_roles r
 WHERE r.rolname <> '$GROUP' AND pg_has_role(r.oid, '$GROUP', 'member')
 ORDER BY 1;
SQL
  say ""
  say "ต่ออยู่ตอนนี้:"
  pq -F ' | ' <<SQL
SELECT a.usename, coalesce(host(a.client_addr), 'local'), to_char(a.backend_start AT TIME ZONE 'Asia/Bangkok', 'DD/MM HH24:MI'),
       a.state, left(regexp_replace(coalesce(a.query, ''), '\s+', ' ', 'g'), 60)
  FROM pg_stat_activity a JOIN pg_roles r ON r.rolname = a.usename
 WHERE r.rolname <> '$GROUP' AND pg_has_role(r.oid, '$GROUP', 'member')
 ORDER BY a.backend_start;
SQL
  say ""
  if listening_outside; then say "พอร์ต $PORT: เปิดรับจากภายนอก"; else say "พอร์ต $PORT: ปิด (ฟังเฉพาะในเครื่อง)"; fi
}

cmd_close() {
  local hba tmp
  hba=$(pq -c "show hba_file")
  if grep -qF "$MARK_BEGIN" "$hba"; then
    cp -p "$hba" "$hba.bak-$(date +%Y%m%d-%H%M%S)"
    tmp=$(mktemp)
    awk -v b="$MARK_BEGIN" -v e="$MARK_END" '$0==b{skip=1} !skip{print} $0==e{skip=0}' "$hba" > "$tmp"
    cat "$tmp" > "$hba"; rm -f "$tmp"
    ok "ลบกฎใน pg_hba.conf แล้ว"
  fi
  pq -c "ALTER SYSTEM RESET listen_addresses"
  if ufw_active; then
    ufw delete limit "$PORT/tcp" >/dev/null 2>&1 || true
    ok "ปิดพอร์ต $PORT ในไฟร์วอลล์แล้ว"
  fi
  restart_pg; sleep 3
  if listening_outside; then die "Postgres ยังฟังจากภายนอกอยู่ — ดู postgresql.conf"; fi
  ok "ปิดแล้ว — ฐานข้อมูลกลับมาฟังเฉพาะในเครื่องเหมือนเดิม (บัญชีคนนอกยังอยู่ แต่ต่อเข้ามาไม่ได้)"
}

case "${1:-}" in
  setup)  cmd_setup ;;
  add)    cmd_add "${2:-}" ;;
  reset)  cmd_reset "${2:-}" ;;
  remove) cmd_remove "${2:-}" ;;
  list)   cmd_list ;;
  close)  cmd_close ;;
  *) sed -n '2,27p' "$0"; exit 1 ;;
esac
