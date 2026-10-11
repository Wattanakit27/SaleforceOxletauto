// หน้า "วันนี้" — ข้อมูลจริงตามบทบาท (GET /api/m/home · ★ 11 ต.ค.69 แทนข้อมูลสมมติในต้นแบบ)
//   เซลล์: เช็คชื่อ · ยอดเดือนนี้ + คะแนน · ลูกค้ารอตอบ · ใบจ่ายลีด (นาฬิกาโทร) · ตามด่วน · ดีลค้าง · รถตรงลูกค้า
//   แอดมิน: ยอดวันนี้ · แชท/ห้องพัก · เช็คชื่อทั้งบริษัท · รถค้าง
//   คนงาน: สแกน QR · รถที่ฉันเบิก · คิวรถของทีม
//   จัดซื้อ: เคสที่ต้องโทร · รุ่นที่ขาดตลาด
// ตัวเลขทุกตัวมาจากตัวเดียวกับเว็บ/ข้อความ LINE (ดู dashboard/services/mobile_home.py)
import { router, useFocusEffect } from 'expo-router';
import { ReactNode, useCallback, useState } from 'react';
import { Linking, Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native';

import { useAuth } from '../../lib/auth';
import { baht, CarRow, CheckinAll, Home, leftText, loadHome, OutRow } from '../../lib/home';
import { Banner, Btn, C, Card, Loading, Tag } from '../../lib/ui';

const TH_MON = ['ม.ค.', 'ก.พ.', 'มี.ค.', 'เม.ย.', 'พ.ค.', 'มิ.ย.', 'ก.ค.', 'ส.ค.', 'ก.ย.', 'ต.ค.', 'พ.ย.', 'ธ.ค.'];
const SECTION_NAME: Record<string, string> = {
  kpi: 'ยอดเดือนนี้', score: 'คะแนน', chats: 'แชท', tasks: 'ใบจ่ายลีด', follow: 'ตามด่วน', carMatch: 'รถตรงลูกค้า',
  numbers: 'ยอดวันนี้', staff: 'เช็คชื่อ', cars: 'รถ', queue: 'คิวรถ', purchase: 'งานจัดซื้อ',
  checkin: 'เช็คชื่อของฉัน', myOut: 'รถที่เบิก',
};

function call(phone?: string) {
  const p = (phone || '').replace(/[^0-9+]/g, '');
  if (p) Linking.openURL('tel:' + p);
}
const openChat = (id: number) => router.push({ pathname: '/chat/[id]', params: { id: String(id) } });
const openCar = (code: string) => router.push({ pathname: '/car/[code]', params: { code } });

export default function Today() {
  const { me } = useAuth();
  const [d, setD] = useState<Home | null>(null);
  const [err, setErr] = useState('');
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async (force: boolean) => {
    try {
      // ตามด่วนมาทีหลัง (คำขอแยก) → เติมเข้าเฉพาะเมื่อยังเป็นรอบเดียวกัน
      const h = await loadHome(force, (merged) => setD((cur) => (cur && cur.now === merged.now ? merged : cur)));
      // ระหว่างรอตามด่วนรอบใหม่ โชว์ของรอบก่อนไว้ก่อน (ไม่กะพริบเป็น "กำลังโหลด" ทุก 60 วิ)
      setD((prev) =>
        h.followLazy && !h.follow && !h.followError && prev?.follow && prev.seller === h.seller
          ? { ...h, follow: prev.follow }
          : h,
      );
      setErr('');
    } catch (e: any) {
      setErr(e?.message || 'โหลดไม่สำเร็จ');
    }
  }, []);

  // เปิดหน้า = ใช้ของที่โหลดไว้ไม่เกิน 45 วิ · เปิดค้างไว้ = โหลดใหม่ทุก 60 วิ
  useFocusEffect(
    useCallback(() => {
      load(false);
      const t = setInterval(() => load(true), 60000);
      return () => clearInterval(t);
    }, [load]),
  );

  const onRefresh = async () => {
    setRefreshing(true);
    await load(true);
    setRefreshing(false);
  };

  if (!d && !err) return <Loading text="กำลังรวบรวมงานวันนี้…" />;

  const errs = Object.keys(d?.errors || {});
  const now = d ? new Date(d.now) : new Date();
  return (
    <ScrollView
      contentContainerStyle={{ padding: 14, gap: 14, paddingBottom: 40 }}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={C.purple} />}>
      {err ? <Banner kind="err" text={err + ' — ดึงลงเพื่อลองใหม่'} /> : null}
      {errs.length ? (
        <Banner kind="warn" text={'บางส่วนโหลดไม่ได้: ' + errs.map((k) => SECTION_NAME[k] || k).join(' · ') + ' — ดึงลงเพื่อโหลดใหม่'} />
      ) : null}
      {d ? (
        <>
          <Card style={{ gap: 8 }}>
            <Text style={st.hello}>สวัสดี {d.me.nickname || me?.nickname}</Text>
            <Text style={st.sub}>
              วัน{d.dayName} {now.getDate()} {TH_MON[now.getMonth()]} {String(now.getFullYear() + 543).slice(-2)}
              {d.me.position ? ` · ${d.me.position}` : ''}
            </Text>
            <CheckinLine c={d.checkin} />
            {d.role === 'seller' && d.chats?.dutyToday ? (
              <Text style={st.sub}>
                เวรรับลูกค้าวันนี้: ทีม {d.chats.dutyToday}
                {d.chats.onDuty ? ' (ทีมคุณเข้าเวร)' : d.chats.dutyTomorrow ? ` · พรุ่งนี้ทีม ${d.chats.dutyTomorrow}` : ''}
              </Text>
            ) : null}
          </Card>
          {d.role === 'admin' ? <AdminBody d={d} /> : null}
          {d.role === 'seller' ? <SellerBody d={d} /> : null}
          {d.role === 'worker' ? <WorkerBody d={d} /> : null}
          {d.role === 'buyer' ? <BuyerBody d={d} /> : null}
          <Text style={st.foot}>ข้อมูลจริงจากระบบ · อัปเดต {String(now.getHours()).padStart(2, '0')}:
            {String(now.getMinutes()).padStart(2, '0')} · ดึงลงเพื่อโหลดใหม่</Text>
        </>
      ) : null}
    </ScrollView>
  );
}

