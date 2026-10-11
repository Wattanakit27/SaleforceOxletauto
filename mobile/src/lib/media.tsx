// แนบรูป/วิดีโอ — ใช้ร่วม: เปลี่ยนสเตปรถ · เบิกรถ · คืนรถ
// อัปทันทีที่เลือก เข้า /track/api/upload (ตัวเดียวกับหน้าสแกนของเว็บ · Google Drive โฟลเดอร์ของรถคันนั้น)
// แล้วส่งแค่ [{id, video}] ไปกับคำสั่งบันทึก — เซิร์ฟเวอร์ตรวจจำนวน/กติกาซ้ำอีกชั้นเสมอ
import * as ImagePicker from 'expo-image-picker';
import { useCallback, useState } from 'react';
import { Alert, Image, Pressable, StyleSheet, Text, View } from 'react-native';

import { api } from './api';
import { Btn, C } from './ui';

export type Shot = { uri: string; video: boolean; id?: string; err?: string; uploading: boolean };

export function useUploads(code: string) {
  const [shots, setShots] = useState<Shot[]>([]);

  const upload = useCallback(
    async (a: ImagePicker.ImagePickerAsset) => {
      const video = a.type === 'video';
      setShots((cur) => [...cur, { uri: a.uri, video, uploading: true }]);
      const form = new FormData();
      const name = a.fileName || `${video ? 'video' : 'photo'}-${Date.now()}.${video ? 'mp4' : 'jpg'}`;
      // React Native รับไฟล์ใน FormData เป็น {uri, name, type}
      form.append('file', { uri: a.uri, name, type: a.mimeType || (video ? 'video/mp4' : 'image/jpeg') } as any);
      form.append('code', code);
      try {
        const r = await api<{ id: string }>('/track/api/upload', { form, timeoutMs: 180000 });
        setShots((cur) => cur.map((s) => (s.uri === a.uri ? { ...s, id: r.id, uploading: false } : s)));
      } catch (e: any) {
        setShots((cur) =>
          cur.map((s) => (s.uri === a.uri ? { ...s, err: e?.message || 'อัปไม่สำเร็จ', uploading: false } : s)),
        );
      }
    },
    [code],
  );

  const takePhoto = useCallback(async () => {
    const p = await ImagePicker.requestCameraPermissionsAsync();
    if (!p.granted) {
      Alert.alert('ต้องอนุญาตใช้กล้องก่อน');
      return;
    }
    const r = await ImagePicker.launchCameraAsync({ mediaTypes: ['images'], quality: 0.6 });
    if (!r.canceled) r.assets.forEach(upload);
  }, [upload]);

  const fromLibrary = useCallback(async () => {
    const r = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ['images', 'videos'],
      allowsMultipleSelection: true,
      selectionLimit: 10,
      quality: 0.6,
    });
    if (!r.canceled) r.assets.forEach(upload);
  }, [upload]);

  const ready = shots.filter((s) => s.id);
  return {
    shots,
    ready,
    busy: shots.some((s) => s.uploading),
    media: ready.map((s) => ({ id: s.id as string, video: s.video })),
    takePhoto,
    fromLibrary,
    clear: () => setShots([]),
    remove: (uri: string) => setShots((cur) => cur.filter((x) => x.uri !== uri)),
  };
}

export type Uploads = ReturnType<typeof useUploads>;

/** ปุ่มถ่าย/เลือก + รูปย่อพร้อมสถานะอัป */
export function MediaPicker({ u }: { u: Uploads }) {
  return (
    <View style={{ gap: 8 }}>
      <View style={{ flexDirection: 'row', gap: 8 }}>
        <Btn title="📷 ถ่ายรูป" small onPress={u.takePhoto} style={{ flex: 1 }} />
        <Btn title="🖼 เลือกจากเครื่อง" small outline onPress={u.fromLibrary} style={{ flex: 1 }} />
      </View>
      {u.shots.length ? (
        <View style={st.thumbs}>
          {u.shots.map((s) => (
            <View key={s.uri} style={st.thumbBox}>
              {s.video ? (
                <View style={[st.thumb, st.videoThumb]}>
                  <Text style={{ color: '#fff', fontSize: 22 }}>▶</Text>
                </View>
              ) : (
                <Image source={{ uri: s.uri }} style={st.thumb} />
              )}
              <Text style={[st.thumbState, s.err ? { color: C.red } : s.id ? { color: C.green } : null]}>
                {s.uploading ? 'กำลังอัป…' : s.err ? 'ไม่สำเร็จ' : 'อัปแล้ว'}
              </Text>
              <Pressable onPress={() => u.remove(s.uri)} hitSlop={8}>
                <Text style={{ color: C.sub, fontSize: 12 }}>ลบ</Text>
              </Pressable>
            </View>
          ))}
        </View>
      ) : null}
    </View>
  );
}

const st = StyleSheet.create({
  thumbs: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  thumbBox: { alignItems: 'center', gap: 2 },
  thumb: { width: 76, height: 76, borderRadius: 8, backgroundColor: C.purpleSoft },
  videoThumb: { backgroundColor: '#1f1147', alignItems: 'center', justifyContent: 'center' },
  thumbState: { fontSize: 11, color: C.sub },
});
