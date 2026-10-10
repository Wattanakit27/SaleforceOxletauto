// แจ้งเตือน (หน้ารวมแชท) — ลูกค้าใหม่รอรับ · เลยเวลา/ใกล้หมดเวลา · นัดวันนี้ · ลูกค้าเงียบ 3/5/7 วัน · รถใหม่ตรง
// แอปทดลองใน Expo Go ส่ง push ไม่ได้ → แจ้งเตือนอยู่ที่กระดิ่งในแอป (เปิดแอปแล้วเห็นทันที)
import { router, useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { FlatList, Pressable, RefreshControl, StyleSheet, Text, View } from 'react-native';

import { api } from '../lib/api';
import { AlertItem, Alerts, uniq } from '../lib/crm';
import { Banner, C, Loading } from '../lib/ui';

const DOT: Record<string, string> = { err: C.red, warn: '#f59e0b', info: C.purple };

export default function AlertsScreen() {
  const [d, setD] = useState<Alerts | null>(null);
  const [err, setErr] = useState('');
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      setD(await api<Alerts>('/connect/api/alerts'));
      setErr('');
    } catch (e: any) {
      setErr(e?.message || 'โหลดไม่สำเร็จ');
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load]),
  );

  const open = (it: AlertItem) => {
    if (it.id) {
      router.push({ pathname: '/chat/[id]', params: { id: String(it.id) } });
      return;
    }
    // กลับหน้ารายชื่อพร้อมตัวกรองของเรื่องนั้น (คิวรอรับ / ลูกค้าเงียบ / รถใหม่ตรง)
    const preset = JSON.stringify({ view: it.view || '', f: it.filter || {}, n: uniq() });
    router.navigate({ pathname: '/', params: { preset } });
  };

  if (!d && !err) return <Loading />;
  return (
    <FlatList
      data={d?.items || []}
      keyExtractor={(_, i) => String(i)}
      refreshControl={
        <RefreshControl
          refreshing={refreshing}
          tintColor={C.purple}
          onRefresh={async () => {
            setRefreshing(true);
            await load();
            setRefreshing(false);
          }}
        />
      }
      ListHeaderComponent={err ? <View style={{ padding: 12 }}><Banner text={err} kind="err" /></View> : null}
      ListEmptyComponent={<Text style={st.empty}>ไม่มีอะไรค้าง 👍</Text>}
      renderItem={({ item }) => (
        <Pressable onPress={() => open(item)} style={({ pressed }) => [st.row, pressed && { backgroundColor: C.purpleSoft }]}>
          <View style={[st.dot, { backgroundColor: DOT[item.level] || C.purple }]} />
          <Text style={st.text}>{item.text}</Text>
        </Pressable>
      )}
    />
  );
}

const st = StyleSheet.create({
  row: {
    flexDirection: 'row',
    gap: 12,
    alignItems: 'flex-start',
    padding: 14,
    backgroundColor: '#fff',
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: C.line,
  },
  dot: { width: 10, height: 10, borderRadius: 5, marginTop: 6 },
  text: { flex: 1, fontSize: 15, color: C.text, lineHeight: 22 },
  empty: { textAlign: 'center', color: C.sub, padding: 40, fontSize: 15 },
});