// ─────────────────────────────────────────────────────────────
function CheckinLine({ c }: { c?: Home['checkin'] }) {
  if (!c) return null;
  if (!c.track) return null; // ผู้บริหารที่ไม่ต้องเช็คชื่อ
  const map: Record<string, [string, string, string]> = {
    ontime: ['✓ เช็คชื่อแล้ว ' + (c.time || ''), C.green, C.greenBg],
    late: [`เช็คชื่อแล้ว ${c.time || ''} · สาย${c.lateMin ? ' ' + c.lateMin + ' นาที' : ''}`, C.amber, C.amberBg],
    abnormal: ['เช็คชื่อแล้ว ' + (c.time || '') + ' · อ่านเวลาไม่ออก', C.amber, C.amberBg],
    dayoff: ['วันนี้วันหยุดของคุณ', C.sub, '#eeeeee'],
    none: ['ยังไม่เช็คชื่อ' + (c.workStart ? ` (เข้างาน ${c.workStart})` : '') + ' — ส่งรูปในกลุ่มเช็คชื่อ', C.red, C.redBg],
  };
  const [t, fg, bg] = map[c.status] || map.none;
  return (
    <View style={[st.pill, { backgroundColor: bg }]}>
      <Text style={{ color: fg, fontWeight: '700', fontSize: 14 }}>{t}</Text>
    </View>
  );
}

function Section({ title, right, children, note }: { title: string; right?: ReactNode; children: ReactNode; note?: string }) {
  return (
    <Card style={{ gap: 10 }}>
      <View style={st.secHead}>
        <Text style={st.h2}>{title}</Text>
        {right}
      </View>
      {note ? <Text style={st.sub}>{note}</Text> : null}
      {children}
    </Card>
  );
}

