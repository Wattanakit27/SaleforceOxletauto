// เรียก API ของเว็บ Oxlet ด้วย token ของแอป (Authorization: Bearer)
// เว็บมี middleware ที่แปลง token เป็น "คนที่ login อยู่" → API เดิมของเว็บใช้กับแอปได้เลย
import Constants from 'expo-constants';
import * as SecureStore from 'expo-secure-store';

export const BASE: string =
  ((Constants.expoConfig?.extra as { apiBase?: string } | undefined)?.apiBase ||
    'https://srv1793506.hstgr.cloud').replace(/\/+$/, '');

const TOKEN_KEY = 'oxlet_token';
let token: string | null = null;
let onUnauthorized: (() => void) | null = null;

export async function loadToken(): Promise<string | null> {
  token = await SecureStore.getItemAsync(TOKEN_KEY);
  return token;
}

export async function saveToken(t: string | null): Promise<void> {
  token = t;
  if (t) await SecureStore.setItemAsync(TOKEN_KEY, t);
  else await SecureStore.deleteItemAsync(TOKEN_KEY);
}

export function setUnauthorizedHandler(fn: (() => void) | null): void {
  onUnauthorized = fn;
}

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

/** ลิงก์รูปที่เว็บส่งมาเป็น path (/media/...) → ต่อโดเมนให้ */
export function absUrl(u?: string | null): string {
  if (!u) return '';
  if (/^https?:\/\//i.test(u)) return u;
  return BASE + (u.startsWith('/') ? u : '/' + u);
}

type Opts = { method?: 'GET' | 'POST'; body?: unknown; form?: FormData; timeoutMs?: number };

export async function api<T = any>(path: string, opts: Opts = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' };
  if (token) headers.Authorization = 'Bearer ' + token;
  let body: string | FormData | undefined;
  if (opts.form) {
    body = opts.form; // ห้ามตั้ง Content-Type เอง — ให้ fetch ใส่ boundary ของ multipart ให้
  } else if (opts.body !== undefined) {
    headers['Content-Type'] = 'application/json';
    body = JSON.stringify(opts.body);
  }
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), opts.timeoutMs ?? 30000);
  let res: Response;
  try {
    res = await fetch(BASE + path, {
      method: opts.method ?? (body ? 'POST' : 'GET'),
      headers,
      body,
      signal: ctl.signal,
    });
  } catch {
    throw new ApiError('ต่อเซิร์ฟเวอร์ไม่ได้ — เช็คอินเทอร์เน็ต', 0);
  } finally {
    clearTimeout(timer);
  }
  let data: any = null;
  try {
    data = await res.json();
  } catch {
    data = null;
  }
  if (res.status === 401 && token && data?.relogin) {
    onUnauthorized?.();
  }
  if (!res.ok || (data && data.ok === false)) {
    const msg = (data && (data.error || data.message)) || `เซิร์ฟเวอร์ตอบ ${res.status}`;
    throw new ApiError(String(msg), res.status);
  }
  return data as T;
}
