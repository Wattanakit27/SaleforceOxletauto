// วิดีโอ / ข้อความเสียง / ไฟล์ ที่ลูกค้าส่งในแชท (★ 13 ต.ค.69)
// ลิงก์ /connect/api/media ต้องแนบ token (เซิร์ฟเวอร์เช็คสิทธิ์ทุกครั้ง) → เบราว์เซอร์ของระบบเปิดตรงไม่ได้
// จึงโหลดลงเครื่องก่อน (โฟลเดอร์ cache · ระบบลบเองเมื่อที่เต็ม) แล้วค่อย:
//   วิดีโอ/เสียง = เล่นในแอป (expo-video) · ไฟล์อื่น = เปิดหน้าแชร์ของเครื่อง (ดู/ส่งต่อ/เปิดด้วยแอปอื่น)
// โหลดซ้ำไม่ได้ยิงเน็ตใหม่ — ไฟล์เดิมอยู่ในเครื่องแล้วใช้เลย
import { Directory, File, Paths } from 'expo-file-system';
import * as Sharing from 'expo-sharing';
import { useVideoPlayer, VideoView } from 'expo-video';
import { useState } from 'react';
import { ActivityIndicator, Alert, Modal, Pressable, StyleSheet, Text, View } from 'react-native';

import { authHeaders } from './api';
import { C } from './ui';

export type MFile = { url: string; kind: string; state: string; name: string; size: number; ext: string };

const MIME: Record<string, string> = {
  pdf: 'application/pdf', mp4: 'video/mp4', mov: 'video/quicktime', m4a: 'audio/mp4', mp3: 'audio/mpeg',
  aac: 'audio/aac', jpg: 'image/jpeg', jpeg: 'image/jpeg', png: 'image/png',
};
const UTI: Record<string, string> = { pdf: 'com.adobe.pdf', mp4: 'public.mpeg-4', mov: 'com.apple.quicktime-movie' };

function sizeText(n: number): string {
  if (!n) return '';
  if (n >= 1024 * 1024) return (n / 1024 / 1024).toFixed(1) + ' MB';
  return Math.max(1, Math.round(n / 1024)) + ' KB';
}

/** ชื่อไฟล์ในเครื่อง = id ของไฟล์ในระบบ (m=l123.0) — ไม่ใช้ชื่อเดิมของลูกค้า (อาจมีอักขระแปลก/ชนกัน) */
function localName(f: MFile): string {
  const m = /[?&]m=([^&]+)/.exec(f.url);
  const key = (m ? decodeURIComponent(m[1]) : String(Date.now())).replace(/[^A-Za-z0-9._-]/g, '_');
  const ext = (f.ext || '').replace(/[^A-Za-z0-9]/g, '').slice(0, 8) || 'bin';
  return `${key}.${ext}`;
}