function Kpis({ items }: { items: { label: string; value: string | number; sub?: string; color?: string; onPress?: () => void }[] }) {
  return (
    <View style={st.kpis}>
      {items.map((k, i) => (
        <Pressable key={i} onPress={k.onPress} style={({ pressed }) => [st.kpi, pressed && k.onPress ? { opacity: 0.7 } : null]}>
          <Text style={[st.kpiVal, k.color ? { color: k.color } : null]} numberOfLines={1} adjustsFontSizeToFit>
            {k.value}
          </Text>
          <Text style={st.kpiLabel} numberOfLines={2}>
            {k.label}
          </Text>
          {k.sub ? <Text style={st.kpiSub} numberOfLines={1}>{k.sub}</Text> : null}
        </Pressable>
      ))}
    </View>
  );
}

function SmallBtn({ title, onPress, color = C.purple }: { title: string; onPress: () => void; color?: string }) {
  return (
    <Pressable onPress={onPress} hitSlop={6} style={({ pressed }) => [st.sbtn, { borderColor: color }, pressed && { opacity: 0.6 }]}>
      <Text style={[st.sbtnText, { color }]}>{title}</Text>
    </Pressable>
  );
}

function Empty({ text }: { text: string }) {
  return <Text style={st.empty}>{text}</Text>;
}

function CarLine({ c, onPress }: { c: CarRow; onPress: () => void }) {
  const late = c.flag === 'red' ? C.red : c.flag === 'amber' ? C.amber : C.sub;
  return (
    <Pressable onPress={onPress} style={({ pressed }) => [st.carRow, { borderLeftColor: c.priorityColor || C.line }, pressed && { backgroundColor: C.purpleSoft }]}>
      <View style={{ flex: 1, minWidth: 0, gap: 2 }}>
        <Text style={st.carLabel} numberOfLines={1}>
          {c.label} <Text style={st.carTitle}>{c.title}</Text>
        </Text>
        <Text style={st.sub} numberOfLines={1}>
          {c.stageName} · <Text style={{ color: late, fontWeight: c.flag === 'red' || c.flag === 'amber' ? '700' : '400' }}>
            {c.flag === 'wait' ? 'รอถ่ายรูป ' : ''}
            {c.days} วัน
          </Text>
          {c.priority && c.priority !== 'normal' ? ` · ${c.priorityName}` : ''}
        </Text>
        {c.flags.length ? (
          <View style={st.tags}>
            {c.flags.map((f) => (
              <Tag key={f.key} text={f.name} color="#fff" bg={f.color} />
            ))}
          </View>
        ) : null}
      </View>
      <Text style={st.chev}>›</Text>
    </Pressable>
  );
}

function OutLines({ rows }: { rows?: OutRow[] }) {
  if (!rows?.length) return null;
  return (
    <Section title={`รถที่ฉันเบิกออกไป (${rows.length})`} note="คืนรถในระบบตอนเอารถกลับ — แตะเพื่อเปิดหน้ารถแล้วกด “คืนรถ”">
      {rows.map((o) => (
        <Pressable key={o.code + o.since} onPress={() => o.code && openCar(o.code)} style={st.listRow}>
          <View style={{ flex: 1 }}>
            <Text style={st.rowMain}>{o.plate || o.code} <Text style={st.carTitle}>{o.title}</Text></Text>
            <Text style={[st.sub, o.hours >= 4 && { color: C.red, fontWeight: '700' }]}>
              {o.purpose || '-'}
              {o.destination ? ' · ' + o.destination : ''} · ออกไป {o.hours} ชม.
            </Text>
          </View>
          <Text style={st.chev}>›</Text>
        </Pressable>
      ))}
    </Section>
  );
}

