// แถบด้านล่าง — จัดตามบทบาท (★ 11 ต.ค.69 ตามต้นแบบ · ข้อมูลจริงทั้งหมด)
//   เซลล์:  แชท · วันนี้ · รถ · ฉัน
//   แอดมิน: แชท · ภาพรวม · ห้องพัก · รถ · ฉัน
//   คนงาน (ช่าง/ฝ่ายทะเบียน/ล้างรถ): งานวันนี้ · รถ · ฉัน
//   จัดซื้อ: วันนี้ · รถ · ฉัน
// login แล้วเปิดมาที่ "แชท" (เจ้าของสั่ง 9 ต.ค.69 · ระบบที่อยากให้เห็นก่อน) · คนที่ไม่มีแชทเปิดมาที่ "วันนี้"
// สแกน QR ย้ายเป็นปุ่มในแท็บ "รถ" (และบนหน้า "งานวันนี้" ของคนงาน)
import { Ionicons } from '@expo/vector-icons';
import { Redirect, Tabs } from 'expo-router';
import { useEffect, useState } from 'react';

import { api } from '../../lib/api';
import { canChat, roleOf, useAuth } from '../../lib/auth';
import { BellButton } from '../../lib/crm';
import { C, Loading } from '../../lib/ui';

type Summary = { counts: { queue: number; mineWaiting: number; tocode?: number; parked?: number; pending?: number }; admin: boolean };

export default function TabsLayout() {
  const { ready, me } = useAuth();
  const chat = canChat(me);
  const role = roleOf(me);
  const admin = role === 'admin';
  const [badge, setBadge] = useState(0);
  const [hubBadge, setHubBadge] = useState(0);

  // ตัวเลขบนแท็บ — แชท: แอดมิน = ลูกค้ารอรับ · เซลล์ = ลูกค้าของฉันที่รอตอบ + คิว · ห้องพัก: รอจ่ายเบอร์
  useEffect(() => {
    if (!chat) return;
    let on = true;
    const tick = () =>
      api<Summary>('/connect/api/summary')
        .then((r) => {
          if (!on) return;
          setBadge(r.admin ? r.counts.queue : r.counts.mineWaiting + r.counts.queue);
          if (r.admin) setHubBadge((r.counts.tocode || 0) + (r.counts.parked || 0) + (r.counts.pending || 0));
        })
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

  const num = (n: number) => (n > 0 ? (n > 99 ? '99+' : n) : undefined);
  const homeLabel = admin ? 'ภาพรวม' : role === 'worker' ? 'งานวันนี้' : 'วันนี้';

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
          headerRight: () => <BellButton />,
          href: chat ? undefined : null,
          tabBarBadge: chat ? num(badge) : undefined,
          tabBarIcon: ({ color, size }) => <Ionicons name="chatbubbles" color={color} size={size} />,
        }}
      />
      <Tabs.Screen
        name="today"
        options={{
          title: homeLabel,
          tabBarLabel: homeLabel,
          headerRight: chat ? () => <BellButton /> : undefined,
          tabBarIcon: ({ color, size }) => (
            <Ionicons name={admin ? 'stats-chart' : 'today-outline'} color={color} size={size} />
          ),
        }}
      />
      <Tabs.Screen
        name="hub"
        options={{
          title: 'ห้องพัก Lead',
          tabBarLabel: 'ห้องพัก',
          href: admin ? undefined : null,
          tabBarBadge: admin ? num(hubBadge) : undefined,
          tabBarIcon: ({ color, size }) => <Ionicons name="file-tray-full-outline" color={color} size={size} />,
        }}
      />
      <Tabs.Screen
        name="cars"
        options={{
          title: 'รถ',
          tabBarLabel: 'รถ',
          tabBarIcon: ({ color, size }) => <Ionicons name="car-sport-outline" color={color} size={size} />,
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
