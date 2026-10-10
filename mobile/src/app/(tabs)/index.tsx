// รายชื่อลูกค้า (Connect) — ข้อมูลชุดเดียวกับหน้า /connect/ ของเว็บ · สิทธิ์เช็คที่เซิร์ฟเวอร์ทั้งหมด
import { Redirect, router, useFocusEffect, useLocalSearchParams } from 'expo-router';
import { useCallback, useEffect, useState } from 'react';
import { Alert, FlatList, Pressable, RefreshControl, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';

import { api } from '../../lib/api';
import { canChat, useAuth } from '../../lib/auth';
import { CrmTags, Extra } from '../../lib/crm';
import { Avatar, Banner, Btn, C, fmtTime, Loading, Tag } from '../../lib/ui';

type Row = Extra & {
  id: number;
  name: string;
  preview: string;
  lastAt: string;
  lastDir: string;
  owner: string;
  awaiting: boolean;
  overdue: boolean;
  unread: boolean;
  mine: boolean;
  pic: string;
  sim: boolean;
  src: 'line' | 'fb';
  staff: boolean;
  code: string;
};
type Inbox = {
  view: string;
  rows: Row[];
  counts: Record<string, number>;
  note: string;
  status: { level: string; text: string }[];
  onDuty: boolean;
  duty: { today: string; tomorrow: string };
  crm?: { stages: { key: string; label: string }[] };
};

// ★ 11 ต.ค.69 หน้ารวมแชท — ตัวกรองลัด (ชุดเดียวกับหน้าเว็บ /connect/)
const QUICK: { k: string; v: string; l: string }[] = [
  { k: 'awaiting', v: '1', l: 'รอเราตอบ' },
  { k: 'follow', v: 'today', l: 'ติดตามวันนี้' },
  { k: 'noreply', v: '1', l: 'ลูกค้าไม่ตอบกลับ' },
  { k: 'silent', v: '3', l: 'เงียบ 3+ วัน' },
  { k: 'silent', v: '7', l: 'เงียบ 7+ วัน' },
  { k: 'heat', v: 'hot', l: '🔥 ร้อน' },
  { k: 'carmatch', v: '1', l: 'รถใหม่ตรง' },
];

const SELLER_TABS = [
  { key: 'queue', label: 'คิวรอรับ', count: 'queue' },
  { key: 'mine', label: 'ลูกค้าของฉัน', count: 'mine' },
];
const ADMIN_TABS = [
  { key: 'queue', label: 'รอรับ', count: 'queue' },
  { key: 'owned', label: 'มีเจ้าของ', count: 'owned' },
  { key: 'all', label: 'ทั้งหมด', count: 'all' },
];

export default function ChatList() {
  const { me } = useAuth();
  const tabs = me?.admin ? ADMIN_TABS : SELLER_TABS;
  const [view, setView] = useState(tabs[0].key);
  const [data, setData] = useState<Inbox | null>(null);
  const [err, setErr] = useState('');
  const [refreshing, setRefreshing] = useState(false);
  const [q, setQ] = useState('');
  const [query, setQuery] = useState(''); // ค่าที่ส่งไปค้นจริง (รอหยุดพิมพ์ก่อน)
  const [f, setF] = useState<Record<string, string>>({}); // ตัวกรองหน้ารวมแชท
  const [running, setRunning] = useState(false);
  const { preset } = useLocalSearchParams<{ preset?: string }>();
  const [seenPreset, setSeenPreset] = useState<string | undefined>(undefined);

  // มาจากหน้าแจ้งเตือน (ลูกค้าเงียบ / รถใหม่ตรง / คิวรอรับ) → ตั้งแท็บ + ตัวกรองให้
  //   ปรับ state ตอน render เมื่อค่าที่ส่งมาเปลี่ยน (แบบที่ React แนะนำ — ไม่ใช้ effect)
  if (preset && preset !== seenPreset) {
    setSeenPreset(preset);
    try {
      const p = JSON.parse(String(preset)) as { view?: string; f?: Record<string, string> };
      setF(p.f || {});
      const v = p.view || (me?.admin ? 'all' : 'mine');
      if (tabs.some((t) => t.key === v)) {
        setData(null);
        setView(v);
      }
    } catch {
      // ค่าเสีย — เพิกเฉย
    }
  }

  useEffect(() => {
    const t = setTimeout(() => setQuery(q.trim()), 400);
    return () => clearTimeout(t);
  }, [q]);

  // แต่ละรอบโหลดผูกกับแท็บของมันเอง — สลับแท็บแล้วผลของแท็บเก่าที่ตอบช้าต้องไม่มาทับ
  const fetchInbox = useCallback(async (v: string, qq: string, ff: Record<string, string>, alive: () => boolean) => {
    try {
      const extra = Object.entries(ff)
        .map(([k, x]) => `&${encodeURIComponent(k)}=${encodeURIComponent(x)}`)
        .join('');
      const r = await api<Inbox>(
        `/connect/api/inbox?view=${encodeURIComponent(v)}` + (qq ? `&q=${encodeURIComponent(qq)}` : '') + extra,
      );
      if (alive()) {
        setData(r);
        setErr('');
      }
    } catch (e: any) {
      if (alive()) setErr(e?.message || 'โหลดไม่สำเร็จ');
    }
  }, []);

  // เปิดหน้า/กลับมาหน้านี้ = โหลดใหม่ + รีเฟรชทุก 10 วิ ระหว่างเปิดอยู่
  useFocusEffect(
    useCallback(() => {
      let on = true;
      const alive = () => on;
      fetchInbox(view, query, f, alive);
      const t = setInterval(() => fetchInbox(view, query, f, alive), 10000);
      return () => {
        on = false;
        clearInterval(t);
      };
    }, [view, query, f, fetchInbox]),
  );

  const onRefresh = async () => {
    setRefreshing(true);
    await fetchInbox(view, query, f, () => true);
    setRefreshing(false);
  };

  const toggle = (k: string, v: string) =>
    setF((cur) => {
      const n = { ...cur };
      if (n[k] === v) delete n[k];
      else n[k] = v;
      return n;
    });

  // ★ Run Auto (แอดมิน · คิวรอรับ) — จ่ายลูกค้ารอรับให้เซลล์ตามคิวจ่ายวน · โอนในระบบเท่านั้น ไม่ส่ง LINE
  const runAuto = () =>
    Alert.alert(
      'Run Auto',
      `จ่ายลูกค้ารอรับ ${data?.rows.length || 0} คนให้เซลล์ตามคิวจ่ายวนเลยไหม?\n(คนได้น้อยสุดก่อน · เบอร์เคยเป็นลีดของใครส่งกลับคนนั้น)`,
      [
        { text: 'ยกเลิก', style: 'cancel' },
        {
          text: 'จ่ายเลย',
          onPress: async () => {
            setRunning(true);
            try {
              const r = await api<{ message: string; assigned: { name: string; to: string; why: string }[]; skipped: { name: string; why: string }[] }>(
                '/connect/api/crm',
                { body: { action: 'run_auto' } },
              );
              const lines = r.assigned.map((a) => `${a.name} → @${a.to}`).concat(r.skipped.map((s) => `ข้าม ${s.name} — ${s.why}`));
              Alert.alert(r.message, lines.join('\n').slice(0, 900));
              await fetchInbox(view, query, f, () => true);
            } catch (e: any) {
              Alert.alert('Run Auto ไม่สำเร็จ', e?.message || '');
            } finally {
              setRunning(false);
            }
          },
        },
      ],
    );

  if (me && !canChat(me)) return <Redirect href="/scan" />; // คนงานใช้แชทลูกค้าไม่ได้

  return (
    <View style={{ flex: 1 }}>
      <View style={st.tabs}>
        {tabs.map((t) => {
          const on = t.key === view;
          const n = data?.counts?.[t.count];
          return (
            <Pressable
              key={t.key}
              onPress={() => {
                setData(null);
                setView(t.key);
              }}
              style={[st.tab, on && st.tabOn]}>
              <Text style={[st.tabText, on && { color: '#fff' }]}>
                {t.label}
                {typeof n === 'number' ? ` ${n}` : ''}
              </Text>
            </Pressable>
          );
        })}
      </View>
      <View style={st.searchWrap}>
        <TextInput
          style={st.search}
          value={q}
          onChangeText={setQ}
          placeholder="ค้นหา ชื่อ / เบอร์ / เลขลีด"
          placeholderTextColor={C.sub}
          clearButtonMode="while-editing"
          autoCorrect={false}
          returnKeyType="search"
        />
      </View>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ flexGrow: 0 }} contentContainerStyle={st.quick}>
        {QUICK.map((x, i) => {
          const on = f[x.k] === x.v;
          return (
            <Pressable key={i} onPress={() => toggle(x.k, x.v)} style={[st.qchip, on && st.qchipOn]}>
              <Text style={[st.qtext, on && { color: '#fff' }]}>{x.l}</Text>
            </Pressable>
          );
        })}
        {(data?.crm?.stages || [])
          .filter((s) => s.key !== 'new')
          .map((s) => {
            const on = f.stage === s.key;
            return (
              <Pressable key={'st' + s.key} onPress={() => toggle('stage', s.key)} style={[st.qchip, on && st.qchipOn]}>
                <Text style={[st.qtext, on && { color: '#fff' }]}>{s.label}</Text>
              </Pressable>
            );
          })}
        {Object.keys(f).length ? (
          <Pressable onPress={() => setF({})} style={[st.qchip, { borderColor: C.red }]}>
            <Text style={[st.qtext, { color: C.red }]}>ล้างตัวกรอง</Text>
          </Pressable>
        ) : null}
      </ScrollView>
      {me?.admin && view === 'queue' && (data?.rows.length || 0) > 0 ? (
        <View style={{ paddingHorizontal: 12, paddingBottom: 6 }}>
          <Btn small title={`Run Auto — จ่าย ${data?.rows.length} คนตามคิว`} busy={running} onPress={runAuto} />
        </View>
      ) : null}
      {data?.duty ? (
        <Text style={st.duty}>
          เวรวันนี้ ทีม {data.duty.today || '-'} · พรุ่งนี้ทีม {data.duty.tomorrow || '-'}
        </Text>
      ) : null}
      {err ? (
        <View style={{ padding: 12 }}>
          <Banner text={err} kind="err" />
        </View>
      ) : null}
      {!data && !err ? (
        <Loading />
      ) : (
        <FlatList
          data={data?.rows || []}
          keyExtractor={(r) => String(r.id)}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={C.purple} />}
          contentContainerStyle={{ paddingBottom: 40 }}
          ListHeaderComponent={
            <View style={{ gap: 8, padding: data?.note || data?.status?.length ? 12 : 0 }}>
              {(data?.status || []).map((s, i) => (
                <Banner key={i} text={s.text} kind={s.level === 'err' ? 'err' : 'warn'} />
              ))}
              {data?.note ? <Banner text={data.note} kind="info" /> : null}
            </View>
          }
          ListEmptyComponent={
            <Text style={st.empty}>{Object.keys(f).length ? 'ไม่มีลูกค้าที่ตรงกับตัวกรอง' : 'ยังไม่มีลูกค้าในแท็บนี้'}</Text>
          }
          renderItem={({ item: r }) => (
            <Pressable
              onPress={() => router.push({ pathname: '/chat/[id]', params: { id: String(r.id), name: r.name } })}
              style={({ pressed }) => [st.row, pressed && { backgroundColor: C.purpleSoft }]}>
              <Avatar name={r.name} pic={r.pic} />
              <View style={{ flex: 1, minWidth: 0 }}>
                <View style={st.line1}>
                  <Text style={[st.name, r.unread && { fontWeight: '800' }]} numberOfLines={1}>
                    {r.name || '(ไม่มีชื่อ)'}
                  </Text>
                  <Text style={[st.time, r.unread && { color: C.red, fontWeight: '700' }]}>
                    {fmtTime(r.lastAt)}
                  </Text>
                  {r.unread ? <View style={st.dot} /> : null}
                </View>
                <Text style={[st.preview, r.unread && { color: C.text, fontWeight: '700' }]} numberOfLines={1}>
                  {r.lastDir === 'out' ? 'คุณ: ' : ''}
                  {r.preview}
                </Text>
                <View style={st.tags}>
                  <Tag
                    text={r.src === 'fb' ? 'Facebook' : 'LINE'}
                    color={r.src === 'fb' ? C.fb : C.lineGreen}
                    bg={r.src === 'fb' ? '#e7f0fe' : '#e6f9ee'}
                  />
                  <CrmTags r={r} />
                  {r.overdue ? <Tag text="เลยเวลา" color={C.red} bg={C.redBg} /> : null}
                  {!r.overdue && r.awaiting ? <Tag text="รอตอบ" color={C.amber} bg={C.amberBg} /> : null}
                  {r.owner ? <Tag text={'@' + r.owner} /> : null}
                  {r.code ? <Tag text={r.code} color={C.green} bg={C.greenBg} /> : null}
                  {r.sim ? <Tag text="ลูกค้าจำลอง" color={C.sub} bg="#eee" /> : null}
                  {r.staff ? <Tag text="พนักงาน" color={C.sub} bg="#eee" /> : null}
                </View>
              </View>
            </Pressable>
          )}
        />
      )}
    </View>
  );
}