// ─────────────────────────────────────────────────────────────
//  เซลล์
// ─────────────────────────────────────────────────────────────
function SellerBody({ d }: { d: Home }) {
  const [moreUrg, setMoreUrg] = useState(false);
  const k = d.kpi;
  const sc = d.score;
  const ch = d.chats;
  const tk = d.tasks;
  const fu = d.follow;
  const cm = d.carMatch;
  const urgent = fu?.urgent || [];
  return (
    <>
      {k ? (
        <Section title={`ผลงานเดือน ${k.month}`}>
          <Kpis
            items={[
              { label: 'ลีด', value: k.lead },
              { label: 'จอง', value: k.booking },
              { label: 'ปล่อย / เป้า', value: `${k.done}/${k.target || '-'}`, color: k.target && k.done >= k.target ? C.green : undefined },
              { label: 'ยอดปล่อย', value: baht(k.dealValue) },
            ]}
          />
          {sc ? (
            <Pressable onPress={() => router.navigate('/me')} style={st.scoreRow}>
              <Text style={st.scoreBig}>{sc.total}</Text>
              <View style={{ flex: 1 }}>
                <Text style={st.rowMain}>คะแนนเซลล์ · อันดับ {sc.rank}/{sc.of}</Text>
                <Text style={st.sub}>แตะเพื่อดูคะแนนแยก 6 ด้าน</Text>
              </View>
              <Text style={st.chev}>›</Text>
            </Pressable>
          ) : null}
        </Section>
      ) : null}

      {ch ? (
        <Section title="แชทลูกค้า" right={<SmallBtn title="เปิดแชท" onPress={() => router.navigate('/')} />}>
          <Kpis
            items={[
              { label: 'ลูกค้าของฉันรอตอบ', value: ch.mineWaiting || 0, color: ch.mineWaiting ? C.amber : undefined, onPress: () => router.navigate('/') },
              { label: 'เลยเวลาตอบ', value: ch.mineOverdue || 0, color: ch.mineOverdue ? C.red : undefined, onPress: () => router.navigate('/') },
              { label: ch.onDuty ? 'คิวรอรับ (เวรคุณ)' : 'คิวรอรับ', value: ch.onDuty ? ch.queue : '-', sub: ch.onDuty ? '' : 'ไม่ใช่วันเวร', onPress: () => router.navigate('/') },
            ]}
          />
        </Section>
      ) : null}

      {tk ? (
        <Section
          title={`ใบจ่ายลีด — ค้างรายงาน ${tk.open}`}
          note={`รายงานผลในห้องจ่ายเบอร์ภายใน ${tk.callMin} นาทีหลังใบถึงกลุ่ม (พิมพ์ "เลขรัน + ผล")${tk.late ? ` · เลยเวลา ${tk.late} ใบ` : ''}`}>
          {tk.rows.length ? (
            tk.rows.map((t) => (
              <View key={t.code} style={st.listRow}>
                <View style={{ flex: 1, gap: 2 }}>
                  <Text style={st.rowMain}>
                    {t.code} <Text style={st.carTitle}>{t.customer || ''}</Text>
                  </Text>
                  <Text style={st.sub} numberOfLines={1}>{t.car || 'ไม่ระบุรถ'}</Text>
                  <Text style={[st.sub, { fontWeight: '700', color: t.kind === 'overdue' ? C.red : C.amber }]}>
                    {t.kind === 'unsent' ? 'ใบยังไม่ถึงกลุ่ม' : leftText(t.leftMin)}
                  </Text>
                </View>
                <View style={{ gap: 6 }}>
                  {t.phone ? <SmallBtn title="โทร" onPress={() => call(t.phone)} color={C.green} /> : null}
                  {t.chatId ? <SmallBtn title="แชท" onPress={() => openChat(t.chatId as number)} /> : null}
                </View>
              </View>
            ))
          ) : (
            <Empty text={tk.total ? 'รายงานครบทุกใบแล้ว 👍' : 'ยังไม่มีใบจ่ายลีดใน 2 วันนี้'} />
          )}
        </Section>
      ) : null}

      {!fu && d.followLazy ? (
        <Section title="ตามด่วน">
          {d.followError ? (
            <Banner kind="warn" text={'โหลดตามด่วนไม่ได้: ' + d.followError + ' — ดึงลงเพื่อลองใหม่'} />
          ) : (
            <Loading text="กำลังจัดลำดับลีดที่ต้องตาม… (ครั้งแรกของวันอาจใช้ ~10 วินาที)" />
          )}
        </Section>
      ) : null}

      {fu ? (
        <Section
          title={`ตามด่วน — ${fu.follow} เคส`}
          note={`ลีด ${fu.windowDays} วันล่าสุด · ยังไม่โทร ${fu.notCalled} · ไม่มีสถานะ ${fu.noStatus} — ลำดับเดียวกับข้อความ "ตามด่วน" ใน LINE`}>
          {urgent.length ? (
            (moreUrg ? urgent : urgent.slice(0, 5)).map((u) => (
              <View key={u.code} style={st.listRow}>
                <View style={{ flex: 1, gap: 2 }}>
                  <Text style={st.rowMain}>
                    {u.code || '(ไม่มีโค้ด)'} {u.hot ? <Text style={{ color: C.red }}>🔥</Text> : null}
                  </Text>
                  <Text style={[st.sub, { fontWeight: '700', color: u.updates === 0 ? C.red : C.amber }]}>{u.reason}</Text>
                  <Text style={st.sub} numberOfLines={1}>
                    {u.car || 'ไม่ระบุรถ'}
                    {u.status ? ' · ' + u.status : ''} · ไม่ได้แตะ {u.idle} วัน
                  </Text>
                </View>
                <View style={{ gap: 6 }}>
                  {u.phone ? <SmallBtn title="โทร" onPress={() => call(u.phone)} color={C.green} /> : null}
                  {u.chatId ? <SmallBtn title="แชท" onPress={() => openChat(u.chatId as number)} /> : null}
                </View>
              </View>
            ))
          ) : (
            <Empty text="ไม่มีลีดที่ต้องตามด่วน 👍" />
          )}
          {urgent.length > 5 ? (
            <Pressable onPress={() => setMoreUrg(!moreUrg)}>
              <Text style={st.more}>{moreUrg ? 'ย่อ' : `ดูอีก ${urgent.length - 5} เคส`}</Text>
            </Pressable>
          ) : null}
        </Section>
      ) : null}

      {fu?.deals?.length ? (
        <Section title={`ดีลค้าง — ดันต่อ (${fu.deals.length})`}>
          {fu.deals.map((b, i) => (
            <View key={i} style={st.listRow}>
              <View style={{ flex: 1, gap: 2 }}>
                <Text style={st.rowMain}>{b.customer || '-'}</Text>
                <Text style={st.sub} numberOfLines={1}>
                  {b.plate || '-'}
                  {b.car ? ' · ' + b.car : ''}
                </Text>
                <Text style={[st.sub, { color: C.red, fontWeight: '700' }]}>
                  {b.reason} {b.days} วัน · สถานะ {b.status}
                </Text>
              </View>
            </View>
          ))}
        </Section>
      ) : null}

      {cm && cm.customers ? (
        <Section title={`รถพร้อมขายตรงลูกค้าของฉัน (${cm.customers})`} note="ระบบไม่ทักลูกค้าเอง — คุณเลือกเองว่าจะเสนอใคร">
          {cm.rows.map((r, i) => (
            <View key={i} style={st.listRow}>
              <View style={{ flex: 1, gap: 2 }}>
                <Text style={st.rowMain}>{r.customer || r.code}</Text>
                <Text style={st.sub} numberOfLines={1}>อยากได้: {r.want || '-'}</Text>
                <View style={st.tags}>
                  {(r.cars || []).map((c) => (
                    <Pressable key={c.code} onPress={() => c.code && openCar(c.code)}>
                      <Tag text={c.name || c.code} color={C.green} bg={C.greenBg} />
                    </Pressable>
                  ))}
                </View>
              </View>
            </View>
          ))}
        </Section>
      ) : null}

      <OutLines rows={d.myOut} />
    </>
  );
}

