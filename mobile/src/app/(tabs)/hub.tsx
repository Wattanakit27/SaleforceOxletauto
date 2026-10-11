// ห้องพัก Lead (แอดมิน) — ลีดที่รอจ่ายเบอร์จากทุกช่องทาง (GET /connect/api/inbox?view=tocode · ตัวเดียวกับเว็บ)
// กดชื่อเซลล์ = จ่ายเบอร์เลย (ปุ่มแรก = คิวถัดไปของคิวจ่ายวน) — ยิง endpoint เดิมของเว็บ:
//   แชท LINE/FB → POST /connect/api/assign_lead {id, emp} · ใบร่างจากกลุ่ม → POST /connect/api/park_assign {mid, emp, …}
// ★ 11 ต.ค.69 กลุ่ม "ลูกค้าให้เบอร์/ID LINE แล้ว — รอแอดมินกดรับ" บนสุด (d.pending) · กด "รับ lead" = assign_lead {id, park:true}
//   แล้วลีดลงไปรายการรอจ่ายเบอร์ข้างล่าง (กดชื่อเซลล์จ่ายต่อ) — กติกาเดียวกับเว็บ
// ★ 11 ต.ค.69 แท็บ "รับซื้อรถ" (d.buyRoom) — ลูกค้าอยากขายรถให้เรา แยกจากลีดขาย · ไม่จ่ายเบอร์ให้เซลล์
//   ส่งใบเคสรับซื้อ (Share → LINE กลุ่มเคสHOT) · "เป็นลีดขายรถ" = assign_lead {id, kind:'sell'} · กลุ่มรอกดรับมี "ลีดรับซื้อ" ({kind:'buy'})
// ★ ใบจ่ายลีดถูกส่งเข้ากลุ่มจ่ายเบอร์จริง + แท็กเซลล์ (ถ้าเปิดสวิตช์ไว้) → ถามยืนยันทุกครั้ง เหมือนเว็บ
//   เบอร์ซ้ำ (เคยเป็นลีดของคนอื่น) → ถามซ้ำอีกชั้นก่อนจ่ายให้คนใหม่
import { router, useFocusEffect } from 'expo-router';
import { useCallback, useMemo, useState } from 'react';
import { Alert, Pressable, RefreshControl, ScrollView, Share, StyleSheet, Text, View } from 'react-native';

import { api } from '../../lib/api';
import { Banner, C, Card, fmtTime, Loading, Tag } from '../../lib/ui';

type Dup = { seller?: string; sellerId?: number; code?: string; date?: string } | null;
type ChatRow = {
  id: number;
  name: string;
  src: string;
  preview: string;
  lastAt: string;
  since?: string;
  hasPhone?: boolean;
  hasLine?: boolean;
  car?: string;
  dup?: Dup;
  phone?: string;
  lineId?: string;
  contact?: string;
  lastDir?: string;
  trade?: boolean;
  slip?: string;
  dealWhy?: string;
  dealBy?: string;
};
type Park = {
  id: string;
  account?: string;
  name?: string;
  lineId?: string;
  phone?: string;
  source?: string;
  channel?: string;
  by?: string;
  at: string;
  car?: string;
  prefix?: string;
  base?: string;
  admin?: boolean;
  reject?: boolean;
  reposts?: number;
  dup?: Dup;
  code?: string;
  doneAt?: string;
  seller?: string;
  sellerNick?: string;
  assignedBy?: string;
  sys?: { code?: string; seller?: string; by?: string; post?: { ok?: boolean } } | null;
};
type Board = { id: number; name: string; team: string; today: number; cap: number; ok: boolean; why: string };
type Inbox = {
  rows: ChatRow[];
  pending?: ChatRow[];
  pendingDays?: number;
  buyRoom?: ChatRow[];
  buyRoomDays?: number;
  buyLast?: Record<string, string>;
  parked?: { waiting?: Park[]; assigned?: Park[]; room?: string; codeHelp?: { next?: number; post?: { on?: boolean; room?: string; rejectRoom?: string } } };
  rrBoard?: Board[];
  sellers?: { id: number; name: string; team: string }[];
  assigned?: { id: number; name: string; src: string; code: string; seller: string; by: string; at: string; how: string; kind?: string }[];
  duty?: { today: string };
};
type Item = {
  kind: 'chat' | 'park';
  id: string;
  name: string;
  src: string;
  car: string;
  line: string;
  since: string;
  hasPhone: boolean;
  hasLine: boolean;
  dup: Dup;
  prefix: string;
  reposts: number;
  p?: Park;
};

