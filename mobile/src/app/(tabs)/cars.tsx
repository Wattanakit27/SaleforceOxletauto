// แท็บ "รถ" — รถทุกคันในระบบติดตามรถ (GET /track/api/cars · ตัวเดียวกับบอร์ด /track/ ของเว็บ)
// สแกน QR · ค้นหาทะเบียน/รหัส/รุ่น · กรองตามเฟส/ค้าง/ออกนอกลาน/ที่ฉันเบิก · แตะ = หน้ารถ (เปลี่ยนสเตป · เบิก-คืน)
import { router, useFocusEffect } from 'expo-router';
import { useCallback, useMemo, useState } from 'react';
import { FlatList, Image, Pressable, RefreshControl, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';

import { absUrl, api } from '../../lib/api';
import { Banner, Btn, C, Loading, Tag } from '../../lib/ui';

type Car = {
  code: string;
  title: string;
  plate: string;
  branch: string;
  stage: string;
  stageName: string;
  sold: boolean;
  flag: 'red' | 'amber' | 'ok' | 'wait';
  days: number;
  price: string;
  priority: string;
  priorityName: string;
  priorityColor: string;
  flags: { key: string; name: string; color: string }[];
  photo: string;
  year: number;
  dateInTs: number;
  out: { who: string; purpose: string; mine: boolean; since: string } | null;
};
type Resp = { cars: Car[]; phaseRows: { name: string; stages: { key: string }[] }[]; total: number };

type F = { k: string; label: string; test: (c: Car) => boolean };

const norm = (s: string) => (s || '').toLowerCase().replace(/[\s-]/g, '');

export default function Cars() {
  const [d, setD] = useState<Resp | null>(null);
  const [err, setErr] = useState('');
  const [refreshing, setRefreshing] = useState(false);
  const [q, setQ] = useState('');
  const [fk, setFk] = useState('all');
  const [sort, setSort] = useState<'days' | 'new'>('days');

  const load = useCallback(async () => {
    try {
      setD(await api<Resp>('/track/api/cars', { timeoutMs: 45000 }));
      setErr('');
    } catch (e: any) {
      setErr(e?.message || 'โหลดรถไม่สำเร็จ');
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load]),
  );

  const phaseOf = useMemo(() => {
    const m: Record<string, string> = {};
    (d?.phaseRows || []).forEach((p) => p.stages.forEach((s) => (m[s.key] = p.name)));
    return m;
  }, [d]);
  const order = useMemo(() => {
    const m: Record<string, number> = {};
    let i = 0;
    (d?.phaseRows || []).forEach((p) => p.stages.forEach((s) => (m[s.key] = i++)));
    return m;
  }, [d]);

  const active = useMemo(() => (d?.cars || []).filter((c) => !c.sold), [d]);
  const filters: F[] = useMemo(() => {
    const phases = (d?.phaseRows || []).map((p) => p.name);
    return [
      { k: 'all', label: 'ทั้งหมด', test: () => true },
      { k: 'show', label: 'พร้อมขาย', test: (c: Car) => c.stage === 'show' },
      { k: 'stuck', label: 'ค้างนาน', test: (c: Car) => c.flag === 'red' || c.flag === 'amber' },
      { k: 'out', label: 'ออกนอกลาน', test: (c: Car) => !!c.out },
      { k: 'mine', label: 'ฉันเบิกอยู่', test: (c: Car) => !!c.out?.mine },
      ...phases.map((p) => ({ k: 'ph:' + p, label: p, test: (c: Car) => phaseOf[c.stage] === p })),
    ];
  }, [d, phaseOf]);

  const rows = useMemo(() => {
    const f = filters.find((x) => x.k === fk) || filters[0];
    const nq = norm(q);
    let out = active.filter(f.test);
    if (nq) out = out.filter((c) => [c.plate, c.code, c.title].some((v) => norm(v).includes(nq)));
    out = [...out];
    if (sort === 'new') out.sort((a, b) => b.dateInTs - a.dateInTs);
    else out.sort((a, b) => b.days - a.days || (order[a.stage] ?? 99) - (order[b.stage] ?? 99));
    return out;
  }, [active, filters, fk, q, sort, order]);

  const onRefresh = async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  };

  return (
    <View style={{ flex: 1 }}>
      <View style={st.top}>
        <Btn title="📷  สแกน QR รถ" onPress={() => router.push('/scan')} />
        <TextInput
          style={st.search}
          value={q}
          onChangeText={setQ}
          placeholder="ค้นหา ทะเบียน / รหัสรถ / รุ่น"
          placeholderTextColor={C.sub}
          clearButtonMode="while-editing"
          autoCorrect={false}
        />
      </View>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ flexGrow: 0 }} contentContainerStyle={st.chips}>
        {filters.map((f) => {
          const on = f.k === fk;
          const n = active.filter(f.test).length;
          if (f.k === 'mine' && !n) return null;
          return (
            <Pressable key={f.k} onPress={() => setFk(f.k)} style={[st.chip, on && st.chipOn]}>
              <Text style={[st.chipText, on && { color: '#fff' }]}>
                {f.label} {n}
              </Text>
            </Pressable>
          );
        })}
      </ScrollView>
      <View style={st.sortRow}>
        <Text style={st.sub}>{rows.length} คัน</Text>
        <View style={{ flexDirection: 'row', gap: 6 }}>
          {(
            [
              ['days', 'ค้างนานสุด'],
              ['new', 'เข้าล่าสุด'],
            ] as const
          ).map(([k, l]) => (
            <Pressable key={k} onPress={() => setSort(k)} style={[st.sortBtn, sort === k && st.chipOn]}>
              <Text style={[st.sortText, sort === k && { color: '#fff' }]}>{l}</Text>
            </Pressable>
          ))}
        </View>
      </View>
      {err ? (
        <View style={{ padding: 12 }}>
          <Banner kind="err" text={err} />
        </View>
      ) : null}
      {!d && !err ? (
        <Loading text="กำลังโหลดรถ…" />
      ) : (
        <FlatList
          data={rows}
          keyExtractor={(c) => c.code}
          initialNumToRender={15}
          windowSize={7}
          contentContainerStyle={{ padding: 12, gap: 8, paddingBottom: 40 }}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={C.purple} />}
          ListEmptyComponent={<Text style={st.empty}>{q ? 'ไม่พบรถที่ค้นหา' : 'ไม่มีรถในหมวดนี้'}</Text>}
          renderItem={({ item: c }) => <CarItem c={c} />}
        />
      )}
    </View>
  );
}