const st = StyleSheet.create({
  tabs: { flexDirection: 'row', gap: 8, padding: 12, paddingBottom: 6 },
  tab: {
    flex: 1,
    minHeight: 40,
    borderRadius: 8,
    borderWidth: 1.5,
    borderColor: C.purple,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#fff',
  },
  tabOn: { backgroundColor: C.purple },
  tabText: { color: C.purple, fontWeight: '700', fontSize: 14 },
  duty: { fontSize: 13, color: C.sub, paddingHorizontal: 14, paddingBottom: 4 },
  searchWrap: { paddingHorizontal: 12, paddingBottom: 6 },
  search: {
    minHeight: 40,
    borderWidth: 1,
    borderColor: C.line,
    borderRadius: 8,
    paddingHorizontal: 12,
    fontSize: 15,
    color: C.text,
    backgroundColor: '#fff',
  },
  row: {
    flexDirection: 'row',
    gap: 12,
    paddingHorizontal: 14,
    paddingVertical: 12,
    backgroundColor: '#fff',
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: C.line,
  },
  line1: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  name: { flex: 1, fontSize: 16, fontWeight: '600', color: C.text },
  time: { fontSize: 12, color: C.sub },
  dot: { width: 8, height: 8, borderRadius: 4, backgroundColor: C.red },
  preview: { fontSize: 14, color: C.sub, marginTop: 2 },
  tags: { flexDirection: 'row', flexWrap: 'wrap', gap: 4, marginTop: 6 },
  empty: { textAlign: 'center', color: C.sub, padding: 40 },
  quick: { gap: 6, paddingHorizontal: 12, paddingBottom: 8 },
  qchip: { paddingHorizontal: 10, paddingVertical: 6, borderRadius: 7, borderWidth: 1, borderColor: C.line, backgroundColor: '#fff' },
  qchipOn: { backgroundColor: C.purple, borderColor: C.purple },
  qtext: { fontSize: 13, fontWeight: '700', color: C.text },
});