const SRC: Record<string, [string, string, string]> = {
  line: ['LINE', C.lineGreen, '#e6f9ee'],
  fb: ['Facebook', C.fb, '#e7f0fe'],
  facebook: ['Facebook', C.fb, '#e7f0fe'],
  tiktok: ['TikTok', '#111', '#eeeeee'],
  other: ['อื่นๆ', C.sub, '#eeeeee'],
};
const pWho = (i: Park) => i.account || i.name || i.lineId || i.phone || '(ไม่มีชื่อ)';

function waited(since: string): [string, boolean] {
  const t = Date.parse(since);
  if (isNaN(t)) return ['', false];
  const m = Math.max(0, Math.floor((Date.now() - t) / 60000));
  if (m < 60) return [`${m} นาที`, m >= 30];
  const h = Math.floor(m / 60);
  return [h < 24 ? `${h} ชม. ${m % 60} นาที` : `${Math.floor(h / 24)} วัน`, true];
}

export default function Hub() {
  const [d, setD] = useState<Inbox | null>(null);
  const [err, setErr] = useState('');
  const [tab, setTab] = useState<'wait' | 'buy' | 'done'>('wait');
  const [busy, setBusy] = useState('');
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      setD(await api<Inbox>('/connect/api/inbox?view=tocode', { timeoutMs: 45000 }));
      setErr('');
    } catch (e: any) {
      setErr(e?.message || 'โหลดไม่สำเร็จ');
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      load();
      const t = setInterval(load, 15000);
      return () => clearInterval(t);
    }, [load]),
  );

  const items: Item[] = useMemo(() => {
    if (!d) return [];
    const out: Item[] = (d.rows || []).map((r) => ({
      kind: 'chat',
      id: String(r.id),
      name: r.name || '(ไม่มีชื่อ)',
      src: r.src === 'fb' ? 'fb' : 'line',
      car: r.car || '',
      line: 'แชท ' + (r.src === 'fb' ? 'Facebook' : 'LINE@') + (r.preview ? ' · ' + r.preview : ''),
      since: r.since || r.lastAt,
      hasPhone: !!r.hasPhone,
      hasLine: !!r.hasLine,
      dup: r.dup || null,
      prefix: '',
      reposts: 0,
    }));
    const P = d.parked || {};
    (P.waiting || []).forEach((i) =>
      out.push({
        kind: 'park',
        id: i.id,
        name: pWho(i),
        src: i.source || 'other',
        car: i.car || '',
        line: 'ใบร่างจากกลุ่ม ' + (P.room || 'ADMIN เก็บ Lead') + (i.channel ? ' · ' + i.channel : '') + (i.by ? ' · พักโดย ' + i.by : ''),
        since: i.at,
        hasPhone: !!i.phone,
        hasLine: !!i.lineId,
        dup: i.dup || null,
        prefix: i.prefix || '',
        reposts: i.reposts || 0,
        p: i,
      }),
    );
    return out.sort((a, b) => Date.parse(a.since) - Date.parse(b.since));
  }, [d]);

  const done = useMemo(() => {
    if (!d) return [];
    const today = new Date().toDateString();
    const out = (d.assigned || []).map((r) => ({
      key: 'c' + r.id + r.code, name: r.name, src: r.src, code: r.code, seller: r.seller, by: r.by, at: r.at,
      how: r.kind === 'buy' ? 'ส่งจัดซื้อ' : r.how, chatId: r.id as number | null,
    }));
    (d.parked?.assigned || []).forEach((i) => {
      const real = i.code;
      const sys = i.sys || null;
      out.push({
        key: 'p' + i.id,
        name: pWho(i),
        src: i.source || 'other',
        code: real || sys?.code || '',
        seller: real ? i.sellerNick || i.seller || '' : sys?.seller || '',
        by: real ? i.assignedBy || '' : sys?.by || '',
        at: i.doneAt || '',
        how: sys?.post?.ok ? 'ระบบ → ส่งเข้ากลุ่มแล้ว' : real ? 'ใบในห้องจ่ายเบอร์' : 'ระบบ',
        chatId: null,
      });
    });
    return out
      .filter((x) => x.at && x.code && new Date(x.at).toDateString() === today)
      .sort((a, b) => Date.parse(b.at) - Date.parse(a.at));
  }, [d]);

  const board = (d?.rrBoard || []).filter((x) => x.ok).slice(0, 9);
  const post = d?.parked?.codeHelp?.post || {};
  const sellerName = (id: number) => (d?.sellers || []).find((s) => s.id === id)?.name || (d?.rrBoard || []).find((s) => s.id === id)?.name || '';

  const doAssign = async (it: Item, emp: number) => {
    const key = it.kind + ':' + it.id;
    setBusy(key);
    try {
      const r = await api<{ message?: string; post?: { ok?: boolean; error?: string } }>(
        it.kind === 'chat' ? '/connect/api/assign_lead' : '/connect/api/park_assign',
        {
          body:
            it.kind === 'chat'
              ? { id: Number(it.id), emp }
              : { mid: it.id, emp, base: it.p?.base, admin: !!it.p?.admin, reject: !!it.p?.reject },
        },
      );
      const failPost = r.post && r.post.ok === false;
      Alert.alert(failPost ? 'จ่ายเบอร์แล้ว แต่ส่งเข้ากลุ่มไม่สำเร็จ' : 'จ่ายเบอร์แล้ว',
        (r.message || '') + (failPost ? '\n' + (r.post?.error || '') + '\nกดส่งอีกครั้งได้ที่หน้าเว็บ (จ่ายแล้ว)' : ''));
    } catch (e: any) {
      Alert.alert('จ่ายเบอร์ไม่สำเร็จ', e?.message || '');
    } finally {
      setBusy('');
      load();
    }
  };

  const assign = (it: Item, emp: number) => {
    const nm = sellerName(emp);
    const room = (it.p?.reject && post.rejectRoom) || post.room || 'กลุ่มจ่ายเบอร์';
    const go = () => {
      if (!post.on) return doAssign(it, emp);
      Alert.alert(`จ่ายเบอร์ให้ ${nm}?`, `"${it.name}"\nระบบจะส่งใบเข้า "${room}" พร้อมแท็ก @${nm}`, [
        { text: 'ยกเลิก', style: 'cancel' },
        { text: 'จ่ายเบอร์', onPress: () => doAssign(it, emp) },
      ]);
    };
    if (it.dup?.sellerId && it.dup.sellerId !== emp) {
      Alert.alert('เบอร์ซ้ำ', `เบอร์นี้เคยเป็นลีด ${it.dup.code || ''} ของ @${it.dup.seller}\nยังจะจ่ายให้ ${nm} อีกคนใช่ไหม?`, [
        { text: 'ยกเลิก', style: 'cancel' },
        { text: 'จ่ายให้คนใหม่', style: 'destructive', onPress: go },
      ]);
      return;
    }
    go();
  };

  const skip = (it: Item) =>
    Alert.alert('ไม่ต้องจ่ายเบอร์?', `"${it.name}" — เช่น ลีดซ้ำ / ไม่ใช่ลีดขาย (เอากลับมาได้ที่หน้าเว็บ)`, [
      { text: 'ยกเลิก', style: 'cancel' },
      {
        text: 'ไม่ต้องจ่าย',
        onPress: async () => {
          try {
            await api(it.kind === 'chat' ? '/connect/api/assign_lead' : '/connect/api/park_assign', {
              body: it.kind === 'chat' ? { id: Number(it.id), skip: true } : { mid: it.id, skip: true },
            });
          } catch (e: any) {
            Alert.alert('ทำไม่สำเร็จ', e?.message || '');
          }
          load();
        },
      },
    ]);

  const accept = async (r: ChatRow) => {
    const key = 'pend:' + r.id;
    setBusy(key);
    try {
      await api('/connect/api/assign_lead', { body: { id: r.id, park: true } });
    } catch (e: any) {
      Alert.alert('รับ lead ไม่สำเร็จ', e?.message || '');
    } finally {
      setBusy('');
      load();
    }
  };
  const pend = d?.pending || [];
  const [pendAll, setPendAll] = useState(false);
  const buys = d?.buyRoom || [];

  // ลีดรับซื้อรถ / ลีดขายรถ — แอดมินตั้งเอง (ระบบไม่เดาทับ)
  const setDeal = async (r: ChatRow, kind: 'buy' | 'sell') => {
    setBusy('deal:' + r.id);
    try {
      const x = await api<{ message?: string }>('/connect/api/assign_lead', { body: { id: r.id, kind } });
      if (x.message) Alert.alert(kind === 'buy' ? 'ย้ายเป็นลีดรับซื้อแล้ว' : 'ย้ายเป็นลีดขายแล้ว', x.message);
    } catch (e: any) {
      Alert.alert('ทำไม่สำเร็จ', e?.message || '');
    } finally {
      setBusy('');
      load();
    }
  };
  const shareSlip = async (r: ChatRow) => {
    try {
      await Share.share({ message: r.slip || '' });
    } catch {}
  };

  const onRefresh = async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  };

  if (!d && !err) return <Loading text="กำลังโหลดห้องพัก Lead…" />;

  return (
    <ScrollView
      contentContainerStyle={{ padding: 12, gap: 12, paddingBottom: 40 }}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={C.purple} />}>
      {err ? <Banner kind="err" text={err} /> : null}
      <View style={st.seg}>
        {(
          [
            ['wait', `รอจ่ายเบอร์ ${items.length}${pend.length ? ' +' + pend.length : ''}`],
            ['buy', `รับซื้อรถ ${buys.length}`],
            ['done', `จ่ายแล้ววันนี้ ${done.length}`],
          ] as const
        ).map(([k, l]) => (
          <Pressable key={k} onPress={() => setTab(k)} style={[st.segBtn, tab === k && st.segOn]}>
            <Text style={[st.segText, tab === k && { color: '#fff' }]}>{l}</Text>
          </Pressable>
        ))}
      </View>

      {tab === 'wait' ? (
        <>
          <Text style={st.note}>
            {post.on
              ? `กดชื่อเซลล์ = ออกเลข + ส่งใบเข้า "${post.room || 'กลุ่มจ่ายเบอร์'}" พร้อมแท็ก @เซลล์ · ปุ่มกรอบชมพู = คิวถัดไป`
              : 'โหมดทดลอง — เก็บในระบบอย่างเดียว ไม่ส่งเข้ากลุ่ม · ปุ่มกรอบชมพู = คิวถัดไป'}
            {d?.parked?.codeHelp?.next ? ` · เลขรันถัดไป ${d.parked.codeHelp.next}` : ''}
          </Text>
          {(d?.rrBoard || []).length ? (
            <Text style={st.note}>
              มือเซลล์วันนี้:{' '}
              {(d?.rrBoard || [])
                .map((x) => `${x.name} ${x.today}${x.cap ? '/' + x.cap : ''}${x.ok ? '' : ` (${x.why || 'หลุดคิว'})`}`)
                .join(' · ')}
            </Text>
          ) : null}
          {pend.length ? (
            <Card style={{ gap: 0, padding: 0, overflow: 'hidden', borderColor: C.amber }}>
              <View style={{ backgroundColor: C.amberBg, padding: 12, gap: 2 }}>
                <Text style={{ color: C.amber, fontWeight: '800', fontSize: 15 }}>
                  ลูกค้าให้เบอร์/ID LINE แล้ว — รอแอดมินกดรับ {pend.length} ราย
                </Text>
                <Text style={st.sub}>
                  {`กด "รับ lead" แล้วลีดจะลงไปรายการรอจ่ายเบอร์ข้างล่าง · เฉพาะที่ทักภายใน ${d?.pendingDays || 3} วัน`}
                </Text>
              </View>
              {(pendAll ? pend : pend.slice(0, 8)).map((r) => {
                const [sl, sfg, sbg] = SRC[r.src === 'fb' ? 'fb' : 'line'];
                return (
                  <View key={r.id} style={st.pend}>
                    <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: 8 }}>
                      <Text style={st.name} numberOfLines={1}>{r.name || '(ไม่มีชื่อ)'}</Text>
                      <Text style={st.sub}>{fmtTime(r.lastAt)}</Text>
                    </View>
                    <View style={st.tags}>
                      <Tag text={sl} color={sfg} bg={sbg} />
                      {r.phone ? <Tag text={'เบอร์ ' + r.phone} color={C.green} bg={C.greenBg} /> : null}
                      {r.lineId ? <Tag text={'ID LINE ' + r.lineId} color={C.green} bg={C.greenBg} />
                        : r.contact === 'qr' ? <Tag text="QR LINE" color={C.green} bg={C.greenBg} /> : null}
                      {r.dup ? <Tag text={'เบอร์ซ้ำ @' + (r.dup.seller || '?')} color={C.red} bg={C.redBg} /> : null}
                      {r.trade ? <Tag text="มีรถเทิร์น" color={C.sub} bg="#eee" /> : null}
                    </View>
                    {r.preview ? <Text style={st.sub} numberOfLines={1}>{r.lastDir === 'out' ? 'เรา: ' : ''}{r.preview}</Text> : null}
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 16 }}>
                      <Pressable
                        disabled={busy === 'pend:' + r.id}
                        onPress={() => accept(r)}
                        style={({ pressed }) => [st.acc, (pressed || busy === 'pend:' + r.id) && { opacity: 0.5 }]}>
                        <Text style={{ color: '#fff', fontWeight: '800', fontSize: 15 }}>รับ lead</Text>
                      </Pressable>
                      <Pressable disabled={!!busy} onPress={() => setDeal(r, 'buy')} hitSlop={6}>
                        <Text style={st.link}>ลีดรับซื้อ</Text>
                      </Pressable>
                      <Pressable
                        onPress={() => skip({ kind: 'chat', id: String(r.id), name: r.name } as Item)}
                        hitSlop={6}>
                        <Text style={st.link}>ไม่ใช่ลีด</Text>
                      </Pressable>
                      <Pressable onPress={() => router.push({ pathname: '/chat/[id]', params: { id: String(r.id) } })} hitSlop={6}>
                        <Text style={st.link}>เปิดแชท</Text>
                      </Pressable>
                    </View>
                  </View>
                );
              })}
              {pend.length > 8 ? (
                <Pressable onPress={() => setPendAll(!pendAll)} style={{ padding: 12 }}>
                  <Text style={st.link}>{pendAll ? 'ย่อเหลือ 8 ราย' : `ดูอีก ${pend.length - 8} ราย`}</Text>
                </Pressable>
              ) : null}
            </Card>
          ) : null}
          {!items.length ? (
            <Text style={st.empty}>{pend.length ? 'ยังไม่มีลีดที่กดรับแล้ว — กด "รับ lead" ข้างบนก่อน แล้วค่อยจ่ายเบอร์' : 'ไม่มีลีดรอจ่ายเบอร์ 👍'}</Text>
          ) : null}
          {items.map((it) => {
            const [w, longWait] = waited(it.since);
            const [sl, sfg, sbg] = SRC[it.src] || SRC.other;
            const key = it.kind + ':' + it.id;
            return (
              <Card key={key} style={[{ gap: 8 }, longWait && { borderColor: C.red }]}>
                <View style={{ flexDirection: 'row', alignItems: 'flex-start', gap: 8 }}>
                  <View style={{ flex: 1, gap: 3 }}>
                    <Text style={st.name}>
                      {it.prefix ? <Text style={{ color: C.purple }}>{it.prefix} </Text> : null}
                      {it.name}
                    </Text>
                    <Text style={st.sub} numberOfLines={1}>{it.car || 'ไม่ระบุรุ่นรถ'}</Text>
                    <Text style={st.sub} numberOfLines={2}>{it.line}</Text>
                  </View>
                  <View style={{ alignItems: 'flex-end' }}>
                    <Text style={[st.wait, longWait && { color: C.red }]}>{w}</Text>
                    <Text style={st.sub}>พักมาแล้ว</Text>
                  </View>
                </View>
                <View style={st.tags}>
                  <Tag text={sl} color={sfg} bg={sbg} />
                  <Tag text={'เบอร์ ' + (it.hasPhone ? '✓' : '✗')} color={it.hasPhone ? C.green : C.sub} bg={it.hasPhone ? C.greenBg : '#eee'} />
                  {it.hasLine ? <Tag text="ID LINE ✓" color={C.green} bg={C.greenBg} /> : null}
                  {it.reposts ? <Tag text={`โพสต์ซ้ำ ${it.reposts}`} color={C.sub} bg="#eee" /> : null}
                </View>
                {it.dup ? (
                  <View style={st.dup}>
                    <Text style={{ color: C.red, fontSize: 13, lineHeight: 19 }}>
                      ⚠️ เบอร์ซ้ำ — เคยเป็นลีด {it.dup.code || '-'} ของ @{it.dup.seller || '?'}
                      {it.dup.date ? ` (${it.dup.date})` : ''} · ลูกค้าคนเดียวไม่ควรได้เซลล์ 2 คน
                    </Text>
                    {it.dup.sellerId ? (
                      <Pressable disabled={!!busy} onPress={() => assign(it, it.dup!.sellerId as number)} style={[st.sel, st.selDup]}>
                        <Text style={[st.selText, { color: '#fff' }]}>จ่ายให้ @{it.dup.seller} (เจ้าของเดิม)</Text>
                      </Pressable>
                    ) : null}
                  </View>
                ) : null}
                {board.length ? (
                  <View style={st.sels}>
                    {board.map((x, i) => (
                      <Pressable
                        key={x.id}
                        disabled={busy === key}
                        onPress={() => assign(it, x.id)}
                        style={({ pressed }) => [st.sel, i === 0 && st.selNext, (pressed || busy === key) && { opacity: 0.5 }]}>
                        <Text style={st.selText}>{x.name}</Text>
                        <Text style={st.selSub}>
                          {x.team} · {x.today}
                          {x.cap ? '/' + x.cap : ''}
                        </Text>
                      </Pressable>
                    ))}
                  </View>
                ) : (
                  <Text style={st.sub}>ไม่มีเซลล์ว่างในคิวจ่ายวน — เลือกเซลล์เองได้ที่หน้าเว็บ Connect</Text>
                )}
                <View style={{ flexDirection: 'row', gap: 16 }}>
                  <Pressable onPress={() => skip(it)} hitSlop={6}>
                    <Text style={st.link}>ไม่ต้องจ่ายเบอร์</Text>
                  </Pressable>
                  {it.kind === 'chat' ? (
                    <Pressable onPress={() => router.push({ pathname: '/chat/[id]', params: { id: it.id } })} hitSlop={6}>
                      <Text style={st.link}>เปิดแชท</Text>
                    </Pressable>
                  ) : null}
                </View>
              </Card>
            );
          })}
        </>
      ) : tab === 'buy' ? (
        <>
          <Text style={st.note}>
            {`ลูกค้าอยากขายรถให้เรา (ให้เบอร์/ID LINE แล้ว · ทักภายใน ${d?.buyRoomDays || 14} วัน) — ส่งใบเคสรับซื้อเข้ากลุ่มเคสHOT ของจัดซื้อ แล้วเติมเลขโค้ด · ระบบเจอใบในกลุ่มแล้วย้ายไป "จ่ายแล้ว" เอง`}
            {Object.values(d?.buyLast || {}).length ? ' · เลขล่าสุดในกลุ่ม ' + Object.values(d?.buyLast || {}).join(', ') : ''}
          </Text>
          {!buys.length ? <Text style={st.empty}>ไม่มีลีดรับซื้อรถรอส่งจัดซื้อ 👍</Text> : null}
          {buys.map((r) => {
            const [sl, sfg, sbg] = SRC[r.src === 'fb' ? 'fb' : 'line'];
            return (
              <Card key={r.id} style={{ gap: 6, borderColor: C.green }}>
                <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: 8 }}>
                  <Text style={st.name} numberOfLines={1}>{r.name || '(ไม่มีชื่อ)'}</Text>
                  <Text style={st.sub}>{fmtTime(r.lastAt)}</Text>
                </View>
                <View style={st.tags}>
                  <Tag text={sl} color={sfg} bg={sbg} />
                  {r.phone ? <Tag text={'เบอร์ ' + r.phone} color={C.green} bg={C.greenBg} /> : null}
                  {r.lineId ? <Tag text={'ID LINE ' + r.lineId} color={C.green} bg={C.greenBg} />
                    : r.contact === 'qr' ? <Tag text="QR LINE" color={C.green} bg={C.greenBg} /> : null}
                  {r.car ? <Tag text={r.car} color={C.sub} bg="#eee" /> : null}
                </View>
                <Text style={st.sub} numberOfLines={2}>
                  {r.dealBy === 'ระบบ' ? `จับจากแชท: "${r.dealWhy || ''}"` : `ตั้งโดย ${r.dealBy || '-'}`}
                </Text>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
                  <Pressable onPress={() => shareSlip(r)} style={({ pressed }) => [st.acc, { backgroundColor: C.green }, pressed && { opacity: 0.5 }]}>
                    <Text style={{ color: '#fff', fontWeight: '800', fontSize: 15 }}>ส่งใบเคสรับซื้อ</Text>
                  </Pressable>
                  <Pressable disabled={!!busy} onPress={() => setDeal(r, 'sell')} hitSlop={6}>
                    <Text style={st.link}>เป็นลีดขายรถ</Text>
                  </Pressable>
                  <Pressable onPress={() => skip({ kind: 'chat', id: String(r.id), name: r.name } as Item)} hitSlop={6}>
                    <Text style={st.link}>ไม่ใช่ลีด</Text>
                  </Pressable>
                  <Pressable onPress={() => router.push({ pathname: '/chat/[id]', params: { id: String(r.id) } })} hitSlop={6}>
                    <Text style={st.link}>เปิดแชท</Text>
                  </Pressable>
                </View>
              </Card>
            );
          })}
        </>
      ) : (
        <>
          {!done.length ? <Text style={st.empty}>วันนี้ยังไม่มีการจ่ายเบอร์</Text> : null}
          {done.map((x) => {
            const [sl, sfg, sbg] = SRC[x.src] || SRC.other;
            return (
              <Pressable
                key={x.key}
                disabled={!x.chatId}
                onPress={() => x.chatId && router.push({ pathname: '/chat/[id]', params: { id: String(x.chatId) } })}>
                <Card style={{ gap: 4 }}>
                  <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: 8 }}>
                    <Text style={st.name} numberOfLines={1}>{x.name}</Text>
                    <Text style={st.sub}>{fmtTime(x.at)}</Text>
                  </View>
                  <Text style={st.sub}>
                    {x.how === 'ส่งจัดซื้อ' ? 'ส่งจัดซื้อ ' : 'จ่ายให้ '}
                    <Text style={{ color: C.text, fontWeight: '700' }}>{x.seller ? '@' + x.seller : 'ไม่ทราบ'}</Text>
                  </Text>
                  <View style={st.tags}>
                    <Tag text={sl} color={sfg} bg={sbg} />
                    <Tag text={x.code} color={C.green} bg={C.greenBg} />
                    <Tag text={x.how + (x.by ? ' · โดย ' + x.by : '')} color={C.sub} bg="#eee" />
                  </View>
                </Card>
              </Pressable>
            );
          })}
        </>
      )}
    </ScrollView>
  );
}

