// ความด่วน + ธงงานค้าง ของรถ 1 คัน (★ 13 ต.ค.69 · เดิมตั้งได้แค่ในหน้าเว็บ)
// ยิง API เดิมของเว็บ: /track/api/set_priority · /track/api/set_flags
// สิทธิ์มาจากเซิร์ฟเวอร์ (canPriority / flagPerms) และเซิร์ฟเวอร์ตรวจซ้ำอีกชั้นเสมอ
//   ความด่วน = เฉพาะสเตปช่วงรับเข้า-ทำสภาพ (showPriority) · ฝ่ายล้างรถดูได้อย่างเดียว
//   ธง = แยกสิทธิ์รายช่อง (รูป/คอนเทนต์ = โปรดักชัน · ยาง = ช่าง+ทะเบียน · ผู้บริหารได้ทุกช่อง)
//   ปลดธง "ยังไม่ได้ถ่ายรูป" = ประกาศว่าถ่ายเสร็จ → ต้องแนบรูป + หมายเหตุ (เก็บลงประวัติรถ)
import { useState } from 'react';
import { Alert, Pressable, StyleSheet, Switch, Text, TextInput, View } from 'react-native';

import { api } from './api';
import { MediaPicker, useUploads } from './media';
import { Banner, Btn, C, Card } from './ui';

export type FlagDef = { key: string; name: string; color: string; proof: boolean; done: string };
export type Marks = {
  code: string;
  priority: string;
  showPriority: boolean;
  canPriority: boolean;
  flagPerms: Record<string, boolean>;
  needPhoto: boolean;
  needContent: boolean;
  needTire: boolean;
  priorities?: { key: string; name: string; color: string }[];
  flagDefs?: FlagDef[];
};

const FIELD: Record<string, 'needPhoto' | 'needContent' | 'needTire'> = {
  need_photo: 'needPhoto',
  need_content: 'needContent',
  need_tire: 'needTire',
};

