// หน้าแรก — ยังไม่ login = ปุ่มเข้าสู่ระบบ · login แล้ว = เมนูใหญ่ 2 อัน (แชทลูกค้า · สแกน QR รถ)
import { router, useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { Alert, Image, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { api, BASE } from '../lib/api';
import { canChat, useAuth } from '../lib/auth';
import { Banner, Btn, C, Card, Loading } from '../lib/ui';

type Summary = { counts: { queue: number; mine: number; mineWaiting: number }; onDuty: boolean; admin: boolean };

export default function Home() {
  const { ready, me, busy, error, login, logout } = useAuth();
  const [sum, setSum] = useState<Summary | null>(null);

  useFocusEffect(
    useCallback(() => {
      if (!canChat(me)) return;
      let alive = true;
      api<Summary>('/connect/api/summary')
        .then((r) => alive && setSum(r))
        .catch(() => alive && setSum(null));
      return () => {
        alive = false;
      };
    }, [me]),
  );

  if (!ready) return <Loading />;

  if (!me) {
    return (
      <SafeAreaView style={st.wrap} edges={['bottom']}>
        <ScrollView contentContainerStyle={{ padding: 20, gap: 16 }}>
          <View style={{ alignItems: 'center', marginTop: 24, marginBottom: 8 }}>
            <Image source={require('../../assets/icon.png')} style={{ width: 84, height: 84, borderRadius: 18 }} />
            <Text style={st.h1}>Oxlet</Text>
            <Text style={st.sub}>แชทลูกค้า · สแกน QR รถ</Text>
          </View>
          {error ? <Banner text={error} kind="err" /> : null}
          <Btn title="เข้าสู่ระบบด้วย LINE" color={C.lineGreen} onPress={() => login('line')} busy={busy} />
          <Btn
            title="ช่าง / ฝ่ายทะเบียน (ชื่อผู้ใช้ + รหัส)"
            outline
            onPress={() => login('pw')}
            disabled={busy}
          />
          <Text style={st.hint}>
            ใช้บัญชีเดียวกับเว็บ — LINE สำหรับเซลล์/แอดมิน · ชื่อผู้ใช้+รหัสสำหรับคนงาน{'\n'}
            (กด &quot;▸ เข้าสู่ระบบแอดมินระบบ&quot; ในหน้าเว็บเพื่อกรอกชื่อผู้ใช้)
          </Text>
          <Banner kind="info" text={`เวอร์ชันทดลอง · ต่อกับเซิร์ฟเวอร์จริง (${BASE.replace('https://', '')})`} />
        </ScrollView>
      </SafeAreaView>
    );
  }

  const chat = canChat(me);
  const waiting = sum ? (sum.admin ? sum.counts.queue : sum.counts.mineWaiting + sum.counts.queue) : 0;

  return (
    <SafeAreaView style={st.wrap} edges={['bottom']}>
      <ScrollView contentContainerStyle={{ padding: 20, gap: 16 }}>
        <View>
          <Text style={st.hello}>สวัสดี {me.nickname}</Text>
          <Text style={st.sub}>{me.admin ? 'แอดมิน' : me.position === 'worker' ? 'คนงาน' : 'เซลล์'}</Text>
        </View>

        {chat ? (
          <Pressable onPress={() => router.push('/chat')} style={({ pressed }) => [pressed && { opacity: 0.8 }]}>
            <Card style={st.tile}>
              <Text style={st.tileIcon}>💬</Text>
              <View style={{ flex: 1 }}>
                <Text style={st.tileTitle}>แชทลูกค้า</Text>
                <Text style={st.sub}>
                  {sum
                    ? sum.admin
                      ? `รอรับ ${sum.counts.queue} คน`
                      : `ลูกค้าของฉัน ${sum.counts.mine} · รอตอบ ${sum.counts.mineWaiting}` +
                        (sum.onDuty ? ` · คิว ${sum.counts.queue}` : '')
                    : 'Connect — ตอบลูกค้า LINE / Facebook'}
                </Text>
              </View>
              {waiting > 0 ? (
                <View style={st.badge}>
                  <Text style={{ color: '#fff', fontWeight: '700' }}>{waiting > 99 ? '99+' : waiting}</Text>
                </View>
              ) : null}
            </Card>
          </Pressable>
        ) : null}

        <Pressable onPress={() => router.push('/scan')} style={({ pressed }) => [pressed && { opacity: 0.8 }]}>
          <Card style={st.tile}>
            <Text style={st.tileIcon}>📷</Text>
            <View style={{ flex: 1 }}>
              <Text style={st.tileTitle}>สแกน QR รถ</Text>
              <Text style={st.sub}>เปิดข้อมูลรถ · เปลี่ยนสเตป · แนบรูป</Text>
            </View>
          </Card>
        </Pressable>

        <Btn
          title="ออกจากระบบ"
          outline
          color={C.sub}
          onPress={() =>
            Alert.alert('ออกจากระบบ?', '', [
              { text: 'ยกเลิก', style: 'cancel' },
              { text: 'ออกจากระบบ', style: 'destructive', onPress: logout },
            ])
          }
        />
        <Text style={st.hint}>เวอร์ชันทดลอง · ข้อความที่ตอบและสเตปที่เปลี่ยน เป็นข้อมูลจริงในระบบ</Text>
      </ScrollView>
    </SafeAreaView>
  );
}

const st = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: C.bg },
  h1: { fontSize: 28, fontWeight: '800', color: C.text, marginTop: 12 },
  hello: { fontSize: 24, fontWeight: '800', color: C.text },
  sub: { fontSize: 14, color: C.sub, marginTop: 2 },
  hint: { fontSize: 13, color: C.sub, textAlign: 'center', lineHeight: 20 },
  tile: { flexDirection: 'row', alignItems: 'center', gap: 14, paddingVertical: 22 },
  tileIcon: { fontSize: 34 },
  tileTitle: { fontSize: 19, fontWeight: '700', color: C.text },
  badge: {
    minWidth: 30,
    height: 30,
    borderRadius: 15,
    backgroundColor: C.red,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 8,
  },
});
