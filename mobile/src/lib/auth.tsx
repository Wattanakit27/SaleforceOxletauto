// login ของแอป — ใช้หน้า login ตัวเดิมของเว็บ (LINE Login / ชื่อผู้ใช้+รหัสของคนงาน)
// ทางเดิน: เปิดเบราว์เซอร์ของระบบ → login → เว็บส่ง "รหัสใช้ครั้งเดียว" กลับเข้าแอป → แลกเป็น token
// PKCE: แอปสุ่มรหัสลับ (verifier) ไว้เอง ส่งแค่แฮชไปตอนเริ่ม → แอปอื่นที่ดักรหัสไปได้ก็แลก token ไม่ได้
import * as Crypto from 'expo-crypto';
import * as Linking from 'expo-linking';
import * as SecureStore from 'expo-secure-store';
import * as WebBrowser from 'expo-web-browser';
import { createContext, ReactNode, useCallback, useContext, useEffect, useState } from 'react';
import { Platform } from 'react-native';

import { api, BASE, loadToken, saveToken, setUnauthorizedHandler } from './api';

export type Me = { nickname: string; position: string; admin: boolean };

type AuthState = {
  ready: boolean;
  me: Me | null;
  busy: boolean;
  error: string;
  login: (via: 'line' | 'pw') => Promise<void>;
  logout: () => Promise<void>;
};

const ME_KEY = 'oxlet_me';
const Ctx = createContext<AuthState | null>(null);

function hex(bytes: Uint8Array): string {
  let s = '';
  bytes.forEach((b) => (s += b.toString(16).padStart(2, '0')));
  return s;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [me, setMe] = useState<Me | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const clear = useCallback(async () => {
    await saveToken(null);
    await SecureStore.deleteItemAsync(ME_KEY);
    setMe(null);
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(() => {
      clear();
      setError('หมดเวลาใช้งาน — เข้าสู่ระบบใหม่อีกครั้ง');
    });
    (async () => {
      const t = await loadToken();
      const raw = await SecureStore.getItemAsync(ME_KEY);
      if (t && raw) {
        try {
          setMe(JSON.parse(raw));
        } catch {
          await clear();
        }
      }
      setReady(true);
      if (t) {
        // เช็คกับเซิร์ฟเวอร์ว่า token ยังใช้ได้ (ถูกยกเลิก/ลาออก = เด้งไปหน้า login เอง)
        try {
          const r = await api<{ me: Me }>('/api/m/me');
          setMe(r.me);
          await SecureStore.setItemAsync(ME_KEY, JSON.stringify(r.me));
        } catch {
          /* ออฟไลน์ = ใช้ข้อมูลเดิมไปก่อน · 401 = handler ด้านบนจัดการแล้ว */
        }
      }
    })();
    return () => setUnauthorizedHandler(null);
  }, [clear]);

  const login = useCallback(async (via: 'line' | 'pw') => {
    setError('');
    setBusy(true);
    try {
      const verifier = hex(Crypto.getRandomBytes(32)); // 64 ตัวอักษร (ช่วงที่ PKCE กำหนด 43–128)
      const b64 = await Crypto.digestStringAsync(Crypto.CryptoDigestAlgorithm.SHA256, verifier, {
        encoding: Crypto.CryptoEncoding.BASE64,
      });
      const challenge = b64.replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
      // Expo Go = exp://<IP เครื่องคอม>:8081/--/auth · แอปจริง = oxletauto://auth
      const redirect = Linking.createURL('auth');
      const url =
        `${BASE}/m/login?r=${encodeURIComponent(redirect)}` +
        `&c=${encodeURIComponent(challenge)}&via=${via}`;
      const res = await WebBrowser.openAuthSessionAsync(url, redirect);
      if (res.type !== 'success') return; // ผู้ใช้กดปิดเอง
      const code = String(Linking.parse(res.url).queryParams?.code || '');
      if (!code) {
        setError('ไม่ได้รับรหัสกลับจากเว็บ — ลองใหม่อีกครั้ง');
        return;
      }
      const r = await api<{ token: string; me: Me }>('/api/m/token', {
        body: { code, verifier, device: `${Platform.OS} ${String(Platform.Version)}` },
      });
      await saveToken(r.token);
      await SecureStore.setItemAsync(ME_KEY, JSON.stringify(r.me));
      setMe(r.me);
    } catch (e: any) {
      setError(e?.message || 'เข้าสู่ระบบไม่สำเร็จ');
    } finally {
      setBusy(false);
    }
  }, []);

  const logout = useCallback(async () => {
    try {
      await api('/api/m/logout', { method: 'POST' });
    } catch {
      /* ออกจากระบบฝั่งเครื่องต่อไปได้แม้เซิร์ฟเวอร์ไม่ตอบ */
    }
    await clear();
  }, [clear]);

  return (
    <Ctx.Provider value={{ ready, me, busy, error, login, logout }}>{children}</Ctx.Provider>
  );
}

export function useAuth(): AuthState {
  const v = useContext(Ctx);
  if (!v) throw new Error('useAuth ต้องอยู่ใน AuthProvider');
  return v;
}

/** คนงาน (ช่าง/ฝ่ายทะเบียน/ล้างรถ) ใช้แชทลูกค้าไม่ได้ — เว็บก็บล็อกเหมือนกัน */
export function canChat(me: Me | null): boolean {
  return !!me && me.position !== 'worker';
}
