// หน้าแชทลูกค้า 1 คน — อ่าน/ตอบ/รับลูกค้า ผ่าน API เดิมของ Connect
// ส่งได้หรือไม่ (canReply/replyOn/replyWhy) เซิร์ฟเวอร์ตัดสินทั้งหมด แอปแค่โชว์ตามนั้น
import { router, Stack, useFocusEffect, useLocalSearchParams } from 'expo-router';
import { useCallback, useRef, useState } from 'react';
import {
  Alert,
  FlatList,
  Image,
  KeyboardAvoidingView,
  Modal,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { absUrl, api, authHeaders } from '../../lib/api';
import { Extra, HEAT } from '../../lib/crm';
import { Banner, Btn, C, fmtTime, Loading } from '../../lib/ui';

// ★ 11 ต.ค.69 รูป/ไฟล์ที่ลูกค้าส่ง — url = /connect/api/media (ต้องแนบ token · เซิร์ฟเวอร์เช็คสิทธิ์)
type MFile = { url: string; kind: string; state: string; name: string; size: number; ext: string };
type Msg = { at: string; text: string; type: string; media: boolean; dir: string; by: string; files?: MFile[] };

const FILE_NOTE: Record<string, string> = {
  gone: 'ไฟล์นี้หมดอายุที่ต้นทางแล้ว — เปิดดูในแอป LINE OA / Facebook',
  big: 'ไฟล์ใหญ่เกินที่ระบบเก็บ — เปิดดูในแอป LINE OA / Facebook',
  none: 'ข้อความนี้ไม่มีไฟล์ให้โหลด',
};

/** รูปในบับเบิล — โหลดไม่ขึ้น (หมดอายุที่ต้นทาง) = บอกเหตุผลแทนกรอบว่าง */
function ChatImage({ uri, onOpen }: { uri: string; onOpen: () => void }) {
  const [bad, setBad] = useState(false);
  if (bad) return <Text style={st.note}>เปิดรูปนี้ไม่ได้ — ไฟล์อาจหมดอายุที่ต้นทางแล้ว</Text>;
  return (
    <Pressable onPress={onOpen}>
      <Image source={{ uri, headers: authHeaders() }} style={st.img} resizeMode="cover" onError={() => setBad(true)} />
    </Pressable>
  );
}
type Chat = {
  row: Extra & { id: number; name: string; owner: string; sim: boolean; src: string; overdue: boolean; awaiting: boolean };
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
  const [viewer, setViewer] = useState('');
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
      <Stack.Screen
        options={{
          title,
          // ★ 11 ต.ค.69 งานกับลูกค้า: ขั้นของลีด · นัด · บันทึกการโทร · สรุป (เฉพาะคนที่เห็นแชทเต็ม)
          headerRight: () =>
            d?.access === 'full' ? (
              <Pressable
                hitSlop={10}
                onPress={() => router.push({ pathname: '/lead/[id]', params: { id: String(id) } })}
                style={{ paddingHorizontal: 6 }}>
                <Text style={{ color: C.purple, fontWeight: '700', fontSize: 15 }}>งาน/นัด</Text>
              </Pressable>
            ) : null,
        }}
      />
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
              {d.access === 'full' && d.row.stageLabel ? (
                <Pressable onPress={() => router.push({ pathname: '/lead/[id]', params: { id: String(id) } })}>
                  <Text style={[st.infoText, { color: C.purple, marginTop: 2 }]} numberOfLines={1}>
                    ขั้น: {d.row.stageLabel}
                    {d.row.heat ? ` · ${HEAT[d.row.heat][0]}` : ''}
                    {d.row.appt ? ` · ${d.row.appt.kind === 'viewing' ? 'นัดดูรถ' : 'นัด'} ${fmtTime(d.row.appt.due)}` : ''} · แตะเพื่อบันทึกงาน ›
                  </Text>
                </Pressable>
              ) : null}
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
                const files = m.files || [];
                // "[รูป]" คือคำแทนตอนไม่มีไฟล์ให้ดู — มีไฟล์แล้วไม่ต้องโชว์ (ข้อความจริงที่พิมพ์มาพร้อมรูปยังโชว์)
                const showText = !files.length || !/^\[[^\]]*\]$/.test((m.text || '').trim());
                return (
                  <View style={[st.bubbleWrap, out ? { alignItems: 'flex-end' } : { alignItems: 'flex-start' }]}>
                    <View style={[st.bubble, out ? st.out : st.in, files.length ? st.withFile : null]}>
                      {showText ? (
                        <Text style={[st.msg, out && { color: '#fff' }, m.media && !files.length && { fontStyle: 'italic' }]}>
                          {m.text || (m.media ? '[รูป/ไฟล์]' : '')}
                        </Text>
                      ) : null}
                      {files.map((f, i) =>
                        FILE_NOTE[f.state] ? (
                          <Text key={i} style={[st.note, out && { color: '#fff' }]}>{FILE_NOTE[f.state]}</Text>
                        ) : f.kind === 'image' ? (
                          <ChatImage key={i} uri={absUrl(f.url)} onOpen={() => setViewer(absUrl(f.url))} />
                        ) : (
                          <Text key={i} style={[st.note, out && { color: '#fff' }]}>
                            {f.kind === 'video' ? 'วิดีโอ' : f.kind === 'audio' ? 'ข้อความเสียง' : 'ไฟล์ ' + (f.name || '')} — เปิดดูได้ที่หน้าเว็บ Connect
                          </Text>
                        ),
                      )}
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
      <Modal visible={!!viewer} transparent animationType="fade" onRequestClose={() => setViewer('')}>
        <Pressable style={st.viewer} onPress={() => setViewer('')}>
          {viewer ? (
            <Image source={{ uri: viewer, headers: authHeaders() }} style={st.viewerImg} resizeMode="contain" />
          ) : null}
          <Text style={st.viewerHint}>แตะเพื่อปิด</Text>
        </Pressable>
      </Modal>
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
  withFile: { paddingHorizontal: 5, paddingVertical: 5, gap: 4 },
  img: { width: 220, height: 220, borderRadius: 10, backgroundColor: C.bg },
  note: { fontSize: 13, color: C.sub, fontStyle: 'italic', paddingHorizontal: 6, paddingVertical: 3 },
  viewer: { flex: 1, backgroundColor: 'rgba(0,0,0,0.92)', alignItems: 'center', justifyContent: 'center' },
  viewerImg: { width: '100%', height: '85%' },
  viewerHint: { color: '#ddd', marginTop: 10, fontSize: 14 },
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