// ─────────────────────────────────────────────────────────────
//  แอดมิน / ผู้บริหาร
// ─────────────────────────────────────────────────────────────
function AdminBody({ d }: { d: Home }) {
  const n = d.numbers;
  const ch = d.chats;
  const s = d.staff as CheckinAll | undefined;
  const cars = d.cars;
  const [allMissing, setAllMissing] = useState(false);
  return (
    <>
      {n ? (
        <Section title="วันนี้">
          <Kpis
            items={[
              { label: 'ลีดเข้า', value: n.today.lead, sub: n.today.leadRJ ? `+RJ ${n.today.leadRJ}` : '' },
              { label: 'จอง', value: n.today.booking },
              { label: 'ปล่อย', value: n.today.done, sub: n.today.dealValue ? baht(n.today.dealValue) : '' },
            ]}
          />
          <Text style={st.sub}>
            ทั้งเดือน {n.month}: ลีด {n.monthTotal.lead.toLocaleString()} · จอง {n.monthTotal.booking} · ปล่อย {n.monthTotal.done} ({baht(n.monthTotal.dealValue)})
          </Text>
        </Section>
      ) : null}

      {ch ? (
        <Section title="แชท & จ่ายเบอร์" right={<Text style={st.sub}>เวร: ทีม {ch.dutyToday || '-'}</Text>}>
          <Kpis
            items={[
              { label: 'ลูกค้ารอรับ', value: ch.queue, color: ch.queue ? C.amber : undefined, onPress: () => router.navigate('/') },
              { label: 'รอจ่ายเบอร์', value: (ch.tocode || 0) + (ch.parked || 0) + (ch.pending || 0), color: (ch.tocode || 0) + (ch.parked || 0) + (ch.pending || 0) ? C.red : undefined, onPress: () => router.navigate('/hub') },
              { label: 'ใบจ่ายลีดวันนี้', value: ch.slipsToday ?? '-', sub: ch.callLate ? `เลยเวลารายงาน ${ch.callLate}` : '' },
            ]}
          />
        </Section>
      ) : null}

      {s ? (
        <Section title={`เช็คชื่อ — มาแล้ว ${s.came}/${s.employees}`}>
          <Kpis
            items={[
              { label: 'ตรงเวลา', value: s.ontime, color: C.green },
              { label: 'สาย', value: s.late, color: s.late ? C.amber : undefined },
              { label: 'เลยเวลาแล้วยังไม่มา', value: s.missing.length, color: s.missing.length ? C.red : undefined },
            ]}
          />
          {s.missing.length ? (
            <View style={{ gap: 4 }}>
              <Text style={st.rowMain}>ยังไม่เช็คชื่อ (เลยเวลาเข้างานแล้ว)</Text>
              <Text style={[st.sub, { color: C.red }]}>
                {(allMissing ? s.missing : s.missing.slice(0, 12)).map((m) => `${m.name} (${m.workStart})`).join(' · ')}
              </Text>
              {s.missing.length > 12 ? (
                <Pressable onPress={() => setAllMissing(!allMissing)}>
                  <Text style={st.more}>{allMissing ? 'ย่อ' : `ดูอีก ${s.missing.length - 12} คน`}</Text>
                </Pressable>
              ) : null}
            </View>
          ) : null}
          {s.lateRows.length ? (
            <Text style={st.sub}>สาย: {s.lateRows.map((r) => `${r.name} ${r.time}`).join(' · ')}</Text>
          ) : null}
          <Text style={st.sub}>
            ยังไม่ถึงเวลาเข้างาน {s.notYet} · วันหยุด {s.dayoff}
            {s.noTime ? ` · ยังไม่ได้ตั้งเวลาเข้างาน ${s.noTime}` : ''}
          </Text>
        </Section>
      ) : null}

      {cars ? (
        <Section title="รถในระบบ" right={<SmallBtn title="ดูทั้งหมด" onPress={() => router.navigate('/cars')} />}>
          <Kpis
            items={[
              { label: 'รถทั้งหมด', value: cars.total },
              { label: 'พร้อมขาย', value: cars.ready, color: C.green },
              { label: 'ค้างนาน', value: cars.flags.red || 0, color: cars.flags.red ? C.red : undefined, sub: cars.flags.amber ? `ใกล้ค้าง ${cars.flags.amber}` : '' },
              { label: 'ออกนอกลาน', value: cars.outNow },
            ]}
          />
          {cars.stuck.length ? <Text style={st.rowMain}>ค้างนานสุด</Text> : null}
          {cars.stuck.map((c) => (
            <CarLine key={c.code} c={c} onPress={() => openCar(c.code)} />
          ))}
        </Section>
      ) : null}

      <OutLines rows={d.myOut} />
    </>
  );
}

