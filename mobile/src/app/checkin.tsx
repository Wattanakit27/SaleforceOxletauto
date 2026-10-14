// เช็คชื่อเข้างานในแอป (★ 14 ต.ค.69 · เจ้าของสั่ง) — เซลฟี่ + ตำแหน่ง → POST /api/m/checkin
// · ไม่ส่งอะไรลงกลุ่ม LINE (ตาราง 9:30 / รอบตามตัว 10:00 อ่านจากระบบอยู่แล้ว)
// · ส่งรูปในกลุ่มเหมือนเดิมก็ยังได้ — อันไหนมาก่อนนับอันนั้น
// · คนที่แอดมินไม่ได้ติ๊ก "เช็คชื่อนอกสถานที่ได้" ต้องอยู่ในรัศมีสาขา (เซิร์ฟเวอร์ตรวจ)
import * as ImagePicker from 'expo-image-picker';
import * as Location from 'expo-location';
import { Stack, useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { Alert, Image, Linking, ScrollView, StyleSheet, Text, View } from 'react-native';

import { api } from '../lib/api';
import { Banner, Btn, C, Card, Loading } from '../lib/ui';

type Info = {
  ok: boolean;
  linked: boolean;
  error?: string;
  name?: string;
  done?: boolean;
  anywhere?: boolean;
  track?: boolean;
  workStart?: string;
  sites?: string[];
  time?: string;
  status?: string;
  lateMin?: number;
  source?: string;
  site?: string;
};
type Pos = { lat: number; lng: number; acc: number };

const ST: Record<string, [string, string, string]> = {
  ontime: ['ตรงเวลา', C.green, C.greenBg],
  late: ['สาย', C.amber, C.amberBg],
  abnormal: ['เช็คชื่อแล้ว', C.amber, C.amberBg],
};

/** หาตำแหน่ง — ให้เวลาสูงสุด 20 วิ แล้วตกไปใช้ตำแหน่งล่าสุดที่เครื่องจำไว้ */
async function locate(): Promise<Pos> {
  const p = await Location.requestForegroundPermissionsAsync();
  if (!p.granted) throw new Error('perm');
  const timeout = new Promise<null>((r) => setTimeout(() => r(null), 20000));
  const cur = await Promise.race([
    Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.High }).catch(() => null),
    timeout,
  ]);
  const got = cur || (await Location.getLastKnownPositionAsync().catch(() => null));
  if (!got) throw new Error('nopos');
  return { lat: got.coords.latitude, lng: got.coords.longitude, acc: got.coords.accuracy || 0 };
}

