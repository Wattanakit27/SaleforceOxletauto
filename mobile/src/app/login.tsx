// หน้าเข้าสู่ระบบ — login แล้วพาไปหน้าแชท (หน้าแรกของแอป)
import { Redirect } from 'expo-router';
import { Image, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { BASE } from '../lib/api';
import { useAuth } from '../lib/auth';
import { Banner, Btn, C, Loading } from '../lib/ui';

export default function Login() {
  const { ready, me, busy, error, login } = useAuth();
  if (!ready) return <Loading />;
  if (me) return <Redirect href="/" />;

  return (
    <SafeAreaView style={st.wrap}>
      <ScrollView contentContainerStyle={{ padding: 20, gap: 16 }}>
        <View style={{ alignItems: 'center', marginTop: 40, marginBottom: 8 }}>
          <Image source={require('../../assets/icon.png')} style={{ width: 84, height: 84, borderRadius: 18 }} />
          <Text style={st.h1}>Oxlet</Text>
          <Text style={st.sub}>แชทลูกค้า · สแกน QR รถ</Text>
        </View>
        {error ? <Banner text={error} kind="err" /> : null}
        <Btn title="เข้าสู่ระบบด้วย LINE" color={C.lineGreen} onPress={() => login('line')} busy={busy} />
        <Btn title="ช่าง / ฝ่ายทะเบียน (ชื่อผู้ใช้ + รหัส)" outline onPress={() => login('pw')} disabled={busy} />
        <Text style={st.hint}>
          ใช้บัญชีเดียวกับเว็บ — LINE สำหรับเซลล์/แอดมิน · ชื่อผู้ใช้+รหัสสำหรับคนงาน{'\n'}
          (กด &quot;▸ เข้าสู่ระบบแอดมินระบบ&quot; ในหน้าเว็บเพื่อกรอกชื่อผู้ใช้)
        </Text>
        <Banner kind="info" text={`เวอร์ชันทดลอง · ต่อกับเซิร์ฟเวอร์จริง (${BASE.replace('https://', '')})`} />
      </ScrollView>
    </SafeAreaView>
  );
}

const st = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: C.bg },
  h1: { fontSize: 28, fontWeight: '800', color: C.text, marginTop: 12 },
  sub: { fontSize: 14, color: C.sub, marginTop: 2 },
  hint: { fontSize: 13, color: C.sub, textAlign: 'center', lineHeight: 20 },
});