async function toCache(url: string, f: MFile): Promise<File> {
  const dir = new Directory(Paths.cache, 'chat-files');
  if (!dir.exists) dir.create({ intermediates: true, idempotent: true });
  const file = new File(dir, localName(f));
  if (file.exists && file.size > 0) return file;
  const got = await File.downloadFileAsync(url, file, { headers: authHeaders(), idempotent: true });
  // กันพลาด: เซิร์ฟเวอร์ตอบ error เป็น JSON แต่ถูกเขียนลงไฟล์ (ไฟล์จริงไม่มีทางเล็กแบบนี้แล้วขึ้นต้นด้วย {"ok")
  if (got.size < 4096) {
    let head = '';
    try {
      head = (await got.text()).slice(0, 400);
    } catch {
      head = '';
    }
    if (/^\s*\{/.test(head) && /"ok"\s*:\s*false|"error"/.test(head)) {
      got.delete();
      let msg = 'เปิดไฟล์ไม่ได้';
      try {
        msg = JSON.parse(head).error || msg;
      } catch {
        // ใช้ข้อความกลาง
      }
      throw new Error(msg);
    }
  }
  return got;
}

/** แถวไฟล์ในบับเบิล (ไม่ใช่รูป) — แตะ = โหลดแล้วเล่น/เปิด */
export function ChatFile({ f, uri, out }: { f: MFile; uri: string; out: boolean }) {
  const [busy, setBusy] = useState(false);
  const [play, setPlay] = useState<{ uri: string; audio: boolean } | null>(null);
  const label =
    f.kind === 'video' ? 'วิดีโอ' : f.kind === 'audio' ? 'ข้อความเสียง' : f.name || 'ไฟล์' + (f.ext ? ' .' + f.ext : '');
  const icon = f.kind === 'video' ? '▶' : f.kind === 'audio' ? '🎤' : '📄';
  const hint = f.kind === 'video' || f.kind === 'audio' ? 'แตะเพื่อเล่น' : 'แตะเพื่อเปิด / ส่งต่อ';

  const open = async () => {
    if (busy) return;
    setBusy(true);
    try {
      const file = await toCache(uri, f);
      if (f.kind === 'video' || f.kind === 'audio') {
        setPlay({ uri: file.uri, audio: f.kind === 'audio' });
      } else if (await Sharing.isAvailableAsync()) {
        const ext = (f.ext || '').toLowerCase();
        await Sharing.shareAsync(file.uri, { mimeType: MIME[ext], UTI: UTI[ext], dialogTitle: label });
      } else {
        Alert.alert('เครื่องนี้เปิดไฟล์จากแอปไม่ได้', 'เปิดดูได้ที่หน้าเว็บ Connect');
      }
    } catch (e: any) {
      Alert.alert('เปิดไฟล์ไม่สำเร็จ', (e?.message || '') + '\nลองใหม่ หรือเปิดดูที่หน้าเว็บ Connect');
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <Pressable onPress={open} style={({ pressed }) => [st.row, out && st.rowOut, pressed && { opacity: 0.7 }]}>
        <View style={[st.icon, out && { backgroundColor: 'rgba(255,255,255,0.2)' }]}>
          {busy ? <ActivityIndicator color={out ? '#fff' : C.purple} /> : <Text style={st.iconT}>{icon}</Text>}
        </View>
        <View style={{ flexShrink: 1 }}>
          <Text style={[st.name, out && { color: '#fff' }]} numberOfLines={2}>
            {label}
          </Text>
          <Text style={[st.hint, out && { color: '#ede9fe' }]}>
            {busy ? 'กำลังโหลด…' : hint}
            {f.size ? ' · ' + sizeText(f.size) : ''}
          </Text>
        </View>
      </Pressable>
      <Modal visible={!!play} transparent animationType="fade" onRequestClose={() => setPlay(null)}>
        <View style={st.viewer}>
          {play ? <Player uri={play.uri} audio={play.audio} /> : null}
          <Pressable onPress={() => setPlay(null)} style={st.close} hitSlop={10}>
            <Text style={st.closeT}>ปิด</Text>
          </Pressable>
        </View>
      </Modal>
    </>
  );
}

function Player({ uri, audio }: { uri: string; audio: boolean }) {
  const player = useVideoPlayer(uri, (p) => {
    p.play();
  });
  return (
    <View style={{ width: '100%', alignItems: 'center', gap: 12 }}>
      {audio ? <Text style={st.audioT}>🎤 ข้อความเสียงจากลูกค้า</Text> : null}
      <VideoView player={player} style={audio ? st.audio : st.video} nativeControls contentFit="contain" />
    </View>
  );
}

const st = StyleSheet.create({
  row: {
    flexDirection: 'row', alignItems: 'center', gap: 10, minWidth: 200, paddingHorizontal: 8, paddingVertical: 8,
    borderRadius: 10, backgroundColor: C.bg,
  },
  rowOut: { backgroundColor: 'rgba(255,255,255,0.12)' },
  icon: { width: 40, height: 40, borderRadius: 8, backgroundColor: C.purpleSoft, alignItems: 'center', justifyContent: 'center' },
  iconT: { fontSize: 18, color: C.purple },
  name: { fontSize: 15, fontWeight: '700', color: C.text },
  hint: { fontSize: 12, color: C.sub, marginTop: 1 },
  viewer: { flex: 1, backgroundColor: 'rgba(0,0,0,0.94)', alignItems: 'center', justifyContent: 'center', padding: 12 },
  video: { width: '100%', height: '75%' },
  audio: { width: '100%', height: 90 },
  audioT: { color: '#fff', fontSize: 16, fontWeight: '700' },
  close: { marginTop: 18, paddingHorizontal: 28, paddingVertical: 10, borderRadius: 8, borderWidth: 1, borderColor: '#888' },
  closeT: { color: '#fff', fontSize: 16, fontWeight: '700' },
});
