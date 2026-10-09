// รายชื่อลูกค้า (Connect) — ข้อมูลชุดเดียวกับหน้า /connect/ ของเว็บ · สิทธิ์เช็คที่เซิร์ฟเวอร์ทั้งหมด
import { router, useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { FlatList, Pressable, RefreshControl, StyleSheet, Text, View } from 'react-native';

import { api } from '../../lib/api';
import { useAuth } from '../../lib/auth';
import { Avatar, Banner, C, fmtTime, Loading, Tag } from '../../lib/ui';

type Row = {
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
};

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
  // แต่ละรอบโหลดผูกกับแท็บของมันเอง — สลับแท็บแล้วผลของแท็บเก่าที่ตอบช้าต้องไม่มาทับ
  const fetchInbox = useCallback(async (v: string, alive: () => boolean) => {
    try {
      const r = await api<Inbox>(`/connect/api/inbox?view=${encodeURIComponent(v)}`);
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
      fetchInbox(view, alive);
      const t = setInterval(() => fetchInbox(view, alive), 10000);
      return () => {
        on = false;
        clearInterval(t);
      };
    }, [view, fetchInbox]),
  );

  const onRefresh = async () => {
    setRefreshing(true);
    await fetchInbox(view, () => true);
    setRefreshing(false);
  };

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
          ListEmptyComponent={<Text style={st.empty}>ยังไม่มีลูกค้าในแท็บนี้</Text>}
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
});
