// งานกับลูกค้า 1 คน (หน้ารวมแชท) — ขั้นของลีด · นัดหมาย · บันทึกการโทร + รูปหลักฐาน · สรุปลูกค้า (AI ร่าง) · ใครเคยดูแล · คืนกองกลาง
// ใช้ API เดิมของเว็บทั้งหมด (/connect/api/chat · /connect/api/crm · /connect/api/upload) — สิทธิ์เซิร์ฟเวอร์ตัดสิน
import * as ImagePicker from 'expo-image-picker';
import { router, Stack, useFocusEffect, useLocalSearchParams } from 'expo-router';
import { useCallback, useMemo, useState } from 'react';
import {
  Alert,
  Image,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';

import { absUrl, api } from '../../lib/api';
import { Extra, fmtFull, HEAT, localDT, STAGE_COLOR } from '../../lib/crm';
import { Banner, Btn, C, Card, Loading } from '../../lib/ui';

type KV = { key: string; label: string };
type Followup = {
  id: number;
  kind: string;
  kindLabel: string;
  due: string;
  note: string;
  who: string;
  done: string;
  doneBy: string;
  result: string;
  late: boolean;
};
type Call = { id: number; at: string; resultLabel: string; note: string; by: string; media: { url: string }[] };
type Crm = {
  stages: KV[];
  lostReasons: string[];
  callResults: KV[];
  extra: Extra;
  stageBy: string;
  stageAt: string;
  summary: string;
  summaryAt: string;
  summaryBy: string;
  followups: Followup[];
  calls: Call[];
  pastOwners: { name: string; from: string; to: string; end: string; how: string; by: string }[];
  booking: { status: string; car: string; date: string; resultDate: string; releaseDate: string; price: number } | null;
  cars: { code: string; name: string; price: number; year: number }[];
  aiOn: boolean;
};
type ChatResp = {
  row: { id: number; name: string; owner: string };
  access: string;
  leadEditable?: boolean;
  canRelease?: boolean;
  crm?: Crm;
  crmError?: string;
};
type Draft = {
  summary: string;
  stage: string;
  stageLabel: string;
  stageReason: string;
  followAt: string;
  followNote: string;
};
type Shot = { uri: string; id?: string; uploading: boolean; err?: string };

const TIMES = ['09:00', '10:00', '11:00', '13:00', '14:00', '15:00', '16:00', '17:00', '18:00'];
const DOW = ['อา.', 'จ.', 'อ.', 'พ.', 'พฤ.', 'ศ.', 'ส.'];
const money = (n: number) => (n ? '฿' + Number(n).toLocaleString() : '');

export default function LeadScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const rid = Number(id);
  const [d, setD] = useState<ChatResp | null>(null);
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState('');
  const [lostOpen, setLostOpen] = useState(false);
  const [kind, setKind] = useState<'follow' | 'viewing'>('follow');
  const [day, setDay] = useState(1);
  const [time, setTime] = useState('10:00');
  const [apptNote, setApptNote] = useState('');
  const [callRes, setCallRes] = useState('');
  const [callNote, setCallNote] = useState('');
  const [shots, setShots] = useState<Shot[]>([]);
  const [sum, setSum] = useState<string | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [why, setWhy] = useState('');

  const load = useCallback(async () => {
    try {
      setD(await api<ChatResp>(`/connect/api/chat?id=${rid}`));
      setErr('');
    } catch (e: any) {
      setErr(e?.message || 'โหลดไม่สำเร็จ');
    }
  }, [rid]);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load]),
  );

  const days = useMemo(() => {
    const out: { i: number; label: string }[] = [];
    for (let i = 0; i < 14; i++) {
      const x = new Date();
      x.setDate(x.getDate() + i);
      out.push({ i, label: i === 0 ? 'วันนี้' : i === 1 ? 'พรุ่งนี้' : `${DOW[x.getDay()]} ${x.getDate()}/${x.getMonth() + 1}` });
    }
    return out;
  }, []);

  const act = async (action: string, extra: Record<string, unknown> = {}, key = action) => {
    setBusy(key);
    try {
      const r = await api<{ crm?: Crm; message?: string }>('/connect/api/crm', { body: { action, id: rid, ...extra } });
      if (r.crm) setD((cur) => (cur ? { ...cur, crm: r.crm } : cur));
      return r;
    } catch (e: any) {
      Alert.alert('ทำไม่สำเร็จ', e?.message || '');
      return null;
    } finally {
      setBusy('');
    }
  };

  const upload = async (a: ImagePicker.ImagePickerAsset) => {
    setShots((cur) => [...cur, { uri: a.uri, uploading: true }]);
    const form = new FormData();
    form.append('id', String(rid));
    form.append('file', { uri: a.uri, name: a.fileName || `call-${Date.now()}.jpg`, type: a.mimeType || 'image/jpeg' } as any);
    try {
      const r = await api<{ id: string }>('/connect/api/upload', { form, timeoutMs: 120000 });
      setShots((cur) => cur.map((s) => (s.uri === a.uri ? { ...s, id: r.id, uploading: false } : s)));
    } catch (e: any) {
      setShots((cur) => cur.map((s) => (s.uri === a.uri ? { ...s, err: e?.message || 'อัปไม่สำเร็จ', uploading: false } : s)));
    }
  };
  const pick = async (camera: boolean) => {
    if (camera) {
      const p = await ImagePicker.requestCameraPermissionsAsync();
      if (!p.granted) {
        Alert.alert('ต้องอนุญาตใช้กล้องก่อน');
        return;
      }
    }
    const r = camera
      ? await ImagePicker.launchCameraAsync({ mediaTypes: ['images'], quality: 0.6 })
      : await ImagePicker.launchImageLibraryAsync({ mediaTypes: ['images'], allowsMultipleSelection: true, selectionLimit: 6, quality: 0.6 });
    if (!r.canceled) r.assets.slice(0, 6 - shots.length).forEach(upload);
  };

  const release = () =>
    Alert.alert('คืนกองกลาง?', 'ลูกค้ากลับเข้าคิวรอรับ ให้เซลล์คนอื่นรับต่อ (จดประวัติว่าใครคืน เพราะอะไร)', [
      { text: 'ยกเลิก', style: 'cancel' },
      {
        text: 'คืนกองกลาง',
        style: 'destructive',
        onPress: async () => {
          const r = await act('release', { reason: why });
          if (r) {
            Alert.alert('คืนกองกลางแล้ว');
            if (router.canDismiss()) router.dismissAll();
          }
        },
      },
    ]);

  if (err && !d) {
    return (
      <View style={{ padding: 16, gap: 12 }}>
        <Banner text={err} kind="err" />
        <Btn title="ลองใหม่" onPress={load} />
      </View>
    );
  }
  if (!d) return <Loading />;
  const K = d.crm;
  const ed = !!d.leadEditable;
  const E = K?.extra || {};
  const busyUp = shots.some((s) => s.uploading);

  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined} keyboardVerticalOffset={90}>
      <Stack.Screen options={{ title: d.row.name || 'งานกับลูกค้า' }} />
      <ScrollView contentContainerStyle={{ padding: 12, gap: 12, paddingBottom: 60 }} keyboardShouldPersistTaps="handled">
        {!K ? (
          <Banner kind="info" text={d.crmError || 'กด "รับลูกค้า" ในหน้าแชทก่อน ถึงจะบันทึกงานกับลูกค้าคนนี้ได้'} />
        ) : (
          <>
            {/* ── ขั้นของลีด ── */}
            <Card style={{ gap: 10 }}>
              <View style={st.hRow}>
                <Text style={st.h}>ขั้นของลีด</Text>
                {E.heat ? (
                  <Text style={[st.heat, { color: HEAT[E.heat][1], backgroundColor: HEAT[E.heat][2] }]}>
                    {HEAT[E.heat][0]} {E.heatScore}
                  </Text>
                ) : null}
              </View>
              <View style={st.wrap}>
                {K.stages.map((s) => {
                  const on = E.stage === s.key;
                  const [fg, bg] = STAGE_COLOR[s.key] || [C.purple, C.purpleSoft];
                  return (
                    <Pressable
                      key={s.key}
                      disabled={!ed || !!busy}
                      onPress={() => (s.key === 'lost' ? setLostOpen(true) : act('stage', { stage: s.key }, 'stage'))}
                      style={[st.chip, on ? { backgroundColor: C.purple, borderColor: C.purple } : { backgroundColor: bg, borderColor: bg }]}>
                      <Text style={[st.chipT, { color: on ? '#fff' : fg }]}>{s.label}</Text>
                    </Pressable>
                  );
                })}
              </View>
              <Text style={st.sub}>
                ตอนนี้: <Text style={{ fontWeight: '700', color: C.text }}>{E.stageLabel}</Text>
                {E.stage === 'lost' && E.lostReason ? ` · ${E.lostReason}` : ''}
                {K.stageBy ? ` · ตั้งโดย ${K.stageBy} ${fmtFull(K.stageAt)}` : ' · ระบบคิดให้ (จากการรับ/ตอบลูกค้า)'}
              </Text>
              {lostOpen ? (
                <View style={{ gap: 8 }}>
                  <Text style={st.sub}>ไม่ซื้อเพราะอะไร (ใช้วิเคราะห์)</Text>
                  <View style={st.wrap}>
                    {K.lostReasons.map((x) => (
                      <Pressable
                        key={x}
                        onPress={async () => {
                          const r = await act('stage', { stage: 'lost', reason: x }, 'stage');
                          if (r) setLostOpen(false);
                        }}
                        style={[st.chip, { borderColor: C.line, backgroundColor: '#fff' }]}>
                        <Text style={st.chipT}>{x}</Text>
                      </Pressable>
                    ))}
                  </View>
                  <Btn small outline title="ยกเลิก" onPress={() => setLostOpen(false)} />
                </View>
              ) : null}
              {E.heatWhy?.length ? <Text style={st.sub}>ความร้อน: {E.heatWhy.join(' · ')}</Text> : null}
              {K.booking ? (
                <Text style={[st.box, { backgroundColor: C.greenBg, color: C.text }]}>
                  ชีตยอดขาย: <Text style={{ fontWeight: '700' }}>{K.booking.status}</Text>
                  {K.booking.car ? ` · ${K.booking.car}` : ''}
                  {K.booking.date ? ` · จอง ${K.booking.date}` : ''}
                  {K.booking.resultDate ? ` · ผล ${K.booking.resultDate}` : ''}
                  {K.booking.releaseDate ? ` · ปล่อย ${K.booking.releaseDate}` : ''}
                  {K.booking.price ? ` · ${money(K.booking.price)}` : ''}
                </Text>
              ) : null}
              {K.cars.length ? (
                <Text style={[st.box, { backgroundColor: C.greenBg, color: C.green }]}>
                  รถพร้อมขายที่ตรงกับลูกค้า: {K.cars.map((c) => `${c.name || c.code}${c.year ? ' ' + c.year : ''} ${money(c.price)}`).join(' · ')}
                </Text>
              ) : null}
            </Card>

            {/* ── นัดหมาย ── */}
            <Card style={{ gap: 10 }}>
              <Text style={st.h}>นัดหมาย</Text>
              {K.followups.length === 0 ? <Text style={st.sub}>ยังไม่มีนัด</Text> : null}
              {K.followups.map((f) => (
                <View key={f.id} style={[st.item, f.late && !f.done && { borderColor: C.red, backgroundColor: C.redBg }, f.done ? { opacity: 0.65 } : null]}>
                  <Text style={st.itemT}>
                    <Text style={{ fontWeight: '700' }}>{f.kindLabel}</Text> {fmtFull(f.due)}
                    {f.who ? ` · @${f.who}` : ''}
                    {f.done ? ` · ${f.result || 'ทำแล้ว'}` : f.late ? ' · เลยนัดแล้ว' : ''}
                  </Text>
                  {f.note ? <Text style={st.sub}>{f.note}</Text> : null}
                  {!f.done && ed ? (
                    <View style={{ flexDirection: 'row', gap: 8, marginTop: 6 }}>
                      <Btn small title="ทำแล้ว" busy={busy === 'f' + f.id} onPress={() => act('followup_done', { fid: f.id }, 'f' + f.id)} />
                      <Btn small outline title="ยกเลิกนัด" onPress={() => act('followup_done', { fid: f.id, cancel: true }, 'f' + f.id)} />
                    </View>
                  ) : null}
                </View>
              ))}
              {ed ? (
                <View style={{ gap: 8 }}>
                  <View style={st.wrap}>
                    {(['follow', 'viewing'] as const).map((k) => (
                      <Pressable key={k} onPress={() => setKind(k)} style={[st.chip, kind === k ? st.chipOn : st.chipOff]}>
                        <Text style={[st.chipT, kind === k && { color: '#fff' }]}>{k === 'follow' ? 'นัดติดตาม' : 'นัดดูรถ'}</Text>
                      </Pressable>
                    ))}
                  </View>
                  <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 6 }}>
                    {days.map((x) => (
                      <Pressable key={x.i} onPress={() => setDay(x.i)} style={[st.chip, day === x.i ? st.chipOn : st.chipOff]}>
                        <Text style={[st.chipT, day === x.i && { color: '#fff' }]}>{x.label}</Text>
                      </Pressable>
                    ))}
                  </ScrollView>
                  <View style={st.wrap}>
                    {TIMES.map((t) => (
                      <Pressable key={t} onPress={() => setTime(t)} style={[st.chip, time === t ? st.chipOn : st.chipOff]}>
                        <Text style={[st.chipT, time === t && { color: '#fff' }]}>{t}</Text>
                      </Pressable>
                    ))}
                  </View>
                  <TextInput style={st.input} value={apptNote} onChangeText={setApptNote} placeholder="รายละเอียด (ไม่บังคับ)" placeholderTextColor={C.sub} maxLength={300} />
                  <Btn
                    title={kind === 'viewing' ? 'บันทึกนัดดูรถ' : 'บันทึกนัดติดตาม'}
                    busy={busy === 'appt'}
                    onPress={async () => {
                      const x = new Date();
                      x.setDate(x.getDate() + day);
                      const [hh, mm] = time.split(':').map(Number);
                      x.setHours(hh, mm, 0, 0);
                      const r = await act('followup', { kind, due: localDT(x), note: apptNote }, 'appt');
                      if (r) setApptNote('');
                    }}
                  />
                </View>
              ) : null}
            </Card>

            {/* ── บันทึกการโทร ── */}
            <Card style={{ gap: 10 }}>
              <Text style={st.h}>บันทึกการโทร</Text>
              {K.calls.length === 0 ? <Text style={st.sub}>ยังไม่มีบันทึกการโทร</Text> : null}
              {K.calls.slice(0, 6).map((c) => (
                <View key={c.id} style={st.item}>
                  <Text style={st.itemT}>
                    <Text style={{ fontWeight: '700' }}>{c.resultLabel}</Text> · {fmtFull(c.at)}
                    {c.by ? ` · ${c.by}` : ''}
                  </Text>
                  {c.note ? <Text style={st.sub}>{c.note}</Text> : null}
                  {c.media.length ? (
                    <View style={[st.wrap, { marginTop: 6 }]}>
                      {c.media.map((m, i) => (
                        <Image key={i} source={{ uri: absUrl(m.url) }} style={st.thumb} />
                      ))}
                    </View>
                  ) : null}
                </View>
              ))}
              {ed ? (
                <View style={{ gap: 8 }}>
                  <View style={st.wrap}>
                    {K.callResults.map((r) => (
                      <Pressable key={r.key} onPress={() => setCallRes(r.key)} style={[st.chip, callRes === r.key ? st.chipOn : st.chipOff]}>
                        <Text style={[st.chipT, callRes === r.key && { color: '#fff' }]}>{r.label}</Text>
                      </Pressable>
                    ))}
                  </View>
                  <TextInput style={st.input} value={callNote} onChangeText={setCallNote} placeholder="หมายเหตุ เช่น นัดโทรกลับหลัง 5 โมง" placeholderTextColor={C.sub} maxLength={500} />
                  {shots.length ? (
                    <View style={st.wrap}>
                      {shots.map((s) => (
                        <View key={s.uri} style={{ alignItems: 'center' }}>
                          <Image source={{ uri: s.uri }} style={st.thumb} />
                          <Text style={{ fontSize: 10, color: s.err ? C.red : C.sub }}>{s.uploading ? 'กำลังอัป…' : s.err ? 'ไม่สำเร็จ' : 'อัปแล้ว'}</Text>
                        </View>
                      ))}
                    </View>
                  ) : null}
                  <View style={{ flexDirection: 'row', gap: 8 }}>
                    <Btn small outline title="ถ่ายรูปหลักฐาน" onPress={() => pick(true)} style={{ flex: 1 }} />
                    <Btn small outline title="เลือกรูป" onPress={() => pick(false)} style={{ flex: 1 }} />
                  </View>
                  <Btn
                    title="บันทึกการโทร"
                    busy={busy === 'call'}
                    disabled={!callRes || busyUp}
                    onPress={async () => {
                      const media = shots.filter((s) => s.id).map((s) => ({ id: s.id }));
                      const r = await act('call', { result: callRes, note: callNote, media }, 'call');
                      if (r) {
                        setCallRes('');
                        setCallNote('');
                        setShots([]);
                      }
                    }}
                  />
                </View>
              ) : null}
            </Card>

            {/* ── สรุปลูกค้า (AI ร่าง · ตรวจก่อนบันทึก) ── */}
            <Card style={{ gap: 10 }}>
              <Text style={st.h}>สรุปลูกค้า</Text>
              {draft ? (
                <View style={[st.box, { backgroundColor: C.purpleSoft, gap: 6 }]}>
                  <Text style={{ fontWeight: '700', color: C.purple }}>AI ร่างให้ — ตรวจก่อนบันทึก</Text>
                  {draft.stage ? (
                    <Text style={st.itemT}>
                      ขั้นที่แนะนำ: <Text style={{ fontWeight: '700' }}>{draft.stageLabel}</Text>
                      {draft.stageReason ? ` — ${draft.stageReason}` : ''}
                    </Text>
                  ) : null}
                  {draft.followAt ? (
                    <Text style={st.itemT}>
                      ควรติดตาม: <Text style={{ fontWeight: '700' }}>{fmtFull(draft.followAt)}</Text>
                      {draft.followNote ? ` — ${draft.followNote}` : ''}
                    </Text>
                  ) : null}
                  <View style={[st.wrap, { marginTop: 4 }]}>
                    {draft.stage && ed ? (
                      <Btn small outline title="ใช้ขั้นนี้" onPress={() => (draft.stage === 'lost' ? setLostOpen(true) : act('stage', { stage: draft.stage }, 'stage'))} />
                    ) : null}
                    {draft.followAt && ed ? (
                      <Btn
                        small
                        outline
                        title="สร้างนัดติดตามนี้"
                        onPress={async () => {
                          const r = await act('followup', { kind: 'follow', due: draft.followAt, note: draft.followNote }, 'appt');
                          if (r) setDraft({ ...draft, followAt: '' });
                        }}
                      />
                    ) : null}
                    <Btn small outline title="ปิดคำแนะนำ" onPress={() => setDraft(null)} />
                  </View>
                </View>
              ) : null}
              {ed ? (
                <>
                  <TextInput
                    style={[st.input, { minHeight: 96, textAlignVertical: 'top' }]}
                    value={sum ?? K.summary}
                    onChangeText={setSum}
                    multiline
                    maxLength={2000}
                    placeholder="ลูกค้าต้องการรถอะไร งบ/ผ่อน/ดาวน์ ข้อกังวล ทำอะไรค้างไว้"
                    placeholderTextColor={C.sub}
                  />
                  <View style={{ flexDirection: 'row', gap: 8 }}>
                    {K.aiOn ? (
                      <Btn
                        small
                        outline
                        style={{ flex: 1 }}
                        title="ให้ AI ร่างจากแชท"
                        busy={busy === 'ai'}
                        onPress={async () => {
                          setBusy('ai');
                          try {
                            const r = await api<{ draft: Draft }>('/connect/api/crm', { body: { action: 'ai', id: rid }, timeoutMs: 90000 });
                            setDraft(r.draft);
                            if (r.draft.summary) setSum(r.draft.summary); // ใส่ในช่องให้ตรวจ/แก้ — ยังไม่บันทึก
                          } catch (e: any) {
                            Alert.alert('AI สรุปไม่สำเร็จ', e?.message || '');
                          } finally {
                            setBusy('');
                          }
                        }}
                      />
                    ) : null}
                    <Btn
                      small
                      style={{ flex: 1 }}
                      title="บันทึกสรุป"
                      busy={busy === 'sum'}
                      onPress={async () => {
                        const r = await act('summary', { text: sum ?? K.summary }, 'sum');
                        if (r) setSum(null);
                      }}
                    />
                  </View>
                  <Text style={st.sub}>
                    {K.summaryAt ? `บันทึกล่าสุด ${fmtFull(K.summaryAt)}${K.summaryBy ? ' โดย ' + K.summaryBy : ''} · ` : ''}
                    {K.aiOn ? 'AI แค่ร่าง — ปิดบังเบอร์/ไอดีก่อนส่งให้ AI · ต้องกดบันทึกเอง' : 'ยังไม่ได้ตั้งคีย์ AI — พิมพ์สรุปเองได้'}
                  </Text>
                </>
              ) : (
                <Text style={st.itemT}>{K.summary || 'ยังไม่มีสรุป'}</Text>
              )}
            </Card>

            {/* ── ใครเคยดูแล ── */}
            {K.pastOwners.length ? (
              <Card style={{ gap: 6 }}>
                <Text style={st.h}>ใครเคยดูแลลูกค้าคนนี้</Text>
                {K.pastOwners.map((o, i) => (
                  <Text key={i} style={st.itemT}>
                    <Text style={{ fontWeight: '700' }}>@{o.name}</Text> {fmtFull(o.from)} → {o.to ? `${fmtFull(o.to)} · ${o.end}` : 'ตอนนี้'}
                    {'\n'}
                    <Text style={st.sub}>{o.how}</Text>
                  </Text>
                ))}
              </Card>
            ) : null}

            {/* ── คืนกองกลาง (เจ้าของลูกค้า) ── */}
            {d.canRelease ? (
              <Card style={{ gap: 8 }}>
                <Text style={st.h}>คืนกองกลาง</Text>
                <Text style={st.sub}>ลูกค้ากลับเข้าคิวรอรับ ให้เซลล์คนอื่นรับต่อ</Text>
                <TextInput style={st.input} value={why} onChangeText={setWhy} placeholder="เหตุผล (ไม่บังคับ) เช่น ลูกค้าอยู่ต่างจังหวัด" placeholderTextColor={C.sub} maxLength={150} />
                <Btn title="คืนกองกลาง" color={C.red} busy={busy === 'release'} onPress={release} />
              </Card>
            ) : null}
          </>
        )}
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const st = StyleSheet.create({
  h: { fontSize: 16, fontWeight: '800', color: C.text },
  hRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  heat: { fontSize: 12, fontWeight: '800', paddingHorizontal: 7, paddingVertical: 2, borderRadius: 5, overflow: 'hidden' },
  sub: { fontSize: 13, color: C.sub, lineHeight: 19 },
  wrap: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  chip: { paddingHorizontal: 11, paddingVertical: 7, borderRadius: 7, borderWidth: 1 },
  chipOn: { backgroundColor: C.purple, borderColor: C.purple },
  chipOff: { backgroundColor: '#fff', borderColor: C.line },
  chipT: { fontSize: 13, fontWeight: '700', color: C.text },
  box: { borderRadius: 8, padding: 10, fontSize: 13, lineHeight: 19 },
  item: { borderWidth: StyleSheet.hairlineWidth, borderColor: C.line, borderRadius: 8, padding: 10, backgroundColor: '#fff' },
  itemT: { fontSize: 14, color: C.text, lineHeight: 20 },
  input: {
    minHeight: 42,
    borderWidth: 1,
    borderColor: C.line,
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 9,
    fontSize: 15,
    color: C.text,
    backgroundColor: C.bg,
  },
  thumb: { width: 60, height: 60, borderRadius: 6, backgroundColor: '#eee' },
});
