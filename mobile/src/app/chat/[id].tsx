// หน้าแชทลูกค้า 1 คน — อ่าน/ตอบ/รับลูกค้า ผ่าน API เดิมของ Connect
// ส่งได้หรือไม่ (canReply/replyOn/replyWhy) เซิร์ฟเวอร์ตัดสินทั้งหมด แอปแค่โชว์ตามนั้น
import { Stack, useFocusEffect, useLocalSearchParams } from 'expo-router';
import { useCallback, useRef, useState } from 'react';
import {
  Alert,
  FlatList,
  KeyboardAvoidingView,
  Platform,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { api } from '../../lib/api';
import { Banner, Btn, C, fmtTime, Loading } from '../../lib/ui';

type Msg = { at: string; text: string; type: string; media: boolean; dir: string; by: string };
type Chat = {
  row: { id: number; name: string; owner: string; sim: boolean; src: string; overdue: boolean; awaiting: boolean };
  access: 'full' | 'preview';
  messages: Msg[];
  canClaim: boolean;
  canReply: boolean;
  canDismiss: boolean;
  replyOn: boolean;
  replyWhy: string;
  profile?: { phones?: string[] };
};

export default function ChatScreen() {
  const { id, name } = useLocalSearchParams<{ id: string; name?: string }>();
  const [d, setD] = useState<Chat | null>(null);
  const [err, setErr] = useState('');
  const [text, setText] = useState('');
  const [sending, setSending] = useState(false);
  const [claiming, setClaiming] = useState(false);
  const confirmed = useRef(false); // ถามยืนยันครั้งแรกที่ตอบลูกค้าจริง (เวอร์ชันทดลอง)

  const load = useCallback(async () => {
    try {
      const r = await api<Chat>(`/connect/api/chat?id=${encodeURIComponent(String(id))}`);
      setD(r);
      setErr('');
    } catch (e: any) {
      setErr(e?.message || 'เปิดแชทไม่สำเร็จ');
    }
  }, [id]);

  useFocusEffect(
    useCallback(() => {
      load();
      const t = setInterval(load, 5000);
      return () => clearInterval(t);
    }, [load]),
  );

  const claim = async () => {
    setClaiming(true);
    try {
      await api('/connect/api/claim', { body: { id: Number(id) } });
      await load();
    } catch (e: any) {
      Alert.alert('รับลูกค้าไม่สำเร็จ', e?.message || '');
    } finally {
      setClaiming(false);
    }
  };

  const doSend = async () => {
    const t = text.trim();
    if (!t) return;
    setSending(true);
    try {
      const r = await api<{ message: Msg }>('/connect/api/reply', { body: { id: Number(id), text: t } });
      setText('');
      setD((cur) => (cur ? { ...cur, messages: [...cur.messages, r.message] } : cur));
      load();
    } catch (e: any) {
      Alert.alert('ส่งไม่สำเร็จ', e?.message || ''); // ข้อความยังอยู่ในช่อง ไม่ต้องพิมพ์ใหม่
    } finally {
      setSending(false);
    }
  };

  const send = () => {
    if (!text.trim() || sending) return;
    if (d && !d.row.sim && !confirmed.current) {
      Alert.alert('ส่งหาลูกค้าจริง?', 'ข้อความนี้จะถูกส่งเข้า LINE/Facebook ของลูกค้าจริง', [
        { text: 'ยกเลิก', style: 'cancel' },
        {
          text: 'ส่ง',
          onPress: () => {
            confirmed.current = true;
            doSend();
          },
        },
      ]);
      return;
    }
    doSend();
  };

  const title = d?.row?.name || name || 'แชท';
  const msgs = d ? [...d.messages].reverse() : [];

  return (
    <SafeAreaView style={{ flex: 1 }} edges={['bottom']}>
      <Stack.Screen options={{ title }} />
      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        keyboardVerticalOffset={Platform.OS === 'ios' ? 90 : 0}>
        {err && !d ? (
          <View style={{ padding: 12 }}>
            <Banner text={err} kind="err" />
          </View>
        ) : !d ? (
          <Loading />
        ) : (
          <>
            <View style={st.info}>
              <Text style={st.infoText} numberOfLines={1}>
                {d.row.src === 'fb' ? 'Facebook' : 'LINE'}
                {d.row.owner ? ` · ดูแลโดย @${d.row.owner}` : ' · ยังไม่มีคนรับ'}
                {d.row.overdue ? ' · เลยเวลาตอบ' : d.row.awaiting ? ' · รอตอบ' : ''}
              </Text>
            </View>
            {d.access === 'preview' ? (
              <View style={{ paddingHorizontal: 12, paddingTop: 8 }}>
                <Banner kind="info" text={'คิวรอรับ — เห็นแค่ข้อความล่าสุดของลูกค้า กด "รับลูกค้า" เพื่อดูทั้งหมดและตอบ'} />
              </View>
            ) : null}
            <FlatList
              inverted
              data={msgs}
              keyExtractor={(m, i) => `${m.at}-${i}`}
              contentContainerStyle={{ padding: 12, gap: 8 }}
              renderItem={({ item: m }) => {
                const out = m.dir === 'out';
                return (
                  <View style={[st.bubbleWrap, out ? { alignItems: 'flex-end' } : { alignItems: 'flex-start' }]}>
                    <View style={[st.bubble, out ? st.out : st.in]}>
                      <Text style={[st.msg, out && { color: '#fff' }, m.media && { fontStyle: 'italic' }]}>
                        {m.text || (m.media ? '[รูป/ไฟล์]' : '')}
                      </Text>
                    </View>
                    <Text style={st.meta}>
                      {fmtTime(m.at)}
                      {out && m.by ? ` · ${m.by}` : ''}
                    </Text>
                  </View>
                );
              }}
            />
            <View style={st.bar}>
              {d.canClaim ? (
                <Btn title="รับลูกค้าคนนี้" onPress={claim} busy={claiming} />
              ) : d.canReply && d.replyOn ? (
                <View style={st.inputRow}>
                  <TextInput
                    style={st.input}
                    value={text}
                    onChangeText={setText}
                    placeholder="พิมพ์ข้อความ…"
                    placeholderTextColor={C.sub}
                    multiline
                  />
                  <Btn title="ส่ง" onPress={send} busy={sending} disabled={!text.trim()} small style={{ minWidth: 64 }} />
                </View>
              ) : (
                <Banner
                  kind="warn"
                  text={
                    d.replyWhy ||
                    (d.canReply
                      ? 'ยังล็อกการส่งข้อความหาลูกค้าอยู่ (ตั้งที่เซิร์ฟเวอร์)'
                      : 'ตอบได้เฉพาะลูกค้าที่คุณรับไว้')
                  }
                />
              )}
            </View>
          </>
        )}
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const st = StyleSheet.create({
  info: { backgroundColor: '#fff', paddingHorizontal: 14, paddingVertical: 8, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: C.line },
  infoText: { color: C.sub, fontSize: 13 },
  bubbleWrap: { maxWidth: '100%' },
  bubble: { maxWidth: '82%', borderRadius: 14, paddingHorizontal: 12, paddingVertical: 8 },
  in: { backgroundColor: '#fff', borderWidth: StyleSheet.hairlineWidth, borderColor: C.line, borderBottomLeftRadius: 4 },
  out: { backgroundColor: C.purple, borderBottomRightRadius: 4 },
  msg: { fontSize: 16, color: C.text, lineHeight: 22 },
  meta: { fontSize: 11, color: C.sub, marginTop: 2, marginHorizontal: 4 },
  bar: { padding: 10, backgroundColor: '#fff', borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: C.line },
  inputRow: { flexDirection: 'row', alignItems: 'flex-end', gap: 8 },
  input: {
    flex: 1,
    minHeight: 42,
    maxHeight: 120,
    borderWidth: 1,
    borderColor: C.line,
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingTop: 10,
    paddingBottom: 10,
    fontSize: 16,
    color: C.text,
    backgroundColor: C.bg,
  },
});
