// ชิ้นส่วนหน้าตาที่ใช้ร่วมกัน — โทนม่วงขาวของบริษัท (ห้ามเปลี่ยนเป็นดำขาว)
import { ReactNode } from 'react';
import {
  ActivityIndicator,
  Image,
  Pressable,
  StyleProp,
  StyleSheet,
  Text,
  View,
  ViewStyle,
} from 'react-native';

export const C = {
  purple: '#7c3aed',
  purpleSoft: '#ede9fe',
  bg: '#f5f3ff',
  card: '#ffffff',
  text: '#1f1147',
  sub: '#6b6488',
  line: '#e4e0f5',
  red: '#dc2626',
  redBg: '#fee2e2',
  amber: '#b45309',
  amberBg: '#fef3c7',
  green: '#15803d',
  greenBg: '#dcfce7',
  lineGreen: '#06C755',
  fb: '#1877f2',
};

export function Btn({
  title,
  onPress,
  color = C.purple,
  outline,
  disabled,
  busy,
  style,
  small,
}: {
  title: string;
  onPress?: () => void;
  color?: string;
  outline?: boolean;
  disabled?: boolean;
  busy?: boolean;
  style?: StyleProp<ViewStyle>;
  small?: boolean;
}) {
  const off = disabled || busy;
  return (
    <Pressable
      onPress={off ? undefined : onPress}
      style={({ pressed }) => [
        s.btn,
        small && s.btnSmall,
        outline
          ? { borderColor: color, borderWidth: 1.5, backgroundColor: '#fff' }
          : { backgroundColor: color },
        (pressed || off) && { opacity: off ? 0.5 : 0.8 },
        style,
      ]}>
      {busy ? (
        <ActivityIndicator color={outline ? color : '#fff'} />
      ) : (
        <Text style={[s.btnText, small && { fontSize: 14 }, { color: outline ? color : '#fff' }]}>
          {title}
        </Text>
      )}
    </Pressable>
  );
}

export function Card({ children, style }: { children: ReactNode; style?: StyleProp<ViewStyle> }) {
  return <View style={[s.card, style]}>{children}</View>;
}

export function Banner({ text, kind = 'warn' }: { text: string; kind?: 'warn' | 'err' | 'info' }) {
  const bg = kind === 'err' ? C.redBg : kind === 'info' ? C.purpleSoft : C.amberBg;
  const fg = kind === 'err' ? C.red : kind === 'info' ? C.purple : C.amber;
  return (
    <View style={[s.banner, { backgroundColor: bg }]}>
      <Text style={{ color: fg, fontSize: 14, lineHeight: 20 }}>{text}</Text>
    </View>
  );
}

export function Avatar({ name, pic, size = 44 }: { name: string; pic?: string; size?: number }) {
  const ch = (name || '?').trim().charAt(0).toUpperCase() || '?';
  return (
    <View
      style={{
        width: size,
        height: size,
        borderRadius: size / 2,
        backgroundColor: C.purpleSoft,
        alignItems: 'center',
        justifyContent: 'center',
        overflow: 'hidden',
      }}>
      <Text style={{ color: C.purple, fontWeight: '700', fontSize: size * 0.4 }}>{ch}</Text>
      {pic ? (
        <Image source={{ uri: pic }} style={StyleSheet.absoluteFill} resizeMode="cover" />
      ) : null}
    </View>
  );
}

export function Tag({ text, color = C.purple, bg = C.purpleSoft }: { text: string; color?: string; bg?: string }) {
  return (
    <View style={[s.tag, { backgroundColor: bg }]}>
      <Text style={{ color, fontSize: 11, fontWeight: '700' }}>{text}</Text>
    </View>
  );
}

export function Loading({ text = 'กำลังโหลด…' }: { text?: string }) {
  return (
    <View style={{ padding: 40, alignItems: 'center', gap: 10 }}>
      <ActivityIndicator color={C.purple} />
      <Text style={{ color: C.sub }}>{text}</Text>
    </View>
  );
}

const pad = (n: number) => String(n).padStart(2, '0');

/** วันนี้ = 14:05 · วันอื่น = 8/10 14:05 */
export function fmtTime(iso?: string | null): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return '';
  const now = new Date();
  const hm = `${pad(d.getHours())}:${pad(d.getMinutes())}`;
  if (d.toDateString() === now.toDateString()) return hm;
  return `${d.getDate()}/${d.getMonth() + 1} ${hm}`;
}

const s = StyleSheet.create({
  btn: {
    minHeight: 50,
    borderRadius: 8,
    paddingHorizontal: 16,
    alignItems: 'center',
    justifyContent: 'center',
  },
  btnSmall: { minHeight: 38, paddingHorizontal: 12 },
  btnText: { fontSize: 16, fontWeight: '700' },
  card: {
    backgroundColor: C.card,
    borderRadius: 12,
    padding: 16,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
  },
  banner: { borderRadius: 8, padding: 12 },
  tag: { borderRadius: 5, paddingHorizontal: 6, paddingVertical: 2 },
});
