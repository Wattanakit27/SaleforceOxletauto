// ข้อมูลหน้า "วันนี้" (GET /api/m/home) — ก้อนเดียวต่อบทบาท ประกอบจากตัวเดียวกับเว็บ/ข้อความ LINE
// จำไว้ในหน่วยความจำ 45 วิ → สลับแท็บ วันนี้ ↔ ฉัน ไม่ต้องโหลดใหม่ (ดึงลงเพื่อโหลดใหม่ได้เสมอ)
import { api } from './api';
import type { Role } from './auth';

export type CarRow = {
  code: string;
  plate: string;
  label: string;
  title: string;
  stage: string;
  stageName: string;
  days: number;
  flag: 'red' | 'amber' | 'ok' | 'wait';
  priority: string;
  priorityName: string;
  priorityColor: string;
  flags: { key: string; name: string; color: string }[];
};
export type OutRow = {
  code: string;
  plate: string;
  title: string;
  purpose: string;
  destination: string;
  since: string;
  hours: number;
};
export type Checkin = {
  status: 'ontime' | 'late' | 'abnormal' | 'none' | 'dayoff';
  time?: string;
  lateMin?: number | null;
  workStart: string;
  dayName: string;
  track: boolean;
} | null;
export type Task = {
  code: string;
  customer: string;
  car: string;
  phone: string;
  dueAt: string;
  kind: 'overdue' | 'waiting' | 'unsent';
  leftMin: number | null;
  chatId: number | null;
  lastReport: string;
};
export type Urgent = {
  code: string;
  car: string;
  phone: string;
  type: string;
  status: string;
  hot: boolean;
  updates: number;
  idle: number;
  reason: string;
  chatId: number | null;
};
export type Deal = { customer: string; plate: string; car: string; status: string; reason: string; days: number; code: string };
export type BuyCase = {
  code: string;
  name: string;
  car: string;
  phone: string;
  owner: string;
  age: number;
  talked: boolean;
  model: string;
  gapDemand: number;
};
export type Gap = { key: string; name: string; demand: number; show: number; total: number; recent: number };

export type Home = {
  ok: boolean;
  role: Role;
  now: string;
  dayName: string;
  me: { nickname: string; position: string };
  errors?: Record<string, string>;
  checkin?: Checkin;
  myOut?: OutRow[];
  // เซลล์
  seller?: string;
  kpi?: { month: string; lead: number; booking: number; done: number; dealValue: number; notCalled: number; target: number };
  score?: { total: number; rank: number; of: number; parts: { label: string; val: number; max: number }[] } | null;
  chats?: {
    mineWaiting?: number;
    mineOverdue?: number;
    mine?: number;
    queue: number;
    team?: string;
    dutyToday: string;
    dutyTomorrow?: string;
    onDuty?: boolean;
    tocode?: number;
    parked?: number;
    pending?: number;
    slipsToday?: number;
    callLate?: number;
  };
  tasks?: { total: number; open: number; late: number; rows: Task[]; callMin: number };
  follow?: { follow: number; notCalled: number; noStatus: number; stale: number; windowDays: number; urgent: Urgent[]; deals: Deal[] };
  followLazy?: boolean; // ตามด่วนมาแยกคำขอ (ยังไม่มา = กำลังโหลด)
  followError?: string;
  carMatch?: { customers: number; rows: { code: string; customer: string; want: string; cars: { code: string; name: string }[] }[] };
  // แอดมิน
  numbers?: {
    month: string;
    today: { lead: number; leadRJ: number; booking: number; done: number; dealValue: number };
    monthTotal: { lead: number; booking: number; done: number; dealValue: number };
  };
  cars?: { total: number; ready: number; flags: Record<string, number>; outNow: number; stuck: CarRow[] };
  staff?: CheckinAll;
  // คนงาน
  queue?: { role: string; roleLabel: string; total: number; rows: CarRow[]; stages?: string[]; note?: string };
  // จัดซื้อ
  purchase?: {
    total: number;
    notCalled: number;
    stale: number;
    staleDays: number;
    days: number;
    cases: BuyCase[];
    moreCases: number;
    gap: Gap[];
  };
};
/** แอดมิน: ช่อง checkin เป็นสรุปทั้งบริษัท (คนละรูปกับของตัวเอง) */
export type CheckinAll = {
  came: number;
  ontime: number;
  late: number;
  abnormal: number;
  lateRows: { name: string; time: string }[];
  missing: { name: string; workStart: string }[];
  notYet: number;
  dayoff: number;
  noTime: number;
  employees: number;
};

let cache: { at: number; data: Home } | null = null;
let followP: Promise<Home> | null = null;
let gen = 0; // ออกจากระบบ/โหลดใหม่ = รอบใหม่ — ผลของรอบเก่าที่ตอบช้าต้องไม่กลับมาทับ
const TTL = 45000;

/** "ตามด่วน" ของเซลล์ต้องอ่านชีตลีดทั้งก้อน (ครั้งแรกของวัน ~8 วิ) → ขอแยก ไม่ให้หน้าแรกรอ */
function startFollow(base: Home): Promise<Home> {
  const my = gen;
  followP = api<{ follow?: Home['follow']; errors?: Record<string, string> }>('/api/m/home?part=follow', {
    timeoutMs: 90000,
  })
    .then((r): Home => ({ ...base, follow: r.follow, followError: r.follow ? '' : r.errors?.follow || 'โหลดไม่ได้' }))
    .catch((e: any): Home => ({ ...base, followError: e?.message || 'โหลดไม่ได้' }))
    .then((merged) => {
      if (my === gen && cache && cache.data === base) cache = { at: cache.at, data: merged };
      return merged;
    });
  return followP;
}

/** onFollow = เรียกอีกครั้งเมื่อ "ตามด่วน" มาถึง (ถ้าเป็นเซลล์) */
export async function loadHome(force = false, onFollow?: (h: Home) => void): Promise<Home> {
  if (!force && cache && Date.now() - cache.at < TTL) {
    const d = cache.data;
    if (d.followLazy && !d.follow && !d.followError && followP && onFollow) followP.then(onFollow);
    return d;
  }
  const my = ++gen;
  const data = await api<Home>('/api/m/home?lazy=1', { timeoutMs: 45000 });
  if (my !== gen) return data;
  cache = { at: Date.now(), data };
  if (data.followLazy) {
    const p = startFollow(data);
    if (onFollow) p.then(onFollow);
  }
  return data;
}

export function clearHome(): void {
  gen++;
  cache = null;
  followP = null;
}

/** ฿1.2M / ฿850K / ฿1,234 */
export function baht(n?: number | null): string {
  const v = Number(n || 0);
  if (v >= 1e6) return '฿' + (v / 1e6).toFixed(v >= 1e7 ? 0 : 1) + 'M';
  if (v >= 1e3) return '฿' + Math.round(v / 1e3) + 'K';
  return '฿' + v.toLocaleString();
}

/** "เหลือ 12 นาที" / "เลย 5 นาที" */
export function leftText(min: number | null | undefined): string {
  if (min === null || min === undefined) return '';
  if (min >= 0) return `เหลือ ${min} นาที`;
  const m = -min;
  return m >= 60 ? `เลย ${Math.floor(m / 60)} ชม. ${m % 60} นาที` : `เลย ${m} นาที`;
}
