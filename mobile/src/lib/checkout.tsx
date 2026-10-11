// เบิก-คืนรถ ในหน้ารถของแอป — ทำแบบเดียวกับหน้าสแกน QR ของเว็บ (ปุ่มเบิก/คืน สลับตามสถานะจริง)
// ยิง API เดิม: POST /checkout/api/car_out · car_return — เซิร์ฟเวอร์ตรวจจำนวนรูปขั้นต่ำซ้ำอีกชั้น
// ติ๊กมุมที่ถ่ายไม่ครบ = ยังบันทึกได้ (ระบบจดว่าขาดมุมไหน ให้หัวหน้าเห็น) — กติกาเดียวกับเว็บ
import { useState } from 'react';
import { Alert, Pressable, StyleSheet, Switch, Text, TextInput, View } from 'react-native';

import { api } from './api';
import { MediaPicker, useUploads } from './media';
import { Banner, Btn, C, Card } from './ui';

export type CkInfo = {
  open: {
    who: string;
    mine: boolean;
    purpose: string;
    destination: string;
    since: string;
    hours: number;
    fuel: boolean;
  } | null;
  purposes: { key: string; name: string }[];
  outMin: number;
  inMin: number;
  outItems: string[];
  inItems: string[];
  shotsOut: { key: string; name: string }[];
  shotsIn: { key: string; name: string }[];
  overdueHours: number;
};