// ─────────────────────────────────────────────────────────────
//  คนงาน
// ─────────────────────────────────────────────────────────────
function WorkerBody({ d }: { d: Home }) {
  const q = d.queue;
  return (
    <>
      <Btn title="📷  สแกน QR รถ" onPress={() => router.push('/scan')} />
      <OutLines rows={d.myOut} />
      {q ? (
        <Section
          title={q.roleLabel ? `คิวรถของ${q.roleLabel} — ${q.total} คัน` : 'คิวรถของทีม'}
          note={q.stages?.length ? 'สเตป: ' + q.stages.join(' · ') + ' · ติดธงงานค้างขึ้นก่อน → ด่วน → ค้างนาน' : undefined}>
          {q.note ? <Banner kind="info" text={q.note} /> : null}
          {q.rows.length ? (
            q.rows.map((c) => <CarLine key={c.code} c={c} onPress={() => openCar(c.code)} />)
          ) : q.note ? null : (
            <Empty text="ไม่มีรถรอทีมคุณ 👍" />
          )}
          {q.total > q.rows.length ? <Text style={st.sub}>…และอีก {q.total - q.rows.length} คัน (ดูในแท็บ “รถ”)</Text> : null}
        </Section>
      ) : null}
    </>
  );
}

// ─────────────────────────────────────────────────────────────
//  จัดซื้อ
// ─────────────────────────────────────────────────────────────
function BuyerBody({ d }: { d: Home }) {
  const p = d.purchase;
  const [more, setMore] = useState(false);
  if (!p) return null;
  const cases = more ? p.cases : p.cases.slice(0, 12);
  return (
    <>
      <Section title={`เคสรับซื้อที่ต้องตาม (${p.days} วัน)`}>
        <Kpis
          items={[
            { label: 'เคสค้าง', value: p.total },
            { label: 'ยังไม่ได้โทร', value: p.notCalled, color: p.notCalled ? C.red : undefined },
            { label: `ค้าง ≥${p.staleDays} วัน`, value: p.stale, color: p.stale ? C.amber : undefined },
          ]}
        />
        <Text style={st.sub}>ลำดับเดียวกับข้อความในห้องเคสHOT — ยังไม่ได้โทรขึ้นก่อน แล้วค่อยรุ่นที่ขาดตลาด · กรอก “รับซื้อ/ไม่รับซื้อ” ในชีตแล้วเคสหลุดเอง</Text>
        {cases.map((c) => (
          <View key={c.code + c.phone} style={st.listRow}>
            <View style={{ flex: 1, gap: 2 }}>
              <Text style={st.rowMain}>
                {c.code} <Text style={st.carTitle}>{c.name}</Text>
              </Text>
              <Text style={st.sub} numberOfLines={1}>
                {c.car || '-'} · {c.age} วันก่อน
              </Text>
              <View style={st.tags}>
                {!c.talked ? <Tag text="ยังไม่ได้โทร" color={C.red} bg={C.redBg} /> : <Tag text="คุยแล้ว" color={C.sub} bg="#eee" />}
                {c.model ? <Tag text={c.model + (c.gapDemand ? ` · ตลาดถามหา ${c.gapDemand}` : '')} color={C.green} bg={C.greenBg} /> : null}
              </View>
            </View>
            {c.phone ? <SmallBtn title="โทร" onPress={() => call(c.phone)} color={C.green} /> : null}
          </View>
        ))}
        {p.cases.length > 12 ? (
          <Pressable onPress={() => setMore(!more)}>
            <Text style={st.more}>{more ? 'ย่อ' : `ดูอีก ${p.cases.length - 12} เคส`}</Text>
          </Pressable>
        ) : null}
        {p.moreCases ? <Text style={st.sub}>…และอีก {p.moreCases} เคส (ดูทั้งหมดที่หน้าเว็บ /buy/)</Text> : null}
      </Section>

      {p.gap.length ? (
        <Section title="รุ่นที่ขาดตลาด" note="ลูกค้าถามหา 3 เดือนล่าสุด เทียบกับรถพร้อมขาย + เพิ่งรับเข้า">
          <View style={st.gapHead}>
            <Text style={[st.gapCell, { flex: 2, textAlign: 'left' }]}>รุ่น</Text>
            <Text style={st.gapCell}>ถามหา</Text>
            <Text style={st.gapCell}>พร้อมขาย</Text>
            <Text style={st.gapCell}>เพิ่งรับ</Text>
          </View>
          {p.gap.map((g) => (
            <View key={g.key} style={st.gapRow}>
              <Text style={[st.gapCell, { flex: 2, textAlign: 'left', color: C.text, fontWeight: '700' }]} numberOfLines={1}>
                {g.name}
              </Text>
              <Text style={st.gapCell}>{g.demand}</Text>
              <Text style={[st.gapCell, !g.show && { color: C.red, fontWeight: '700' }]}>
                {g.show}
                {!g.show && g.total ? `(${g.total})` : ''}
              </Text>
              <Text style={st.gapCell}>{g.recent}</Text>
            </View>
          ))}
          <Text style={st.sub}>“0(4)” = พร้อมขาย 0 แต่มีรุ่นนี้อีก 4 คันที่ยังไม่พร้อมขาย</Text>
        </Section>
      ) : null}
      <OutLines rows={d.myOut} />
    </>
  );
}

