// เลือก "สถานะลูกค้า" (คอลัมน์ Z ในชีตลีด) จากแอป — ★ 13 ต.ค.69
// ยิง /crm/api/lead_status ตัวเดียวกับหน้า /crm/ ของเว็บ: เขียนช่อง Z ช่องเดียว · เฉพาะแถวที่ชื่อเซลล์ตรงคนที่ login
// ตัวเลือก = dropdown ชุดเดียวกับในชีต (เซิร์ฟเวอร์ส่งมาใน follow.zOptions · ค่านอกลิสต์ถูกปฏิเสธ)
// รายการตามด่วนจำผลไว้ ~1-2 นาทีฝั่งเซิร์ฟเวอร์ → จำค่าที่เพิ่งบันทึกไว้ในเครื่อง 10 นาที กันโชว์ค่าเก่าแล้วนึกว่าไม่ติด
import { useState } from 'react';
import { Alert, Modal, Pressable, ScrollView, StyleSheet, Text } from 'react-native';

import { api } from './api';
import { C } from './ui';

const KEEP_MS = 10 * 60 * 1000;
const SAVED: Record<string, { v: string; at: number }> = {};

/** สถานะที่ควรโชว์ = ค่าที่เพิ่งบันทึกในเครื่อง (ถ้ายังไม่เกิน 10 นาที) ไม่งั้นค่าจากเซิร์ฟเวอร์ */
export function shownStatus(code: string, server: string): { v: string; saved: boolean } {
  const s = SAVED[code];
  if (s && Date.now() - s.at < KEEP_MS) return { v: s.v, saved: true };
  return { v: server, saved: false };
}

function remember(code: string, v: string) {
  SAVED[code] = { v, at: Date.now() };
}

export function clearSavedStatus() {
  Object.keys(SAVED).forEach((k) => delete SAVED[k]);
}

export function StatusPicker({
  code,
  current,
  options,
  onClose,
  onSaved,
}: {
  code: string;
  current: string;
  options: string[];
  onClose: () => void;
  onSaved: (v: string) => void;
}) {
  const [busy, setBusy] = useState('');

  const save = async (v: string) => {
    if (busy) return;
    if (v === current) {
      onClose();
      return;
    }
    setBusy(v);
    try {
      await api('/crm/api/lead_status', { body: { code, value: v } });
      remember(code, v);
      onSaved(v);
      onClose();
    } catch (e: any) {
      Alert.alert('บันทึกไม่สำเร็จ', e?.message || '');
    } finally {
      setBusy('');
    }
  };

  return (
    <Modal visible transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={st.back} onPress={onClose}>
        <Pressable style={st.sheet} onPress={() => {}}>
          <Text style={st.h}>สถานะลูกค้า · {code}</Text>
          <Text style={st.sub}>บันทึกลงช่อง “สถานะลูกค้า” ในชีตลีด (ชุดเดียวกับ dropdown ในชีต)</Text>
          <ScrollView style={{ maxHeight: 440 }} contentContainerStyle={{ gap: 6, paddingVertical: 8 }}>
            {options.map((o) => {
              const on = o === current;
              return (
                <Pressable
                  key={o}
                  onPress={() => save(o)}
                  disabled={!!busy}
                  style={({ pressed }) => [st.opt, on && st.optOn, pressed && { opacity: 0.7 }]}>
                  <Text style={[st.optT, on && { color: '#fff' }]}>
                    {busy === o ? 'กำลังบันทึก…' : o}
                    {on ? '  ✓' : ''}
                  </Text>
                </Pressable>
              );
            })}
          </ScrollView>
          <Pressable onPress={onClose} style={st.cancel}>
            <Text style={st.cancelT}>ยกเลิก</Text>
          </Pressable>
        </Pressable>
      </Pressable>
    </Modal>
  );
}

const st = StyleSheet.create({
  back: { flex: 1, backgroundColor: 'rgba(0,0,0,0.4)', justifyContent: 'flex-end' },
  sheet: { backgroundColor: '#fff', borderTopLeftRadius: 16, borderTopRightRadius: 16, padding: 16, paddingBottom: 30 },
  h: { fontSize: 18, fontWeight: '800', color: C.text },
  sub: { fontSize: 13, color: C.sub, marginTop: 2 },
  opt: {
    minHeight: 48, borderRadius: 8, borderWidth: 1, borderColor: C.line, paddingHorizontal: 14,
    justifyContent: 'center', backgroundColor: '#fff',
  },
  optOn: { backgroundColor: C.purple, borderColor: C.purple },
  optT: { fontSize: 16, color: C.text, fontWeight: '600' },
  cancel: { marginTop: 8, minHeight: 46, alignItems: 'center', justifyContent: 'center' },
  cancelT: { fontSize: 16, color: C.sub, fontWeight: '700' },
});
