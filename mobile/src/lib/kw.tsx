// ★ 12 ต.ค.69 คำที่ระบบจับได้ในแชท (เจ้าของเลือกจากเดโม CRM "เอาแบบนี้แหละ แก้ไขเลย") — ชุดเดียวกับหน้าเว็บ Connect
//   เซิร์ฟเวอร์ส่ง m.hl = [[เริ่ม, จบ, ช่อง]] (ตำแหน่งแบบ UTF-16 = แบบเดียวกับ JS) · lead.sugg = ค่าใหม่รอคนตัดสิน
//   แอปแค่โชว์ + กดยืนยัน/ปิด ผ่าน /connect/api/lead ตัวเดียวกับเว็บ (ไม่มี API ใหม่)
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { C, fmtTime } from './ui';

export type Hl = [number, number, string];
export type KwMsg = { id?: string; at: string; text: string; type: string; dir: string; hl?: Hl[]; files?: { kind: string }[] };
export type Sugg = { v?: string; opts?: string[]; why?: string; from?: string };
export type Lead = Record<string, any> & { auto?: Record<string, string>; sugg?: Record<string, Sugg>; deal?: string };

// สีตามหมวด: ติดต่อ · รถ · การเงินลูกค้า · เจตนา/สถานะ (ตัวอักษรเข้มบนพื้นอ่อน อ่านออกทั้ง 2 แบบ)
export const KW_CAT: Record<string, 'c' | 'r' | 'm' | 'i'> = {
  phone: 'c', line_id: 'c', car_text: 'r', car_model: 'r', occupation: 'm', income: 'm', job_tenure: 'm',
  pay_history: 'm', customer_type: 'm', customer_status: 'i', deal: 'i', trade: 'i',
};
export const KW_COLOR: Record<string, { bg: string; line: string; name: string }> = {
  c: { bg: '#dbeafe', line: '#2563eb', name: 'ติดต่อ' },
  r: { bg: '#ede9fe', line: '#7c3aed', name: 'รถ' },
  m: { bg: '#d1fae5', line: '#059669', name: 'การเงินลูกค้า' },
  i: { bg: '#ffedd5', line: '#c2410c', name: 'เจตนา / สถานะ' },
};
export const KW_NAME: Record<string, string> = {
  phone: 'เบอร์โทร', line_id: 'ID LINE', car_text: 'รถลูกค้าถาม', car_model: 'CAR / สูตร', occupation: 'อาชีพ',
  income: 'รายได้', job_tenure: 'อายุงาน', pay_history: 'ประวัติการผ่อน', customer_type: 'ประเภทลูกค้า',
  customer_status: 'สถานะลูกค้า', deal: 'ลีดรับซื้อรถ', trade: 'มีรถเทิร์น',
};
// {q} = คำลงท้ายคำถาม (ครับ/คะ) · {p} = คำลงท้ายบอกเล่า (ครับ/ค่ะ) — กดแล้วแค่ใส่ช่องพิมพ์ ไม่ส่งเอง
const KW_ASK: Record<string, string> = {
  contact: 'รบกวนขอเบอร์โทร หรือ ID LINE ไว้ให้เจ้าหน้าที่ติดต่อกลับหน่อยนะ{q}',
  car: 'สนใจรุ่นไหน ปีประมาณไหนเป็นพิเศษไหม{q}',
  money: 'ลูกค้าทำงานอะไร รายได้ต่อเดือนประมาณเท่าไหร่{q} จะได้เช็คไฟแนนซ์ให้{p}',
  tenure: 'ทำงานที่ปัจจุบันมากี่ปีแล้ว{q}',
  pay: 'ตอนนี้มีผ่อนอะไรอยู่ไหม{q} ผ่อนตรงทุกงวดไหม{q}',
  view: 'สะดวกเข้ามาดูรถที่เต็นท์วันไหน{q}',
  bcar: 'รถรุ่นอะไร ปีไหน เลขไมล์ประมาณเท่าไหร่{q}',
  photos: 'รบกวนส่งภาพรถ ด้านนอก ด้านใน หน้าปัดให้เห็นเลขไมล์ และสำเนาเล่มทะเบียน หน้า 4 และ 18 เพื่อให้เจ้าหน้าที่ฝ่ายจัดซื้อประเมินราคานะ{q}',
  payoff: 'รถยังติดไฟแนนซ์อยู่ไหม{q} ยอดปิดประมาณเท่าไหร่{q}',
  handoff: 'ขอบคุณ{p} แอดมินจะประสานงานให้เจ้าหน้าที่ฝ่ายจัดซื้อติดต่อกลับนะ{q}',
};
export type Pt = 'm' | 'f';
export const askText = (k: string, pt: Pt) =>
  (KW_ASK[k] || '').replace(/\{q\}/g, pt === 'f' ? 'คะ' : 'ครับ').replace(/\{p\}/g, pt === 'f' ? 'ค่ะ' : 'ครับ');

