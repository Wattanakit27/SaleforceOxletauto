// แท็บ "ฉัน" — บัญชีที่ใช้อยู่ + ออกจากระบบ
import { Alert, ScrollView, Text, View } from 'react-native';

import { BASE } from '../../lib/api';
import { useAuth } from '../../lib/auth';
import { Avatar, Banner, Btn, C, Card } from '../../lib/ui';

export default function Me() {
  const { me, logout } = useAuth();
  if (!me) return null;
  const role = me.admin ? 'แอดมิน' : me.position === 'worker' ? 'คนงาน (ช่าง/ฝ่ายทะเบียน)' : 'เซลล์';
  return (
    <ScrollView contentContainerStyle={{ padding: 20, gap: 16 }}>
      <Card style={{ flexDirection: 'row', alignItems: 'center', gap: 14 }}>
        <Avatar name={me.nickname} size={56} />
        <View style={{ flex: 1 }}>
          <Text style={{ fontSize: 20, fontWeight: '800', color: C.text }}>{me.nickname}</Text>
          <Text style={{ fontSize: 14, color: C.sub, marginTop: 2 }}>{role}</Text>
        </View>
      </Card>
      <Banner
        kind="info"
        text={`เวอร์ชันทดลอง · ต่อกับเซิร์ฟเวอร์จริง (${BASE.replace('https://', '')}) — ข้อความที่ตอบและสเตปที่เปลี่ยนเป็นข้อมูลจริง`}
      />
      <Btn
        title="ออกจากระบบ"
        outline
        color={C.red}
        onPress={() =>
          Alert.alert('ออกจากระบบ?', '', [
            { text: 'ยกเลิก', style: 'cancel' },
            { text: 'ออกจากระบบ', style: 'destructive', onPress: logout },
          ])
        }
      />
    </ScrollView>
  );
}
