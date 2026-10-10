// หน้ารวมแชท (Chat Inbox) — ของที่ใช้ร่วมกันในแอป: ป้ายขั้นของลีด/ความร้อน · กระดิ่งแจ้งเตือน
// ข้อมูลทั้งหมดมาจาก API เดิมของเว็บ (/connect/api/…) · เซิร์ฟเวอร์ตัดสินสิทธิ์ทุกอย่าง
import { Ionicons } from '@expo/vector-icons';
import { router, useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { Pressable, Text, View } from 'react-native';

import { api } from './api';
import { C, fmtTime, Tag } from './ui';

export type Appt = { kind: string; due: string; late: boolean } | null;
export type Extra = {
  stage?: string;
  stageLabel?: string;
  heat?: '' | 'hot' | 'warm' | 'cold';
  heatScore?: number;
  heatWhy?: string[];
  silentDays?: number;
  silent?: number;
  noReply?: boolean;
  appt?: Appt;
  carMatch?: number;
  lostReason?: string;
};

export const STAGE_COLOR: Record<string, [string, string]> = {
  new: [C.purple, C.purpleSoft],
  pool: [C.purple, C.purpleSoft],
  waiting: [C.amber, C.amberBg],
  contacted: [C.text, '#eeeaf8'],
  viewing: ['#6d28d9', C.purpleSoft],
  finance: ['#6d28d9', C.purpleSoft],
  won: [C.green, C.greenBg],
  lost: [C.sub, '#eeeeee'],
};
export const HEAT: Record<string, [string, string, string]> = {
  hot: ['🔥 ร้อน', C.red, C.redBg],
  warm: ['อุ่น', C.amber, C.amberBg],
  cold: ['เย็น', C.sub, '#eeeeee'],
};

/** ป้ายในรายชื่อ — ลีดใหม่ไม่ติด (ทุกแถวในคิวเหมือนกันหมด) · ความร้อนโชว์เฉพาะร้อน/อุ่น */
export function CrmTags({ r }: { r: Extra }) {
  const out = [];
  if (r.stage && r.stage !== 'new') {
    const [fg, bg] = STAGE_COLOR[r.stage] || [C.sub, '#eee'];
    out.push(<Tag key="st" text={r.stageLabel || r.stage} color={fg} bg={bg} />);
  }
  if (r.heat === 'hot' || r.heat === 'warm') {
    const [t, fg, bg] = HEAT[r.heat];
    out.push(<Tag key="ht" text={t} color={fg} bg={bg} />);
  }
  if (r.appt) {
    out.push(
      <Tag
        key="ap"
        text={(r.appt.kind === 'viewing' ? 'ดูรถ ' : 'นัด ') + fmtTime(r.appt.due)}
        color={r.appt.late ? '#fff' : '#6d28d9'}
        bg={r.appt.late ? C.red : C.purpleSoft}
      />,
    );
  }
  if (r.silent) out.push(<Tag key="sl" text={`เงียบ ${r.silentDays} วัน`} color={C.amber} bg={C.amberBg} />);
  else if (r.noReply) out.push(<Tag key="nr" text="ลูกค้าไม่ตอบ" color={C.amber} bg={C.amberBg} />);
  if (r.carMatch) out.push(<Tag key="cm" text={`รถใหม่ตรง ${r.carMatch}`} color={C.green} bg={C.greenBg} />);
  return <>{out}</>;
}

export type AlertItem = {
  kind: string;
  level: 'info' | 'warn' | 'err';
  text: string;
  id?: number;
  view?: string;
  filter?: Record<string, string>;
  n?: number;
};
export type Alerts = { items: AlertItem[]; count: number };

/** กระดิ่งบนหัวหน้าแชท — ทุก 30 วิ ระหว่างเปิดหน้านี้ */
export function BellButton() {
  const [n, setN] = useState(0);
  useFocusEffect(
    useCallback(() => {
      let on = true;
      const tick = () =>
        api<Alerts>('/connect/api/alerts')
          .then((r) => on && setN(r.count || 0))
          .catch(() => undefined);
      tick();
      const t = setInterval(tick, 30000);
      return () => {
        on = false;
        clearInterval(t);
      };
    }, []),
  );
  return (
    <Pressable onPress={() => router.push('/alerts')} hitSlop={10} style={{ paddingHorizontal: 14 }}>
      <View>
        <Ionicons name="notifications-outline" size={24} color={C.purple} />
        {n > 0 ? (
          <View
            style={{
              position: 'absolute',
              top: -5,
              right: -8,
              minWidth: 18,
              height: 18,
              borderRadius: 9,
              backgroundColor: C.red,
              alignItems: 'center',
              justifyContent: 'center',
              paddingHorizontal: 4,
            }}>
            <Text style={{ color: '#fff', fontSize: 11, fontWeight: '800' }}>{n > 99 ? '99+' : n}</Text>
          </View>
        ) : null}
      </View>
    </Pressable>
  );
}

/** ค่าที่ไม่ซ้ำ ใช้แนบตอนส่งตัวกรองข้ามหน้า (กดเรื่องเดิมซ้ำแล้วต้องตั้งตัวกรองซ้ำได้) */
export function uniq(): string {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
}

const pad = (n: number) => String(n).padStart(2, '0');
/** "2026-10-12T10:00" (เวลาเครื่อง = เวลาไทย) — รูปแบบที่ API นัดหมายรับ */
export function localDT(d: Date): string {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
const TH_MON = ['ม.ค.', 'ก.พ.', 'มี.ค.', 'เม.ย.', 'พ.ค.', 'มิ.ย.', 'ก.ค.', 'ส.ค.', 'ก.ย.', 'ต.ค.', 'พ.ย.', 'ธ.ค.'];
/** 12 ต.ค. 69 14:30 */
export function fmtFull(iso?: string | null): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return '';
  return `${d.getDate()} ${TH_MON[d.getMonth()]} ${String(d.getFullYear() + 543).slice(-2)} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