export function CarMarks({ car, onDone }: { car: Marks; onDone: () => Promise<void> | void }) {
  const [busy, setBusy] = useState('');
  const [proof, setProof] = useState<FlagDef | null>(null);
  const [note, setNote] = useState('');
  const u = useUploads(car.code);
  const prios = car.priorities || [];
  const defs = car.flagDefs || [];
  if (!prios.length && !defs.length) return null; // เซิร์ฟเวอร์รุ่นเก่ายังไม่ส่งรายการมา
  const anyFlagPerm = defs.some((f) => car.flagPerms?.[f.key]);

  const setPriority = async (key: string) => {
    if (busy || key === car.priority) return;
    setBusy('p:' + key);
    try {
      await api('/track/api/set_priority', { body: { code: car.code, priority: key } });
      await onDone();
    } catch (e: any) {
      Alert.alert('ตั้งความด่วนไม่สำเร็จ', e?.message || '');
    } finally {
      setBusy('');
    }
  };

  const sendFlag = async (f: FlagDef, on: boolean, extra?: { note: string; media: { id: string; video: boolean }[] }) => {
    setBusy('f:' + f.key);
    try {
      await api('/track/api/set_flags', { body: { code: car.code, [f.key]: on, ...(extra || {}) } });
      setProof(null);
      setNote('');
      u.clear();
      await onDone();
      if (extra) Alert.alert('บันทึกแล้ว', `${f.done || 'งานเสร็จแล้ว'} — เก็บรูปลงประวัติรถให้แล้ว`);
    } catch (e: any) {
      Alert.alert('บันทึกไม่สำเร็จ', e?.message || '');
    } finally {
      setBusy('');
    }
  };

  const toggle = (f: FlagDef, v: boolean) => {
    const cur = !!car[FIELD[f.key]];
    if (!v && cur && f.proof) {
      // ปลดธงนี้ต้องมีหลักฐาน — เปิดฟอร์มแนบรูปก่อน (สวิตช์ยังติดอยู่จนกว่าจะยืนยัน)
      setProof(f);
      setNote('');
      u.clear();
      return;
    }
    sendFlag(f, v);
  };

  const proofMissing: string[] = [];
  if (proof) {
    if (!u.ready.length) proofMissing.push('แนบรูปที่ถ่ายแล้ว');
    if (!note.trim()) proofMissing.push('ใส่หมายเหตุ');
  }

  return (
    <Card style={{ gap: 12 }}>
      {car.showPriority && prios.length ? (
        <View style={{ gap: 8 }}>
          <Text style={st.h2}>ความด่วน</Text>
          <View style={st.chips}>
            {prios.map((p) => {
              const on = p.key === car.priority;
              const light = p.key === 'low' || p.key === 'normal'; // สีอ่อน ตัวหนังสือดำอ่านง่ายกว่า
              return (
                <Pressable
                  key={p.key}
                  disabled={!car.canPriority || !!busy}
                  onPress={() => setPriority(p.key)}
                  style={({ pressed }) => [
                    st.chip,
                    { borderColor: p.color || C.line },
                    on && { backgroundColor: p.color || C.purple },
                    !car.canPriority && !on && { opacity: 0.45 },
                    pressed && { opacity: 0.7 },
                  ]}>
                  <Text style={[st.chipT, on && { color: light ? C.text : '#fff' }]}>
                    {busy === 'p:' + p.key ? '…' : p.name}
                  </Text>
                </Pressable>
              );
            })}
          </View>
          {!car.canPriority ? <Text style={st.sub}>บทบาทนี้ดูความด่วนได้อย่างเดียว</Text> : null}
        </View>
      ) : null}

      {defs.length ? (
        <View style={{ gap: 6 }}>
          <Text style={st.h2}>งานค้าง (ธง)</Text>
          <Text style={st.sub}>ติดธงแล้วรถยังย้ายสเตปได้ตามปกติ ธงติดตามรถไปจนกว่าจะเอาออก</Text>
          {defs.map((f) => {
            const can = !!car.flagPerms?.[f.key];
            const val = !!car[FIELD[f.key]];
            return (
              <View key={f.key} style={{ gap: 8 }}>
                <View style={st.flagRow}>
                  <View style={[st.dot, { backgroundColor: f.color }]} />
                  <Text style={[st.flagT, !can && { color: C.sub }]}>{f.name}</Text>
                  <Switch
                    value={proof?.key === f.key ? true : val}
                    disabled={!can || !!busy}
                    onValueChange={(v) => toggle(f, v)}
                    trackColor={{ true: f.color, false: '#d6d3e0' }}
                  />
                </View>
                {proof?.key === f.key ? (
                  <View style={st.proof}>
                    <Text style={st.h3}>เอาติ๊กออก = {f.done || 'งานเสร็จแล้ว'}</Text>
                    <Text style={st.sub}>แนบรูปที่ถ่ายแล้ว + หมายเหตุ — ระบบเก็บลงประวัติรถให้</Text>
                    <MediaPicker u={u} />
                    <TextInput
                      style={st.note}
                      value={note}
                      onChangeText={setNote}
                      placeholder="เช่น ถ่ายครบรอบคันแล้ว"
                      placeholderTextColor={C.sub}
                      multiline
                    />
                    {proofMissing.length ? <Banner kind="warn" text={'ยังขาด: ' + proofMissing.join(' และ ')} /> : null}
                    <Btn
                      title="ยืนยัน"
                      busy={busy === 'f:' + f.key}
                      disabled={u.busy || !!proofMissing.length}
                      onPress={() => sendFlag(f, false, { note: note.trim(), media: u.media })}
                    />
                    <Btn title="ยกเลิก (ยังติดธงไว้)" outline small color={C.sub} onPress={() => setProof(null)} />
                  </View>
                ) : null}
              </View>
            );
          })}
          {!anyFlagPerm ? <Text style={st.sub}>บทบาทนี้ดูธงได้อย่างเดียว — ทีมที่ดูแลงานนั้นเป็นคนติ๊ก</Text> : null}
        </View>
      ) : null}
    </Card>
  );
}

const st = StyleSheet.create({
  h2: { fontSize: 18, fontWeight: '800', color: C.text },
  h3: { fontSize: 15, fontWeight: '700', color: C.purple },
  sub: { fontSize: 13, color: C.sub, lineHeight: 19 },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip: {
    minHeight: 44, minWidth: 72, paddingHorizontal: 14, borderRadius: 8, borderWidth: 2,
    alignItems: 'center', justifyContent: 'center', backgroundColor: '#fff',
  },
  chipT: { fontSize: 15, fontWeight: '700', color: C.text },
  flagRow: { flexDirection: 'row', alignItems: 'center', gap: 10, minHeight: 44 },
  dot: { width: 12, height: 12, borderRadius: 6 },
  flagT: { flex: 1, fontSize: 16, color: C.text },
  proof: { gap: 10, padding: 12, borderRadius: 10, backgroundColor: C.bg },
  note: {
    minHeight: 70, borderWidth: 1, borderColor: C.line, borderRadius: 8, padding: 12, fontSize: 16,
    color: C.text, backgroundColor: '#fff', textAlignVertical: 'top',
  },
});