const kwKey = (f: string) => (f === 'car_model' ? 'car_text' : f === 'customer_type' ? 'occupation' : f);
const norm = (s?: string) => String(s || '').replace(/…/g, '').replace(/\s+/g, '').toLowerCase();
const digits = (s?: string) => {
  const d = String(s || '').replace(/\D/g, '');
  return d.startsWith('66') ? '0' + d.slice(2) : d;
};

/** ข้อความต้นทางของช่อง — ตรงกับคำที่จับได้/ค่าในช่องก่อน · ไม่ตรง = ข้อความแรก (สถานะลูกค้า = ล่าสุด) · -1 = ไม่เจอ */
export function findMsg(msgs: KwMsg[], f: string, why?: string, val?: string, last?: boolean): number {
  const k = kwKey(f), w = norm(why), dv = digits(val);
  const cand: [number, string][] = [];
  msgs.forEach((m, i) => (m.hl || []).forEach((x) => { if (x[2] === k) cand.push([i, (m.text || '').slice(x[0], x[1])]); }));
  if (!cand.length) return -1;
  const ok = cand.filter(([, t]) => (k === 'phone' && dv && digits(t) === dv)
    || (w && (w.includes(norm(t)) || norm(t).includes(w)))
    || (k === 'line_id' && val && norm(t).includes(norm(val))));
  const pool = ok.length ? ok : (k === 'phone' && dv ? [] : cand);
  if (!pool.length) return -1;
  return (last ? pool[pool.length - 1] : pool[0])[0];
}

/** ความพร้อมของข้อมูล — ลีดขาย: ก่อนจ่ายเบอร์ · ลีดรับซื้อ: ก่อนส่งจัดซื้อ → [ชื่อ, มีแล้วไหม, คีย์ประโยคถามต่อ] */
export function ready(L: Lead, msgs: KwMsg[]) {
  const has = (f: string) => !!(L[f] && String(L[f]).trim());
  if (L.deal === 'buy') {
    const imgs = msgs.filter((m) => m.dir !== 'out' && (m.type === 'image' || (m.files || []).some((x) => x.kind === 'image'))).length;
    return { title: 'พร้อมส่งจัดซื้อ', items: [
      ['เบอร์ หรือ ID LINE', has('phone') || has('line_id'), 'contact'],
      ['รุ่น + ปีรถของลูกค้า', has('car_text'), 'bcar'],
      ['รูปรถ + เล่ม (2 รูปขึ้นไป)', imgs >= 2, 'photos'],
    ] as [string, boolean, string][] };
  }
  return { title: L.code ? 'ข้อมูลลูกค้าสำหรับไฟแนนซ์' : 'ข้อมูลพร้อมจ่ายเบอร์', items: [
    ['เบอร์ หรือ ID LINE', has('phone') || has('line_id'), 'contact'],
    ['รถที่สนใจ', has('car_text') || (has('car_model') && L.car_model !== 'ไม่ระบุรุ่นรถ'), 'car'],
    ['อาชีพ + รายได้', has('occupation') && has('income'), 'money'],
    ['อายุงาน', has('job_tenure'), 'tenure'],
    ['ประวัติการผ่อน', has('pay_history'), 'pay'],
  ] as [string, boolean, string][] };
}

