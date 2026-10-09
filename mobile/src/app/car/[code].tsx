// หน้ารถ 1 คัน (เปิดจากสแกน QR) — ข้อมูลชุดเดียวกับป๊อปอัปรถบนบอร์ดของเว็บ
// เปลี่ยนสเตป: เลือกสเตป → หมายเหตุ + รูป (+ เช็คลิสต์ตรวจรถ ถ้าเป็นสเตปตรวจ) → ยืนยัน
// กติกา "ต้องแนบรูป/หมายเหตุ" มาจากเซิร์ฟเวอร์ (rules) และเซิร์ฟเวอร์ตรวจซ้ำอีกชั้นเสมอ
import * as ImagePicker from 'expo-image-picker';
import { Stack, useLocalSearchParams } from 'expo-router';
import { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  Image,
  KeyboardAvoidingView,
  Linking,
  Platform,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  TextInput,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { absUrl, api } from '../../lib/api';
import { Banner, Btn, C, Card, Loading, Tag } from '../../lib/ui';

type Media = { url: string; video: boolean };
type Log = { stage: string; worker: string; note: string; at: string; dur: string; cur: boolean; media: Media[] };
type Direct = { key: string; name: string; ph: string; color: string; owner: string };
type Car = {
  code: string;
  title: string;
  plate: string;
  year: number | null;
  color: string;
  km: number | null;
  branch: string;
  stage: string;
  stageName: string;
  daysInStage: number;
  flag: string;
  priorityName: string;
  priorityColor: string;
  showPriority: boolean;
  flags: { key: string; name: string; color: string }[];
  outNow: { who: string; why: string; where: string; since: string } | null;
  photo: string;
  price: string;
  logs: Log[];
  direct: Direct[];
  role: string;
  rules: { forceMedia: string[]; forceNote: string[]; checklistStages: string[]; checklistItems: string[] };
};
type Shot = { uri: string; video: boolean; id?: string; err?: string; uploading: boolean };

const PHASE_NAME: Record<string, string> = {
  intake_phase: 'รับเข้า',
  recon_phase: 'ทำสภาพ',
  sale_phase: 'ขาย',
  release_phase: 'ปล่อยรถ',
};

export default function CarScreen() {
  const { code } = useLocalSearchParams<{ code: string }>();
  const [car, setCar] = useState<Car | null>(null);
  const [err, setErr] = useState('');
  const [refreshing, setRefreshing] = useState(false);
  const [pick, setPick] = useState<Direct | null>(null);
  const [note, setNote] = useState('');
  const [shots, setShots] = useState<Shot[]>([]);
  const [chk, setChk] = useState<Record<string, boolean>>({});
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try {
      const r = await api<Car>(`/track/api/m/car/${encodeURIComponent(String(code))}`);
      setCar(r);
      setErr('');
    } catch (e: any) {
      setErr(e?.message || 'เปิดข้อมูลรถไม่สำเร็จ');
    }
  }, [code]);

  useEffect(() => {
    load();
  }, [load]);

  const choose = (d: Direct) => {
    setPick(d);
    setNote('');
    setShots([]);
    const items = car?.rules.checklistItems || [];
    setChk(Object.fromEntries(items.map((i) => [i, true]))); // ค่าตั้งต้น = ผ่านทุกข้อ เอาออกเฉพาะข้อที่มีปัญหา (เหมือนเว็บ)
  };

  const upload = async (a: ImagePicker.ImagePickerAsset) => {
    const video = a.type === 'video';
    const shot: Shot = { uri: a.uri, video, uploading: true };
    setShots((cur) => [...cur, shot]);
    const form = new FormData();
    const name = a.fileName || `${video ? 'video' : 'photo'}-${Date.now()}.${video ? 'mp4' : 'jpg'}`;
    // React Native รับไฟล์ใน FormData เป็น {uri, name, type}
    form.append('file', { uri: a.uri, name, type: a.mimeType || (video ? 'video/mp4' : 'image/jpeg') } as any);
    form.append('code', String(code));
    try {
      const r = await api<{ id: string }>('/track/api/upload', { form, timeoutMs: 180000 });
      setShots((cur) => cur.map((s) => (s.uri === a.uri ? { ...s, id: r.id, uploading: false } : s)));
    } catch (e: any) {
      setShots((cur) =>
        cur.map((s) => (s.uri === a.uri ? { ...s, err: e?.message || 'อัปไม่สำเร็จ', uploading: false } : s)),
      );
    }
  };

  const takePhoto = async () => {
    const p = await ImagePicker.requestCameraPermissionsAsync();
    if (!p.granted) {
      Alert.alert('ต้องอนุญาตใช้กล้องก่อน');
      return;
    }
    const r = await ImagePicker.launchCameraAsync({ mediaTypes: ['images'], quality: 0.6 });
    if (!r.canceled) r.assets.forEach(upload);
  };

  const fromLibrary = async () => {
    const r = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ['images', 'videos'],
      allowsMultipleSelection: true,
      selectionLimit: 10,
      quality: 0.6,
    });
    if (!r.canceled) r.assets.forEach(upload);
  };

  if (err && !car) {
    return (
      <View style={{ padding: 16, gap: 12 }}>
        <Stack.Screen options={{ title: String(code) }} />
        <Banner text={err} kind="err" />
        <Btn title="ลองใหม่" onPress={load} />
      </View>
    );
  }
  if (!car) return <Loading />;

  const needMedia = !!pick && car.rules.forceMedia.includes(pick.key);
  const needNote = !!pick && car.rules.forceNote.includes(pick.key);
  const showChk = !!pick && car.rules.checklistStages.includes(pick.key);
  const ready = shots.filter((s) => s.id);
  const busyUp = shots.some((s) => s.uploading);
  const missing: string[] = [];
  if (needMedia && !ready.length) missing.push('แนบรูป');
  if (needNote && !note.trim()) missing.push('ใส่หมายเหตุ'); // เช็คก่อนต่อผลเช็คลิสต์ (ไม่งั้นนับเป็นหมายเหตุหลอก)

  const submit = async () => {
    if (!pick) return;
    if (busyUp) {
      Alert.alert('รอรูปอัปโหลดให้เสร็จก่อน');
      return;
    }
    if (missing.length) {
      Alert.alert('ยังขาด', missing.join(' และ '));
      return;
    }
    let full = note.trim();
    if (showChk) {
      const items = car.rules.checklistItems;
      const bad = items.filter((i) => !chk[i]);
      const ok = items.filter((i) => chk[i]);
      const parts: string[] = [];
      if (bad.length) parts.push('❌ ไม่ผ่าน: ' + bad.join(' · '));
      if (ok.length) parts.push('✅ ผ่าน: ' + ok.join(' · '));
      if (parts.length) full = (full ? full + '\n' : '') + '[ตรวจรถ] ' + parts.join('\n');
    }
    setSaving(true);
    try {
      await api('/track/api/seller_set_stage', {
        body: { code: car.code, stage: pick.key, note: full, media: ready.map((s) => ({ id: s.id, video: s.video })) },
      });
      setPick(null);
      setShots([]);
      setNote('');
      await load();
      Alert.alert('บันทึกแล้ว', `เปลี่ยนเป็น "${pick.name}"`);
    } catch (e: any) {
      Alert.alert('เปลี่ยนสเตปไม่สำเร็จ', e?.message || '');
    } finally {
      setSaving(false);
    }
  };

  // ปุ่มสเตปแยกกลุ่มตามเฟส (บทบาทสิทธิ์เต็มมี 20 ปุ่ม กองรวมจะรก)
  const groups: { ph: string; items: Direct[] }[] = [];
  car.direct.forEach((d) => {
    const g = groups.find((x) => x.ph === d.ph);
    if (g) g.items.push(d);
    else groups.push({ ph: d.ph, items: [d] });
  });

  return (
    <SafeAreaView style={{ flex: 1 }} edges={['bottom']}>
      <Stack.Screen options={{ title: car.plate || car.code }} />
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        keyboardVerticalOffset={Platform.OS === 'ios' ? 90 : 0}>
        <ScrollView
          contentContainerStyle={{ padding: 14, gap: 14, paddingBottom: 40 }}
          keyboardShouldPersistTaps="handled"
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
          }>
          <Card style={{ gap: 10 }}>
            {car.photo ? (
              <Image source={{ uri: absUrl(car.photo) }} style={st.hero} resizeMode="cover" />
            ) : null}
            <Text style={st.title}>{car.title || car.code}</Text>
            <Text style={st.sub}>
              {car.code}
              {car.plate ? ` · ${car.plate}` : ''}
              {car.branch ? ` · ${car.branch}` : ''}
              {car.price ? ` · ฿${car.price}` : ''}
            </Text>
            <View style={st.stageRow}>
              <View style={[st.stagePill, { backgroundColor: C.purple }]}>
                <Text style={{ color: '#fff', fontWeight: '700', fontSize: 15 }}>{car.stageName}</Text>
              </View>
              <Text style={[st.sub, car.flag === 'red' && { color: C.red, fontWeight: '700' },
                car.flag === 'amber' && { color: C.amber, fontWeight: '700' }]}>
                {car.flag === 'wait' ? 'รอถ่ายรูป ' : 'อยู่สเตปนี้ '}
                {car.daysInStage} วัน
              </Text>
            </View>
            <View style={st.tags}>
              {car.showPriority ? (
                <Tag text={'ความด่วน: ' + car.priorityName} color="#fff" bg={car.priorityColor || C.sub} />
              ) : null}
              {car.flags.map((f) => (
                <Tag key={f.key} text={f.name} color="#fff" bg={f.color} />
              ))}
            </View>
            {car.outNow ? (
              <Banner
                kind="warn"
                text={`🚗 ออกนอกลาน — ${car.outNow.who} · ${car.outNow.why}${car.outNow.where ? ' · ' + car.outNow.where : ''} (ตั้งแต่ ${car.outNow.since})`}
              />
            ) : null}
          </Card>

          <Card style={{ gap: 12 }}>
            <Text style={st.h2}>เปลี่ยนสเตป</Text>
            {!car.direct.length ? (
              <Banner
                kind="info"
                text={'บัญชีนี้ยังไม่มีสิทธิ์เปลี่ยนสเตปรถ — ให้แอดมินตั้งบทบาทให้ที่ /track/users/' +
                  (car.role ? ` (บทบาทตอนนี้: ${car.role})` : '')}
              />
            ) : null}
            {groups.map((g) => (
              <View key={g.ph || 'x'} style={{ gap: 8 }}>
                {groups.length > 1 ? <Text style={st.phase}>{PHASE_NAME[g.ph] || g.ph}</Text> : null}
                {g.items.map((d) => {
                  const on = pick?.key === d.key && pick?.name === d.name;
                  return (
                    <Pressable
                      key={d.key + d.name}
                      onPress={() => (on ? setPick(null) : choose(d))}
                      style={[st.stageBtn, { borderLeftColor: d.color || C.purple }, on && st.stageBtnOn]}>
                      <Text style={[st.stageBtnText, on && { color: '#fff' }]}>{d.name}</Text>
                      {d.owner ? (
                        <Text style={[st.owner, on && { color: '#ede9fe' }]}>→ {d.owner}</Text>
                      ) : null}
                    </Pressable>
                  );
                })}
              </View>
            ))}

            {pick ? (
              <View style={st.form}>
                <Text style={st.h3}>เปลี่ยนเป็น: {pick.name}</Text>

                <Text style={st.label}>
                  รูป / วิดีโอ {needMedia ? <Text style={{ color: C.red }}>(ต้องแนบ)</Text> : '(ถ้ามี)'}
                </Text>
                <View style={{ flexDirection: 'row', gap: 8 }}>
                  <Btn title="📷 ถ่ายรูป" small onPress={takePhoto} style={{ flex: 1 }} />
                  <Btn title="🖼 เลือกจากเครื่อง" small outline onPress={fromLibrary} style={{ flex: 1 }} />
                </View>
                {shots.length ? (
                  <View style={st.thumbs}>
                    {shots.map((s) => (
                      <View key={s.uri} style={st.thumbBox}>
                        {s.video ? (
                          <View style={[st.thumb, st.videoThumb]}>
                            <Text style={{ color: '#fff', fontSize: 22 }}>▶</Text>
                          </View>
                        ) : (
                          <Image source={{ uri: s.uri }} style={st.thumb} />
                        )}
                        <Text style={[st.thumbState, s.err ? { color: C.red } : s.id ? { color: C.green } : null]}>
                          {s.uploading ? 'กำลังอัป…' : s.err ? 'ไม่สำเร็จ' : 'อัปแล้ว'}
                        </Text>
                        <Pressable onPress={() => setShots((cur) => cur.filter((x) => x.uri !== s.uri))} hitSlop={8}>
                          <Text style={{ color: C.sub, fontSize: 12 }}>ลบ</Text>
                        </Pressable>
                      </View>
                    ))}
                  </View>
                ) : null}

                <Text style={st.label}>
                  หมายเหตุ {needNote ? <Text style={{ color: C.red }}>(ต้องใส่)</Text> : '(ถ้ามี)'}
                </Text>
                <TextInput
                  style={st.note}
                  value={note}
                  onChangeText={setNote}
                  placeholder="เช่น ซ่อมช่วงล่างเสร็จ / ปียาง 2023"
                  placeholderTextColor={C.sub}
                  multiline
                />

                {showChk ? (
                  <View style={{ gap: 6 }}>
                    <Text style={st.label}>เช็คลิสต์ตรวจรถ (ปิดข้อที่มีปัญหา)</Text>
                    {car.rules.checklistItems.map((i) => (
                      <View key={i} style={st.chkRow}>
                        <Text style={[st.chkText, !chk[i] && { color: C.red }]}>{i}</Text>
                        <Switch
                          value={!!chk[i]}
                          onValueChange={(v) => setChk((cur) => ({ ...cur, [i]: v }))}
                          trackColor={{ true: C.purple, false: '#f3b4b4' }}
                        />
                      </View>
                    ))}
                  </View>
                ) : null}

                {missing.length ? <Banner kind="warn" text={'ยังขาด: ' + missing.join(' และ ')} /> : null}
                <Btn title="ยืนยันเปลี่ยนสเตป" onPress={submit} busy={saving} disabled={busyUp || !!missing.length} />
                <Btn title="ยกเลิก" outline color={C.sub} small onPress={() => setPick(null)} />
              </View>
            ) : null}
          </Card>

          <Card style={{ gap: 12 }}>
            <Text style={st.h2}>ประวัติ</Text>
            {!car.logs.length ? <Text style={st.sub}>ยังไม่มีประวัติ</Text> : null}
            {car.logs.slice(0, 15).map((l, i) => (
              <View key={i} style={st.log}>
                <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: 8 }}>
                  <Text style={st.logStage}>{l.stage}</Text>
                  <Text style={st.logAt}>{l.at}</Text>
                </View>
                <Text style={st.sub}>
                  {l.worker || '-'}
                  {l.dur ? ` · ${l.cur ? 'อยู่มาแล้ว' : 'อยู่'} ${l.dur}` : ''}
                </Text>
                {l.note ? <Text style={st.logNote}>{l.note}</Text> : null}
                {l.media?.length ? (
                  <View style={st.thumbs}>
                    {l.media.slice(0, 8).map((m, j) => (
                      <Pressable key={j} onPress={() => Linking.openURL(absUrl(m.url))}>
                        {m.video ? (
                          <View style={[st.logThumb, st.videoThumb]}>
                            <Text style={{ color: '#fff' }}>▶</Text>
                          </View>
                        ) : (
                          <Image source={{ uri: absUrl(m.url) }} style={st.logThumb} />
                        )}
                      </Pressable>
                    ))}
                  </View>
                ) : null}
              </View>
            ))}
          </Card>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const st = StyleSheet.create({
  hero: { width: '100%', height: 190, borderRadius: 10, backgroundColor: C.purpleSoft },
  title: { fontSize: 20, fontWeight: '800', color: C.text },
  sub: { fontSize: 14, color: C.sub },
  h2: { fontSize: 18, fontWeight: '800', color: C.text },
  h3: { fontSize: 16, fontWeight: '700', color: C.purple },
  stageRow: { flexDirection: 'row', alignItems: 'center', gap: 10, flexWrap: 'wrap' },
  stagePill: { borderRadius: 8, paddingHorizontal: 12, paddingVertical: 6 },
  tags: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  phase: { fontSize: 13, fontWeight: '700', color: C.sub, marginTop: 4 },
  stageBtn: {
    minHeight: 50,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: C.line,
    borderLeftWidth: 6,
    paddingHorizontal: 14,
    paddingVertical: 10,
    backgroundColor: '#fff',
    justifyContent: 'center',
  },
  stageBtnOn: { backgroundColor: C.purple, borderColor: C.purple },
  stageBtnText: { fontSize: 16, fontWeight: '700', color: C.text },
  owner: { fontSize: 12, color: C.sub, marginTop: 2 },
  form: { gap: 10, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: C.line, paddingTop: 12 },
  label: { fontSize: 14, fontWeight: '700', color: C.text },
  note: {
    minHeight: 80,
    borderWidth: 1,
    borderColor: C.line,
    borderRadius: 8,
    padding: 12,
    fontSize: 16,
    color: C.text,
    backgroundColor: C.bg,
    textAlignVertical: 'top',
  },
  thumbs: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  thumbBox: { alignItems: 'center', gap: 2 },
  thumb: { width: 76, height: 76, borderRadius: 8, backgroundColor: C.purpleSoft },
  videoThumb: { backgroundColor: '#1f1147', alignItems: 'center', justifyContent: 'center' },
  thumbState: { fontSize: 11, color: C.sub },
  chkRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10, paddingVertical: 2 },
  chkText: { flex: 1, fontSize: 15, color: C.text },
  log: { gap: 3, borderLeftWidth: 3, borderLeftColor: C.purpleSoft, paddingLeft: 10 },
  logStage: { fontSize: 15, fontWeight: '700', color: C.text, flex: 1 },
  logAt: { fontSize: 12, color: C.sub },
  logNote: { fontSize: 14, color: C.text, lineHeight: 20 },
  logThumb: { width: 56, height: 56, borderRadius: 6, backgroundColor: C.purpleSoft },
});