const st = StyleSheet.create({
  hello: { fontSize: 22, fontWeight: '800', color: C.text },
  sub: { fontSize: 13, color: C.sub, lineHeight: 19 },
  h2: { fontSize: 17, fontWeight: '800', color: C.text, flex: 1 },
  secHead: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  pill: { alignSelf: 'flex-start', borderRadius: 8, paddingHorizontal: 10, paddingVertical: 6 },
  kpis: { flexDirection: 'row', gap: 8 },
  kpi: {
    flex: 1,
    minHeight: 76,
    backgroundColor: C.bg,
    borderRadius: 10,
    paddingVertical: 10,
    paddingHorizontal: 6,
    alignItems: 'center',
    justifyContent: 'center',
  },
  kpiVal: { fontSize: 22, fontWeight: '800', color: C.text },
  kpiLabel: { fontSize: 12, color: C.sub, textAlign: 'center', marginTop: 2 },
  kpiSub: { fontSize: 11, color: C.amber, marginTop: 1 },
  scoreRow: { flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: C.purpleSoft, borderRadius: 10, padding: 12 },
  scoreBig: { fontSize: 28, fontWeight: '800', color: C.purple },
  listRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    paddingVertical: 10,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: C.line,
  },
  rowMain: { fontSize: 15, fontWeight: '700', color: C.text },
  carTitle: { fontSize: 14, fontWeight: '400', color: C.sub },
  sbtn: { minHeight: 34, minWidth: 56, borderWidth: 1.5, borderRadius: 7, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 10 },
  sbtnText: { fontSize: 14, fontWeight: '700' },
  empty: { color: C.sub, textAlign: 'center', paddingVertical: 10 },
  more: { color: C.purple, fontWeight: '700', textAlign: 'center', paddingVertical: 6 },
  carRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    paddingVertical: 10,
    paddingHorizontal: 10,
    borderLeftWidth: 5,
    borderRadius: 8,
    backgroundColor: C.bg,
  },
  carLabel: { fontSize: 16, fontWeight: '800', color: C.text },
  chev: { fontSize: 24, color: C.sub, paddingHorizontal: 2 },
  tags: { flexDirection: 'row', flexWrap: 'wrap', gap: 4, marginTop: 2 },
  foot: { textAlign: 'center', color: C.sub, fontSize: 12 },
  gapHead: { flexDirection: 'row', paddingBottom: 4, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: C.line },
  gapRow: { flexDirection: 'row', paddingVertical: 6 },
  gapCell: { flex: 1, fontSize: 13, color: C.sub, textAlign: 'center' },
});