/** ข้อความในบับเบิลพร้อมคำที่ระบบจับได้ระบายสีตามหมวด · แตะคำ = onPick(ช่อง) */
export function HlText({ m, out, on, style, onPick }: {
  m: KwMsg; out: boolean; on: boolean; style: any; onPick: (f: string) => void;
}) {
  const t = m.text || '';
  const hl = on ? m.hl || [] : [];
  if (!hl.length) return <Text style={style}>{t}</Text>;
  const parts: any[] = [];
  let p = 0;
  hl.forEach(([s, e, f], i) => {
    if (s < p || e > t.length) return;
    if (s > p) parts.push(t.slice(p, s));
    const col = KW_COLOR[KW_CAT[f] || 'i'];
    parts.push(
      <Text key={i} onPress={() => onPick(f)} suppressHighlighting={false}
        style={out ? st.hlOut : { backgroundColor: col.bg, textDecorationLine: 'underline', textDecorationColor: col.line }}>
        {t.slice(s, e)}
      </Text>,
    );
    p = e;
  });
  if (p < t.length) parts.push(t.slice(p));
  return <Text style={style}>{parts}</Text>;
}

const fmtVal = (f: string, v?: string) =>
  f === 'income' && /^\d+$/.test(String(v || '')) ? Number(v).toLocaleString() : v || '–';