const pad = (n: number) => String(n).padStart(2, '0');
function hm(iso: string): string {
  const d = new Date(iso);
  return isNaN(d.getTime()) ? '' : `${d.getDate()}/${d.getMonth() + 1} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function CheckoutCard({ code, info, onDone }: { code: string; info: CkInfo; onDone: () => void }) {
  const open = info.open;
  const mode: 'out' | 'in' = open ? 'in' : 'out';
  const [form, setForm] = useState(false);
  const u = useUploads(code);
  const [purpose, setPurpose] = useState('');
  const [dest, setDest] = useState('');
  const [odo, setOdo] = useState('');
  const [fuel, setFuel] = useState(false);
  const [damage, setDamage] = useState(false);
  const [note, setNote] = useState('');
  const [sel, setSel] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);

  const angles = mode === 'out' ? info.shotsOut : info.shotsIn;
  const minPhotos = mode === 'out' ? info.outMin : info.inMin;
  const items = mode === 'out' ? info.outItems : info.inItems;
  const late = !!open && open.hours >= info.overdueHours;

  const reset = () => {
    setForm(false);
    u.clear();
    setPurpose('');
    setDest('');
    setOdo('');
    setFuel(false);
    setDamage(false);
    setNote('');
    setSel([]);
  };

  const start = () => {
    if (open && !open.mine) {
      Alert.alert('คืนรถแทนคนอื่น?', `รถคันนี้ ${open.who} เป็นคนเบิกออกไป`, [
        { text: 'ยกเลิก', style: 'cancel' },
        { text: 'คืนรถแทน', onPress: () => setForm(true) },
      ]);
      return;
    }
    setForm(true);
  };

  const missing: string[] = [];
  if (mode === 'out' && !purpose) missing.push('เลือกประเภทงาน');
  if (u.ready.length < minPhotos) missing.push(`แนบรูปอีก ${minPhotos - u.ready.length} รูป`);
  const lackAngles = angles.filter((a) => !sel.includes(a.key)).length;

  const submit = async () => {
    if (u.busy) {
      Alert.alert('รอรูปอัปโหลดให้เสร็จก่อน');
      return;
    }
    if (missing.length) {
      Alert.alert('ยังขาด', missing.join(' และ '));
      return;
    }
    setSaving(true);
    try {
      if (mode === 'out') {
        await api('/checkout/api/car_out', {
          body: { code, purpose, destination: dest.trim(), odo_out: odo.trim(), fuel, note: note.trim(), media: u.media, shots: sel },
        });
      } else {
        await api('/checkout/api/car_return', {
          body: { code, odo_in: odo.trim(), damage, note: note.trim(), media: u.media, shots: sel },
        });
      }
      reset();
      onDone();
      Alert.alert('บันทึกแล้ว', mode === 'out' ? 'เบิกรถเรียบร้อย — อย่าลืมคืนในระบบตอนเอารถกลับ' : 'คืนรถเรียบร้อย');
    } catch (e: any) {
      Alert.alert(mode === 'out' ? 'เบิกรถไม่สำเร็จ' : 'คืนรถไม่สำเร็จ', e?.message || '');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card style={{ gap: 12 }}>
      <Text style={st.h2}>เบิก-คืนรถ</Text>
      {open ? (
        <Banner
          kind={late ? 'err' : 'warn'}
          text={`🚗 ออกนอกลาน — ${open.who}${open.mine ? ' (คุณ)' : ''} · ${open.purpose || '-'}` +
            `${open.destination ? ' · ' + open.destination : ''}\nเบิกเมื่อ ${hm(open.since)} · ${open.hours} ชม.` +
            `${late ? ` (เกิน ${info.overdueHours} ชม.)` : ''}${open.fuel ? ' · ขอเบิกน้ำมัน' : ''}`}
        />
      ) : (
        <Text style={st.sub}>รถอยู่ที่ลาน — กดเบิกเมื่อจะเอารถออก (ตรวจขนส่ง / เข้าศูนย์ / ส่งลูกค้า …)</Text>
      )}

      {!form ? (
        <Btn
          title={open ? (open.mine ? 'คืนรถ' : `คืนรถแทน ${open.who}`) : 'เบิกรถออกนอกลาน'}
          color={open ? C.green : C.purple}
          onPress={start}
        />
      ) : (
        <View style={{ gap: 10 }}>
          {mode === 'out' ? (
            <>
              <Text style={st.label}>
                ประเภทงาน <Text style={{ color: C.red }}>(ต้องเลือก)</Text>
              </Text>
              <View style={st.chips}>
                {info.purposes.map((p) => {
                  const on = purpose === p.key;
                  return (
                    <Pressable key={p.key} onPress={() => setPurpose(p.key)} style={[st.chip, on && st.chipOn]}>
                      <Text style={[st.chipText, on && { color: '#fff' }]}>{p.name}</Text>
                    </Pressable>
                  );
                })}
              </View>
              <TextInput
                style={st.input}
                value={dest}
                onChangeText={setDest}
                placeholder="ไปที่ไหน (ถ้ามี) เช่น ขนส่งชลบุรี"
                placeholderTextColor={C.sub}
              />
            </>
          ) : null}
          <TextInput
            style={st.input}
            value={odo}
            onChangeText={setOdo}
            placeholder={mode === 'out' ? 'เลขไมล์ตอนออก (ถ้ามี)' : 'เลขไมล์ตอนคืน (ถ้ามี)'}
            placeholderTextColor={C.sub}
            keyboardType="number-pad"
          />
          {mode === 'out' ? (
            <View style={st.row}>
              <Text style={st.rowText}>ขอเบิกน้ำมันด้วย</Text>
              <Switch value={fuel} onValueChange={setFuel} trackColor={{ true: C.purple, false: C.line }} />
            </View>
          ) : (
            <View style={st.row}>
              <Text style={[st.rowText, damage && { color: C.red }]}>มีความเสียหาย / ผิดปกติ</Text>
              <Switch value={damage} onValueChange={setDamage} trackColor={{ true: C.red, false: C.line }} />
            </View>
          )}

          <Text style={st.label}>
            รูป <Text style={{ color: C.red }}>(อย่างน้อย {minPhotos} รูป)</Text>
          </Text>
          {items.length ? <Text style={st.sub}>{items.join(' · ')}</Text> : null}
          <MediaPicker u={u} />

          {angles.length ? (
            <View style={{ gap: 6 }}>
              <View style={[st.row, { paddingVertical: 0 }]}>
                <Text style={st.label}>ถ่ายครบมุมไหนบ้าง</Text>
                <Pressable onPress={() => setSel(angles.map((a) => a.key))} hitSlop={8}>
                  <Text style={{ color: C.purple, fontWeight: '700' }}>ครบทุกมุม</Text>
                </Pressable>
              </View>
              <View style={st.chips}>
                {angles.map((a) => {
                  const on = sel.includes(a.key);
                  return (
                    <Pressable
                      key={a.key}
                      onPress={() => setSel((cur) => (on ? cur.filter((x) => x !== a.key) : [...cur, a.key]))}
                      style={[st.chip, on && st.chipOn]}>
                      <Text style={[st.chipText, on && { color: '#fff' }]}>
                        {on ? '✓ ' : ''}
                        {a.name}
                      </Text>
                    </Pressable>
                  );
                })}
              </View>
              {lackAngles ? (
                <Text style={st.sub}>ยังไม่ครบ {lackAngles} มุม — บันทึกได้ แต่หัวหน้าจะเห็นว่าขาดมุมไหน</Text>
              ) : null}
            </View>
          ) : null}

          <TextInput
            style={[st.input, { minHeight: 70, textAlignVertical: 'top' }]}
            value={note}
            onChangeText={setNote}
            placeholder="หมายเหตุ (ถ้ามี)"
            placeholderTextColor={C.sub}
            multiline
          />
          {missing.length ? <Banner kind="warn" text={'ยังขาด: ' + missing.join(' และ ')} /> : null}
          <Btn
            title={mode === 'out' ? 'ยืนยันเบิกรถ' : 'ยืนยันคืนรถ'}
            color={mode === 'out' ? C.purple : C.green}
            onPress={submit}
            busy={saving}
            disabled={u.busy || !!missing.length}
          />
          <Btn title="ยกเลิก" outline color={C.sub} small onPress={reset} />
        </View>
      )}
    </Card>
  );
}

const st = StyleSheet.create({
  h2: { fontSize: 18, fontWeight: '800', color: C.text },
  sub: { fontSize: 13, color: C.sub, lineHeight: 19 },
  label: { fontSize: 14, fontWeight: '700', color: C.text },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip: {
    minHeight: 40,
    paddingHorizontal: 12,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: C.line,
    backgroundColor: '#fff',
    justifyContent: 'center',
  },
  chipOn: { backgroundColor: C.purple, borderColor: C.purple },
  chipText: { fontSize: 15, fontWeight: '700', color: C.text },
  input: {
    minHeight: 46,
    borderWidth: 1,
    borderColor: C.line,
    borderRadius: 8,
    paddingHorizontal: 12,
    fontSize: 16,
    color: C.text,
    backgroundColor: C.bg,
  },
  row: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10, paddingVertical: 4 },
  rowText: { flex: 1, fontSize: 15, color: C.text },
});
