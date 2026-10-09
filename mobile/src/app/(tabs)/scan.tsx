// สแกน QR ที่ติดรถ → เปิดหน้ารถ · QR ของระบบเป็นลิงก์ …/track/scan/<รหัสรถ>/
import { CameraView, useCameraPermissions } from 'expo-camera';
import { router, useFocusEffect } from 'expo-router';
import { useCallback, useRef, useState } from 'react';
import { Alert, StyleSheet, Text, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { Btn, C, Card, Loading } from '../../lib/ui';

/** ข้อความใน QR → รหัสรถ (ไม่ใช่ QR ของระบบ = '') */
function codeFrom(data: string): string {
  const s = (data || '').trim();
  const m = s.match(/\/track\/scan\/([^/?#\s]+)/);
  if (m) return decodeURIComponent(m[1]);
  if (/^[A-Za-z]{1,4}[0-9]{2,6}(-[0-9]+)?$/.test(s)) return s.toUpperCase(); // พิมพ์/QR รหัสรถตรงๆ
  return '';
}

export default function Scan() {
  const [perm, requestPerm] = useCameraPermissions();
  const [active, setActive] = useState(true);
  const [manual, setManual] = useState('');
  const lock = useRef(false);

  // กลับมาหน้านี้ = พร้อมสแกนคันถัดไป
  useFocusEffect(
    useCallback(() => {
      lock.current = false;
      setActive(true);
      return () => setActive(false);
    }, []),
  );

  const open = (code: string) => {
    lock.current = true;
    setActive(false);
    router.push({ pathname: '/car/[code]', params: { code } });
  };

  const onScan = ({ data }: { data: string }) => {
    if (lock.current) return;
    const code = codeFrom(data);
    lock.current = true;
    if (!code) {
      Alert.alert('QR นี้ไม่ใช่ของรถในระบบ', data.slice(0, 120), [
        { text: 'สแกนใหม่', onPress: () => (lock.current = false) },
      ]);
      return;
    }
    open(code);
  };

  if (!perm) return <Loading />;

  return (
    <SafeAreaView style={{ flex: 1 }} edges={[]}>
      {perm.granted ? (
        <View style={st.camWrap}>
          {active ? (
            <CameraView
              style={StyleSheet.absoluteFill}
              facing="back"
              barcodeScannerSettings={{ barcodeTypes: ['qr'] }}
              onBarcodeScanned={onScan}
            />
          ) : null}
          <View style={st.frame} pointerEvents="none" />
          <Text style={st.camHint}>เล็ง QR ที่ติดรถให้อยู่ในกรอบ</Text>
        </View>
      ) : (
        <View style={{ padding: 20, gap: 12 }}>
          <Card>
            <Text style={{ fontSize: 16, color: C.text, lineHeight: 24 }}>
              ต้องอนุญาตให้แอปใช้กล้องก่อน ถึงจะสแกน QR ได้
            </Text>
          </Card>
          <Btn title="อนุญาตใช้กล้อง" onPress={requestPerm} />
        </View>
      )}
      <View style={st.manual}>
        <TextInput
          style={st.input}
          value={manual}
          onChangeText={setManual}
          placeholder="หรือพิมพ์รหัสรถ เช่น CS0011"
          placeholderTextColor={C.sub}
          autoCapitalize="characters"
          autoCorrect={false}
          returnKeyType="go"
          onSubmitEditing={() => manual.trim() && open(manual.trim().toUpperCase())}
        />
        <Btn title="เปิด" small onPress={() => manual.trim() && open(manual.trim().toUpperCase())} />
      </View>
    </SafeAreaView>
  );
}

const st = StyleSheet.create({
  camWrap: { flex: 1, backgroundColor: '#000', alignItems: 'center', justifyContent: 'center' },
  frame: { width: 240, height: 240, borderWidth: 3, borderColor: '#fff', borderRadius: 16 },
  camHint: { position: 'absolute', bottom: 24, color: '#fff', fontSize: 16, fontWeight: '600' },
  manual: { flexDirection: 'row', gap: 8, padding: 12, backgroundColor: '#fff' },
  input: {
    flex: 1,
    minHeight: 42,
    borderWidth: 1,
    borderColor: C.line,
    borderRadius: 8,
    paddingHorizontal: 12,
    fontSize: 16,
    color: C.text,
    backgroundColor: C.bg,
  },
});