/** แผง "ระบบจับได้" — ความพร้อม · ค่าใหม่รอคนตัดสิน · ช่องที่ระบบเติม (ย้อนไปข้อความได้) */
export function KwPanel({ lead, msgs, editable, canAsk, pt, focus, busy, onAsk, onUse, onDismiss, onGoMsg }: {
  lead: Lead; msgs: KwMsg[]; editable: boolean; canAsk: boolean; pt: Pt; focus: string; busy: boolean;
  onAsk: (k: string) => void; onUse: (f: string, v: string) => void; onDismiss: (f: string) => void;
  onGoMsg: (i: number) => void;
}) {
  const R = ready(lead, msgs);
  const done = R.items.filter((x) => x[1]).length;
  const miss = R.items.find((x) => !x[1]);
  const sugg = editable ? Object.entries(lead.sugg || {}) : [];
  const A = lead.auto || {};
  const filled = Object.keys(KW_NAME).filter((f) => lead[f] && A[f] && A[f] !== 'คน');
  return (
    <View style={{ gap: 10 }}>
      <View>
        <View style={st.row}>
          <Text style={st.h}>{R.title}</Text>
          <Text style={[st.h, { color: C.purple, marginLeft: 'auto' }]}>{done}/{R.items.length}</Text>
        </View>
        <View style={st.bar}><View style={[st.barIn, { width: `${Math.round((done / R.items.length) * 100)}%` }]} /></View>
        <View style={st.grid}>
          {R.items.map(([n, ok]) => (
            <Text key={n} style={[st.item, { color: ok ? C.green : C.sub }]}>{ok ? '✓' : '○'} {n}</Text>
          ))}
        </View>
        {miss ? (
          <View style={st.ask}>
            <Text style={{ color: C.amber, fontWeight: '700' }}>ถามต่อ: {miss[0]}</Text>
            <Text style={{ color: C.text, marginTop: 2 }}>“{askText(miss[2], pt)}”</Text>
            {canAsk ? (
              <Pressable onPress={() => onAsk(miss[2])} style={st.smBtn}><Text style={st.smBtnT}>ใส่ในช่องพิมพ์</Text></Pressable>
            ) : null}
          </View>
        ) : null}
      </View>
      {sugg.length ? (
        <View style={st.sugBox}>
          <Text style={[st.h, { color: C.amber }]}>ลูกค้าพูดค่าใหม่ — รอคนตัดสิน (ระบบไม่ทับค่าเดิมเอง)</Text>
          {sugg.map(([f, s]) => (
            <View key={f} style={[st.sug, focus === f && st.focus]}>
              <Text style={{ color: C.text }}>
                <Text style={{ fontWeight: '700' }}>{KW_NAME[f] || f} </Text>
                {s.opts ? `ลูกค้าบอกแค่ “${s.why || ''}” — รุ่นไหน?` : `${fmtVal(f, s.from)} → ${fmtVal(f, s.v)}`}
              </Text>
              <View style={st.acts}>
                {s.opts ? (
                  <>
                    {s.opts.map((o) => (
                      <Pressable key={o} disabled={busy} onPress={() => onUse(f, o)} style={st.smBtn}><Text style={st.smBtnT}>{o}</Text></Pressable>
                    ))}
                    <Pressable disabled={busy} onPress={() => onDismiss(f)} style={st.smBtn}><Text style={st.smBtnT}>ยังไม่รู้</Text></Pressable>
                  </>
                ) : (
                  <>
                    <Pressable disabled={busy} onPress={() => onUse(f, s.v || '')} style={[st.smBtn, st.pri]}>
                      <Text style={[st.smBtnT, { color: '#fff' }]}>ใช้ {fmtVal(f, s.v)}</Text>
                    </Pressable>
                    <Pressable disabled={busy} onPress={() => onUse(f, s.from || '')} style={st.smBtn}>
                      <Text style={st.smBtnT}>คง {fmtVal(f, s.from)}</Text>
                    </Pressable>
                  </>
                )}
              </View>
            </View>
          ))}
        </View>
      ) : null}
      {filled.length ? (
        <View>
          <Text style={st.h}>ช่องที่ระบบเติมให้</Text>
          {filled.map((f) => {
            const i = A[f] === 'แชท' ? findMsg(msgs, f, (lead.autoWhy || {})[f], lead[f], f === 'customer_status') : -1;
            const col = KW_COLOR[KW_CAT[f] || 'i'];
            return (
              <View key={f} style={[st.fld, focus === f && st.focus]}>
                <View style={[st.dot, { backgroundColor: col.line }]} />
                <Text style={st.fldL}>{KW_NAME[f]}</Text>
                <Text style={st.fldV} numberOfLines={2}>{fmtVal(f, lead[f])}</Text>
                {i >= 0 ? (
                  <Pressable onPress={() => onGoMsg(i)} hitSlop={6}>
                    <Text style={[st.src, { borderColor: col.line }]}>แชท {fmtTime(msgs[i].at)}</Text>
                  </Pressable>
                ) : (
                  <Text style={st.srcPlain}>จาก{A[f]}</Text>
                )}
              </View>
            );
          })}
        </View>
      ) : null}
    </View>
  );
}

