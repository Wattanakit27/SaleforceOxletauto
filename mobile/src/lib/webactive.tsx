// ปุ่ม Active — ให้รถขึ้น/ลงเว็บโชว์รูม Oxlet (★ 14 ต.ค.69 · เดิมกดได้แค่ในหน้าเว็บ)
// ยิง API เดิมของเว็บ: POST /track/api/web_active {code, active}
// ข้อมูล/สิทธิ์มากับ car_json ช่อง `web` (can = ผู้บริหาร/แอดมินเท่านั้น · เซิร์ฟเวอร์ตรวจซ้ำอีกชั้นเสมอ)
//   ขึ้นเว็บจริงเมื่อ Active + อยู่สเตปพร้อมขาย/จอง · ขายแล้ว = หายจากเว็บเสมอ
import { useState } from 'react';
import { Alert, Linking, StyleSheet, Text, View } from 'react-native';

import { api } from './api';
import { BigSwitch, Btn, C, Card } from './ui';

export type WebInfo = {
  active: boolean;
  can: boolean;
  state: string; // live | wait | pending | error | ''
  text: string;
  short: string;
  color: string;
  sold: boolean;
  listed: boolean;
  by: string;
  at: string;
  url: string;
  configured: boolean;
  stageOk: boolean;
};

export function WebActiveCard({ code, web, onDone }: { code: string; web?: WebInfo; onDone: () => Promise<void> | void }) {
  const [busy, setBusy] = useState(false);
  if (!web) return null; // เซิร์ฟเวอร์รุ่นเก่ายังไม่ส่งช่องนี้

  const send = async (on: boolean) => {
    setBusy(true);
    try {
      const r = await api<{ message?: string }>('/track/api/web_active', { body: { code, active: on } });
      await onDone();
      if (r?.message) Alert.alert(on ? 'Active แล้ว' : 'ปิด Active แล้ว', r.message);
    } catch (e: any) {
      Alert.alert('บันทึกไม่สำเร็จ', e?.message || '');
    } finally {
      setBusy(false);
    }
  };

  // ถามยืนยันทั้งเปิดและปิด (เหมือนหน้าเว็บ) — ลูกค้าเห็นผลบนเว็บทันที
  const ask = (on: boolean) =>
    Alert.alert(
      on ? 'ให้รถคันนี้ขึ้นเว็บ Oxlet?' : 'ซ่อนรถคันนี้จากเว็บ Oxlet?',
      on
        ? web.stageOk
          ? 'ลูกค้าจะเห็นรถคันนี้บนเว็บโชว์รูมทันที'
          : 'รถยังไม่ถึงสเตปพร้อมขาย — จะขึ้นเว็บเองเมื่อถึง'
        : 'ลูกค้าจะไม่เห็นรถคันนี้บนเว็บอีก',
      [
        { text: 'ยกเลิก', style: 'cancel' },
        { text: on ? 'Active' : 'ซ่อน', style: on ? 'default' : 'destructive', onPress: () => send(on) },
      ],
    );

  const color = web.color || (web.active ? C.purple : C.sub);
  return (
    <Card style={{ gap: 10 }}>
      <View style={st.row}>
        <View style={{ flex: 1, gap: 2 }}>
          <Text style={st.h2}>แสดงบนเว็บ Oxlet</Text>
          <Text style={st.sub}>{web.can ? 'เปิด = Active (ลูกค้าเห็นบนเว็บโชว์รูม)' : 'เฉพาะผู้บริหาร/แอดมินที่กด Active ได้'}</Text>
        </View>
        <BigSwitch
          value={web.active}
          disabled={!web.can || busy || (web.sold && !web.active)}
          onValueChange={ask}
          trackColor={{ true: C.purple, false: '#d6d3e0' }}
        />
      </View>
      {web.text ? (
        <View style={[st.state, { borderColor: color }]}>
          <Text style={[st.stateT, { color }]}>{web.text}</Text>
        </View>
      ) : null}
      {web.active && web.by ? (
        <Text style={st.sub}>
          กด Active โดย {web.by}
          {web.at ? ` · ${web.at}` : ''}
        </Text>
      ) : null}
      {!web.configured ? <Text style={st.sub}>ระบบยังไม่ได้เชื่อมเว็บโชว์รูม — บันทึกได้ แต่ยังไม่ส่งไปเว็บ</Text> : null}
      {web.url ? <Btn title="ดูบนเว็บ" outline small onPress={() => Linking.openURL(web.url)} /> : null}
      {web.can && web.active && web.state === 'error' ? (
        <Btn title="ส่งไปเว็บอีกครั้ง" small busy={busy} onPress={() => send(true)} />
      ) : null}
    </Card>
  );
}

const st = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  h2: { fontSize: 18, fontWeight: '800', color: C.text },
  sub: { fontSize: 13, color: C.sub, lineHeight: 19 },
  state: { borderWidth: 1.5, borderRadius: 8, paddingHorizontal: 12, paddingVertical: 8 },
  stateT: { fontSize: 15, fontWeight: '700', lineHeight: 21 },
});
