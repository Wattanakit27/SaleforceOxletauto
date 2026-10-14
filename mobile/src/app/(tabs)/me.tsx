// แท็บ "ฉัน" — บัญชีที่ใช้ · เช็คชื่อวันนี้ · คะแนนเซลล์แยก 6 ด้าน (เซลล์) · ออกจากระบบ
// ข้อมูลชุดเดียวกับหน้า "วันนี้" (GET /api/m/home · จำไว้ 45 วิ ไม่โหลดซ้ำตอนสลับแท็บ)
import { router, useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { Alert, RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native';

import { BASE } from '../../lib/api';
import { roleOf, useAuth } from '../../lib/auth';
import { clearHome, Home, loadHome } from '../../lib/home';
import { Avatar, Banner, Btn, C, Card } from '../../lib/ui';

const ROLE_TEXT: Record<string, string> = {
  admin: 'แอดมิน / ผู้บริหาร',
  seller: 'เซลล์',
  worker: 'คนงาน (ช่าง / ฝ่ายทะเบียน / ล้างรถ)',
  buyer: 'จัดซื้อ',
};
const CHECKIN_TEXT: Record<string, [string, string]> = {
  ontime: ['ตรงเวลา', C.green],
  late: ['สาย', C.amber],
  abnormal: ['อ่านเวลาไม่ออก', C.amber],
  dayoff: ['วันหยุด', C.sub],
  none: ['ยังไม่เช็คชื่อ', C.red],
};

export default function Me() {
  const { me, logout } = useAuth();
  const [d, setD] = useState<Home | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async (force: boolean) => {
    try {
      setD(await loadHome(force));
    } catch {
      // หน้านี้ยังใช้ได้แม้โหลดไม่ขึ้น (ออกจากระบบได้เสมอ)
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      load(false);
    }, [load]),
  );

  if (!me) return null;
  const role = roleOf(me);
  const ci = d?.checkin;
  const sc = d?.score;
  const k = d?.kpi;

  return (
    <ScrollView
      contentContainerStyle={{ padding: 16, gap: 14, paddingBottom: 40 }}
      refreshControl={
        <RefreshControl
          refreshing={refreshing}
          tintColor={C.purple}
          onRefresh={async () => {
            setRefreshing(true);
            await load(true);
            setRefreshing(false);
          }}
        />
      }>
      <Card style={{ flexDirection: 'row', alignItems: 'center', gap: 14 }}>
        <Avatar name={me.nickname} size={56} />
        <View style={{ flex: 1 }}>
          <Text style={{ fontSize: 20, fontWeight: '800', color: C.text }}>{me.nickname}</Text>
          <Text style={st.sub}>{ROLE_TEXT[role] || role}</Text>
          {d?.me.position ? <Text style={st.sub}>ตำแหน่งในทะเบียน: {d.me.position}</Text> : null}
        </View>
      </Card>

      {ci && ci.track ? (
        <Card style={{ gap: 6 }}>
          <Text style={st.h2}>เช็คชื่อวันนี้ (วัน{ci.dayName})</Text>
          <Text style={{ fontSize: 18, fontWeight: '800', color: (CHECKIN_TEXT[ci.status] || CHECKIN_TEXT.none)[1] }}>
            {(CHECKIN_TEXT[ci.status] || CHECKIN_TEXT.none)[0]}
            {ci.time ? ` · ${ci.time}` : ''}
            {ci.status === 'late' && ci.lateMin ? ` (${ci.lateMin} นาที)` : ''}
          </Text>
          <Text style={st.sub}>
            เวลาเข้างานของคุณ: {ci.workStart || 'ยังไม่ได้ตั้ง (แจ้งแอดมิน)'}
            {ci.source ? ` · เช็คชื่อทาง${ci.source === 'app' ? 'แอป' : 'รูปในกลุ่ม LINE'}` : ''}
            {ci.anywhere ? ' · เช็คชื่อนอกสถานที่ได้' : ''}
          </Text>
          {ci.status === 'none' ? (
            <Btn title="📍  เช็คชื่อเข้างาน" onPress={() => router.push('/checkin')} />
          ) : (
            <Btn title="ดูรายละเอียดเช็คชื่อ" outline small onPress={() => router.push('/checkin')} />
          )}
          <Text style={st.sub}>ส่งรูปในกลุ่ม LINE เหมือนเดิมก็ได้ — นับอันที่มาก่อน</Text>
        </Card>
      ) : null}

      {role === 'seller' && k ? (
        <Card style={{ gap: 6 }}>
          <Text style={st.h2}>เดือน {k.month}</Text>
          <Text style={st.line}>
            ลีด {k.lead} · จอง {k.booking} · ปล่อย {k.done}
            {k.target ? ` / เป้า ${k.target}` : ''}
          </Text>
        </Card>
      ) : null}

      {role === 'seller' && sc ? (
        <Card style={{ gap: 10 }}>
          <View style={{ flexDirection: 'row', alignItems: 'baseline', gap: 10 }}>
            <Text style={{ fontSize: 34, fontWeight: '800', color: C.purple }}>{sc.total}</Text>
            <Text style={st.line}>คะแนนเดือนนี้ · อันดับ {sc.rank} จาก {sc.of}</Text>
          </View>
          {sc.parts.map((p) => {
            const pct = p.max ? Math.max(0, Math.min(1, p.val / p.max)) : 0;
            return (
              <View key={p.label} style={{ gap: 3 }}>
                <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
                  <Text style={st.line}>{p.label}</Text>
                  <Text style={st.sub}>
                    {p.val} / {p.max}
                  </Text>
                </View>
                <View style={st.bar}>
                  <View style={[st.barFill, { width: `${Math.round(pct * 100)}%`, backgroundColor: pct >= 0.8 ? C.green : pct >= 0.4 ? C.purple : C.amber }]} />
                </View>
              </View>
            );
          })}
          <Text style={st.sub}>สูตรเดียวกับตารางคะแนนในแดชบอร์ด (จบ 30 · จอง 10 · Conv 20 · สถานะ 10 · ติดตาม 20 · โดนแบน 10)</Text>
        </Card>
      ) : null}

      <Banner
        kind="info"
        text={`เวอร์ชันทดลอง · ต่อกับเซิร์ฟเวอร์จริง (${BASE.replace('https://', '')}) — ข้อความที่ตอบ สเตปที่เปลี่ยน และการเบิก-คืนรถเป็นข้อมูลจริง`}
      />
      <Btn
        title="ออกจากระบบ"
        outline
        color={C.red}
        onPress={() =>
          Alert.alert('ออกจากระบบ?', '', [
            { text: 'ยกเลิก', style: 'cancel' },
            {
              text: 'ออกจากระบบ',
              style: 'destructive',
              onPress: () => {
                clearHome();
                logout();
              },
            },
          ])
        }
      />
    </ScrollView>
  );
}

const st = StyleSheet.create({
  h2: { fontSize: 17, fontWeight: '800', color: C.text },
  sub: { fontSize: 13, color: C.sub, lineHeight: 19 },
  line: { fontSize: 15, color: C.text, fontWeight: '600' },
  bar: { height: 8, borderRadius: 4, backgroundColor: C.purpleSoft, overflow: 'hidden' },
  barFill: { height: 8, borderRadius: 4 },
});