function CarItem({ c }: { c: Car }) {
  const late = c.flag === 'red' ? C.red : c.flag === 'amber' ? C.amber : C.sub;
  return (
    <Pressable
      onPress={() => router.push({ pathname: '/car/[code]', params: { code: c.code } })}
      style={({ pressed }) => [st.row, { borderLeftColor: c.priorityColor || C.line }, pressed && { backgroundColor: C.purpleSoft }]}>
      <View style={st.photo}>
        <Text style={{ fontSize: 22 }}>🚗</Text>
        {c.photo ? <Image source={{ uri: absUrl(c.photo) }} style={StyleSheet.absoluteFill} resizeMode="cover" /> : null}
      </View>
      <View style={{ flex: 1, minWidth: 0, gap: 2 }}>
        <Text style={st.plate} numberOfLines={1}>
          {c.plate || c.code} <Text style={st.title}>{c.title}</Text>
        </Text>
        <Text style={st.sub} numberOfLines={1}>
          {c.stageName} ·{' '}
          <Text style={{ color: late, fontWeight: c.flag === 'red' || c.flag === 'amber' ? '700' : '400' }}>
            {c.flag === 'wait' ? 'รอถ่ายรูป ' : ''}
            {c.days} วัน
          </Text>
          {c.stage === 'show' && c.price ? ` · ฿${c.price}` : ''}
          {c.branch ? ` · ${c.branch}` : ''}
        </Text>
        <View style={st.tags}>
          {c.out ? (
            <Tag text={`ออกนอกลาน · ${c.out.mine ? 'คุณ' : c.out.who}`} color={c.out.mine ? '#fff' : C.amber} bg={c.out.mine ? C.amber : C.amberBg} />
          ) : null}
          {c.priority && c.priority !== 'normal' ? <Tag text={c.priorityName} color="#fff" bg={c.priorityColor} /> : null}
          {c.flags.map((f) => (
            <Tag key={f.key} text={f.name} color="#fff" bg={f.color} />
          ))}
        </View>
      </View>
      <Text style={st.chev}>›</Text>
    </Pressable>
  );
}

const st = StyleSheet.create({
  top: { padding: 12, paddingBottom: 6, gap: 8 },
  search: {
    minHeight: 42,
    borderWidth: 1,
    borderColor: C.line,
    borderRadius: 8,
    paddingHorizontal: 12,
    fontSize: 15,
    color: C.text,
    backgroundColor: '#fff',
  },
  chips: { gap: 6, paddingHorizontal: 12, paddingBottom: 6 },
  chip: { paddingHorizontal: 10, paddingVertical: 7, borderRadius: 7, borderWidth: 1, borderColor: C.line, backgroundColor: '#fff' },
  chipOn: { backgroundColor: C.purple, borderColor: C.purple },
  chipText: { fontSize: 13, fontWeight: '700', color: C.text },
  sortRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 14 },
  sortBtn: { paddingHorizontal: 8, paddingVertical: 4, borderRadius: 6, borderWidth: 1, borderColor: C.line, backgroundColor: '#fff' },
  sortText: { fontSize: 12, fontWeight: '700', color: C.text },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    backgroundColor: '#fff',
    borderRadius: 10,
    padding: 10,
    borderLeftWidth: 5,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
  },
  photo: {
    width: 64,
    height: 48,
    borderRadius: 6,
    backgroundColor: C.purpleSoft,
    alignItems: 'center',
    justifyContent: 'center',
    overflow: 'hidden',
  },
  plate: { fontSize: 16, fontWeight: '800', color: C.text },
  title: { fontSize: 14, fontWeight: '400', color: C.sub },
  sub: { fontSize: 13, color: C.sub },
  tags: { flexDirection: 'row', flexWrap: 'wrap', gap: 4, marginTop: 2 },
  chev: { fontSize: 24, color: C.sub },
  empty: { textAlign: 'center', color: C.sub, padding: 40 },
});