/** แถบตอบด่วนเหนือช่องพิมพ์ — ประโยคถามต่อ (ข้อมูลที่ยังขาด) ขึ้นก่อน · เลือกคำลงท้ายได้ */
export function QuickBar({ lead, msgs, pt, setPt, onAsk }: {
  lead: Lead; msgs: KwMsg[]; pt: Pt; setPt: (p: Pt) => void; onAsk: (k: string) => void;
}) {
  const miss = ready(lead, msgs).items.find((x) => !x[1]);
  const base: [string, string][] = lead.deal === 'buy'
    ? [['ขอรูปรถ + เล่ม', 'photos'], ['ถามรุ่น/ปี/ไมล์', 'bcar'], ['ถามยอดปิด', 'payoff'], ['แจ้งส่งจัดซื้อ', 'handoff']]
    : [['ขอเบอร์/ไลน์', 'contact'], ['ถามอาชีพ/รายได้', 'money'], ['ถามประวัติผ่อน', 'pay'], ['ชวนนัดดูรถ', 'view']];
  const list: [string, string, boolean][] = (miss ? [['ถามต่อ: ' + miss[0], miss[2], true] as [string, string, boolean]] : [])
    .concat(base.filter((b) => !miss || b[1] !== miss[2]).map((b) => [b[0], b[1], false] as [string, string, boolean]));
  return (
    <View style={st.qr}>
      {list.map(([l, k, nx]) => (
        <Pressable key={k} onPress={() => onAsk(k)} style={[st.q, nx && st.qNext]}>
          <Text style={[st.qT, nx && { color: C.amber, fontWeight: '700' }]}>{l}</Text>
        </Pressable>
      ))}
      <View style={st.pt}>
        {(['m', 'f'] as Pt[]).map((p) => (
          <Pressable key={p} onPress={() => setPt(p)} style={[st.ptB, pt === p && { backgroundColor: C.purple }]}>
            <Text style={{ fontSize: 13, color: pt === p ? '#fff' : C.sub }}>{p === 'm' ? 'ครับ' : 'ค่ะ'}</Text>
          </Pressable>
        ))}
      </View>
    </View>
  );
}

const st = StyleSheet.create({
  hlOut: { backgroundColor: 'rgba(255,255,255,0.25)', textDecorationLine: 'underline', textDecorationColor: '#fff' },
  row: { flexDirection: 'row', alignItems: 'baseline' },
  h: { fontSize: 13, fontWeight: '700', color: C.sub },
  bar: { height: 6, borderRadius: 3, backgroundColor: C.purpleSoft, overflow: 'hidden', marginVertical: 6 },
  barIn: { height: 6, backgroundColor: C.purple },
  grid: { flexDirection: 'row', flexWrap: 'wrap' },
  item: { width: '50%', fontSize: 13, paddingVertical: 1 },
  ask: { marginTop: 8, padding: 10, borderRadius: 8, backgroundColor: C.amberBg },
  smBtn: { alignSelf: 'flex-start', marginTop: 6, paddingHorizontal: 10, paddingVertical: 7, borderRadius: 7,
           borderWidth: 1, borderColor: C.line, backgroundColor: '#fff' },
  smBtnT: { fontSize: 14, color: C.text, fontWeight: '600' },
  pri: { backgroundColor: C.purple, borderColor: C.purple },
  sugBox: { padding: 10, borderRadius: 8, borderWidth: 1, borderColor: '#fdba74', gap: 6 },
  sug: { paddingVertical: 4, borderRadius: 6 },
  acts: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  focus: { backgroundColor: C.purpleSoft },
  fld: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 6, paddingHorizontal: 4, borderRadius: 6 },
  dot: { width: 8, height: 8, borderRadius: 4 },
  fldL: { width: 92, fontSize: 13, color: C.sub },
  fldV: { flex: 1, fontSize: 14, color: C.text },
  src: { fontSize: 12, color: C.text, borderWidth: 1, borderRadius: 6, paddingHorizontal: 6, paddingVertical: 2 },
  srcPlain: { fontSize: 12, color: C.purple },
  qr: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, alignItems: 'center', marginBottom: 8 },
  q: { paddingHorizontal: 10, paddingVertical: 6, borderRadius: 7, borderWidth: 1, borderColor: C.line, backgroundColor: C.bg },
  qNext: { borderColor: '#fdba74', backgroundColor: C.amberBg },
  qT: { fontSize: 13, color: C.text },
  pt: { flexDirection: 'row', marginLeft: 'auto', borderWidth: 1, borderColor: C.line, borderRadius: 7, overflow: 'hidden' },
  ptB: { paddingHorizontal: 9, paddingVertical: 5 },
});