const st = StyleSheet.create({
  seg: { flexDirection: 'row', gap: 8 },
  segBtn: {
    flex: 1,
    minHeight: 40,
    borderRadius: 8,
    borderWidth: 1.5,
    borderColor: C.purple,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#fff',
  },
  segOn: { backgroundColor: C.purple },
  segText: { color: C.purple, fontWeight: '700', fontSize: 14 },
  note: { fontSize: 12, color: C.sub, lineHeight: 18 },
  empty: { textAlign: 'center', color: C.sub, padding: 30 },
  name: { fontSize: 16, fontWeight: '800', color: C.text },
  sub: { fontSize: 13, color: C.sub, lineHeight: 18 },
  wait: { fontSize: 15, fontWeight: '800', color: C.amber },
  tags: { flexDirection: 'row', flexWrap: 'wrap', gap: 4 },
  dup: { backgroundColor: C.redBg, borderRadius: 8, padding: 10, gap: 8 },
  sels: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  sel: {
    minHeight: 44,
    minWidth: 72,
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 8,
    borderWidth: 1.5,
    borderColor: C.line,
    backgroundColor: '#fff',
    alignItems: 'center',
    justifyContent: 'center',
  },
  selNext: { borderColor: '#db2777', backgroundColor: '#fdf2f8' },
  selDup: { backgroundColor: C.red, borderColor: C.red, alignSelf: 'flex-start' },
  selText: { fontSize: 15, fontWeight: '800', color: C.text },
  selSub: { fontSize: 11, color: C.sub },
  link: { color: C.purple, fontWeight: '700', fontSize: 14 },
  pend: { padding: 12, gap: 6, borderTopWidth: 1, borderTopColor: C.line },
  acc: { backgroundColor: C.amber, borderRadius: 8, minHeight: 40, paddingHorizontal: 16, alignItems: 'center', justifyContent: 'center' },
});