export default function CheckinScreen() {
  const [info, setInfo] = useState<Info | null>(null);
  const [err, setErr] = useState('');
  const [step, setStep] = useState(''); // ข้อความระหว่างทำงาน (หาตำแหน่ง / ส่ง)
  const [photo, setPhoto] = useState<ImagePicker.ImagePickerAsset | null>(null);
  const [pos, setPos] = useState<Pos | null>(null);
  const [result, setResult] = useState('');

  const load = useCallback(async () => {
    try {
      setInfo(await api<Info>('/api/m/checkin'));
      setErr('');
    } catch (e: any) {
      setErr(e?.message || 'โหลดไม่สำเร็จ');
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load]),
  );

  const start = async () => {
    setResult('');
    setStep('กำลังหาตำแหน่ง…');
    let where: Pos;
    try {
      where = await locate();
    } catch (e: any) {
      setStep('');
      if (e?.message === 'perm') {
        Alert.alert('ต้องอนุญาตตำแหน่งก่อน', 'เปิดการเข้าถึงตำแหน่งให้แอป แล้วกดเช็คชื่ออีกครั้ง', [
          { text: 'ปิด', style: 'cancel' },
          { text: 'เปิดการตั้งค่า', onPress: () => Linking.openSettings() },
        ]);
      } else {
        Alert.alert('หาตำแหน่งไม่ได้', 'ลองออกไปที่โล่ง หรือเปิด GPS แล้วกดใหม่');
      }
      return;
    }
    setPos(where);
    setStep('');
    const cam = await ImagePicker.requestCameraPermissionsAsync();
    if (!cam.granted) {
      Alert.alert('ต้องอนุญาตใช้กล้องก่อน', 'เปิดการเข้าถึงกล้องให้แอป แล้วกดเช็คชื่ออีกครั้ง', [
        { text: 'ปิด', style: 'cancel' },
        { text: 'เปิดการตั้งค่า', onPress: () => Linking.openSettings() },
      ]);
      return;
    }
    const r = await ImagePicker.launchCameraAsync({
      mediaTypes: ['images'],
      cameraType: ImagePicker.CameraType.front,
      quality: 0.5,
    });
    if (!r.canceled && r.assets[0]) setPhoto(r.assets[0]);
  };

  const submit = async () => {
    if (!photo || !pos) return;
    setStep('กำลังเช็คชื่อ…');
    const form = new FormData();
    form.append('photo', { uri: photo.uri, name: photo.fileName || 'selfie.jpg', type: photo.mimeType || 'image/jpeg' } as any);
    form.append('lat', String(pos.lat));
    form.append('lng', String(pos.lng));
    form.append('acc', String(Math.round(pos.acc)));
    try {
      const r = await api<{ message: string }>('/api/m/checkin', { form, timeoutMs: 60000 });
      setResult(r.message || 'เช็คชื่อแล้ว');
      setPhoto(null);
      await load();
    } catch (e: any) {
      Alert.alert('เช็คชื่อไม่สำเร็จ', e?.message || '');
    } finally {
      setStep('');
    }
  };

  if (err && !info) {
    return (
      <View style={{ padding: 16, gap: 12 }}>
        <Banner kind="err" text={err} />
        <Btn title="ลองใหม่" onPress={load} />
      </View>
    );
  }
  if (!info) return <Loading />;

  const st = info.status ? ST[info.status] || ST.abnormal : null;
  return (
    <ScrollView contentContainerStyle={{ padding: 14, gap: 14, paddingBottom: 40 }}>
      <Stack.Screen options={{ title: 'เช็คชื่อเข้างาน' }} />
      {!info.linked ? <Banner kind="err" text={info.error || 'บัญชีนี้ยังไม่ผูกกับทะเบียนพนักงาน'} /> : null}
      {info.linked && info.track === false ? <Banner kind="info" text="บัญชีนี้ตั้งไว้ว่าไม่ต้องเช็คชื่อเข้างาน" /> : null}

      {info.linked && info.done ? (
        <Card style={{ gap: 10, alignItems: 'center' }}>
          <Text style={s.big}>✓</Text>
          <Text style={s.h2}>เช็คชื่อแล้ววันนี้</Text>
          <Text style={s.time}>{info.time || '-'}</Text>
          {st ? (
            <View style={[s.pill, { backgroundColor: st[2] }]}>
              <Text style={[s.pillT, { color: st[1] }]}>
                {st[0]}
                {info.status === 'late' && info.lateMin ? ` ${info.lateMin} นาที` : ''}
              </Text>
            </View>
          ) : null}
          <Text style={s.sub}>
            เช็คชื่อทาง{info.source || '-'}
            {info.site ? ` · สาขา${info.site}` : ''}
            {info.workStart ? ` · เวลาเข้างาน ${info.workStart}` : ''}
          </Text>
          {result ? <Banner kind="info" text={result} /> : null}
        </Card>
      ) : null}

      {info.linked && !info.done && info.track !== false ? (
        <Card style={{ gap: 12 }}>
          <Text style={s.h2}>สวัสดี {info.name}</Text>
          <Text style={s.sub}>
            เวลาเข้างาน {info.workStart || '(ยังไม่ได้ตั้ง — แจ้งแอดมิน)'} ·{' '}
            {info.anywhere
              ? 'เช็คชื่อนอกสถานที่ได้'
              : info.sites?.length
                ? `ต้องอยู่ที่สาขา (${info.sites.join(' / ')})`
                : 'เช็คชื่อได้ทุกที่ (ยังไม่ได้ตั้งพิกัดสาขา)'}
          </Text>
          <Text style={s.sub}>กดแล้วระบบจะหาตำแหน่ง แล้วเปิดกล้องหน้าให้ถ่ายเซลฟี่ 1 รูป — ไม่ส่งรูปลงกลุ่ม LINE</Text>

          {photo ? (
            <View style={{ gap: 10 }}>
              <Image source={{ uri: photo.uri }} style={s.selfie} resizeMode="cover" />
              {pos ? (
                <Text style={s.sub}>
                  ตำแหน่ง {pos.lat.toFixed(5)}, {pos.lng.toFixed(5)} (คลาดเคลื่อน ~{Math.round(pos.acc)} ม.)
                </Text>
              ) : null}
              <Btn title="ยืนยันเช็คชื่อ" onPress={submit} busy={!!step} />
              <Btn title="ถ่ายใหม่" outline small onPress={start} disabled={!!step} />
            </View>
          ) : (
            <Btn title="📍  เช็คชื่อเข้างาน" onPress={start} busy={!!step} style={{ minHeight: 64 }} />
          )}
          {step ? <Text style={[s.sub, { textAlign: 'center' }]}>{step}</Text> : null}
        </Card>
      ) : null}

      <Text style={s.foot}>ส่งรูปเช็คชื่อในกลุ่ม LINE เหมือนเดิมก็ได้ — ระบบนับอันที่มาก่อน</Text>
    </ScrollView>
  );
}

const s = StyleSheet.create({
  h2: { fontSize: 20, fontWeight: '800', color: C.text },
  sub: { fontSize: 14, color: C.sub, lineHeight: 21 },
  big: { fontSize: 44, color: C.green, fontWeight: '800' },
  time: { fontSize: 36, fontWeight: '800', color: C.text },
  pill: { borderRadius: 8, paddingHorizontal: 14, paddingVertical: 6 },
  pillT: { fontSize: 16, fontWeight: '800' },
  selfie: { width: '100%', aspectRatio: 3 / 4, borderRadius: 12, backgroundColor: C.purpleSoft },
  foot: { fontSize: 13, color: C.sub, textAlign: 'center' },
});
