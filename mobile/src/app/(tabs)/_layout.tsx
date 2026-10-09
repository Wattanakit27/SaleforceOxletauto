// แถบด้านล่าง: แชท (หน้าแรก) · สแกน QR · ฉัน
// คนงาน (ช่าง/ฝ่ายทะเบียน) ใช้แชทลูกค้าไม่ได้ → ซ่อนแท็บแชท เปิดมาที่สแกนเลย
import { Ionicons } from '@expo/vector-icons';
import { Redirect, Tabs } from 'expo-router';
import { useEffect, useState } from 'react';

import { api } from '../../lib/api';
import { canChat, useAuth } from '../../lib/auth';
import { C, Loading } from '../../lib/ui';

type Summary = { counts: { queue: number; mineWaiting: number }; admin: boolean };

export default function TabsLayout() {
  const { ready, me } = useAuth();
  const chat = canChat(me);
  const [badge, setBadge] = useState(0);

  // ตัวเลขบนแท็บแชท — แอดมิน: ลูกค้ารอรับ · เซลล์: ลูกค้าของฉันที่รอตอบ + คิว (เฉพาะวันเวร)
  useEffect(() => {
    if (!chat) return;
    let on = true;
    const tick = () =>
      api<Summary>('/connect/api/summary')
        .then((r) => on && setBadge(r.admin ? r.counts.queue : r.counts.mineWaiting + r.counts.queue))
        .catch(() => undefined);
    tick();
    const t = setInterval(tick, 30000);
    return () => {
      on = false;
      clearInterval(t);
    };
  }, [chat]);

  if (!ready) return <Loading />;
  if (!me) return <Redirect href="/login" />;

  return (
    <Tabs
      screenOptions={{
        tabBarActiveTintColor: C.purple,
        tabBarInactiveTintColor: C.sub,
        headerTitleStyle: { color: C.text, fontWeight: '700' },
        sceneStyle: { backgroundColor: C.bg },
      }}>
      <Tabs.Screen
        name="index"
        options={{
          title: 'แชทลูกค้า',
          tabBarLabel: 'แชท',
          href: chat ? undefined : null,
          tabBarBadge: chat && badge > 0 ? (badge > 99 ? '99+' : badge) : undefined,
          tabBarIcon: ({ color, size }) => <Ionicons name="chatbubbles" color={color} size={size} />,
        }}
      />
      <Tabs.Screen
        name="scan"
        options={{
          title: 'สแกน QR รถ',
          tabBarLabel: 'สแกน QR',
          tabBarIcon: ({ color, size }) => <Ionicons name="qr-code-outline" color={color} size={size} />,
        }}
      />
      <Tabs.Screen
        name="me"
        options={{
          title: me.nickname || 'ฉัน',
          tabBarLabel: 'ฉัน',
          tabBarIcon: ({ color, size }) => <Ionicons name="person-circle-outline" color={color} size={size} />,
        }}
      />
    </Tabs>
  );
}
