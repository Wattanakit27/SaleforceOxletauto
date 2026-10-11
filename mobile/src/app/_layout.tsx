import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { AuthProvider } from '../lib/auth';
import { C } from '../lib/ui';

// โครงหน้า: (tabs) = แชท · วันนี้ · ห้องพัก (แอดมิน) · รถ · ฉัน — จัดตามบทบาท (ดู (tabs)/_layout.tsx)
//           chat/[id] · lead/[id] (งานกับลูกค้า) · alerts · scan · car/[code] เปิดซ้อนเต็มจอเหนือแถบด้านล่าง
export default function RootLayout() {
  return (
    <SafeAreaProvider>
      <AuthProvider>
        <StatusBar style="dark" />
        <Stack
          screenOptions={{
            headerTintColor: C.purple,
            headerTitleStyle: { color: C.text, fontWeight: '700' },
            headerBackTitle: 'กลับ',
            contentStyle: { backgroundColor: C.bg },
          }}>
          <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
          <Stack.Screen name="login" options={{ headerShown: false }} />
          <Stack.Screen name="chat/[id]" options={{ title: 'แชท' }} />
          <Stack.Screen name="lead/[id]" options={{ title: 'งานกับลูกค้า' }} />
          <Stack.Screen name="alerts" options={{ title: 'แจ้งเตือน' }} />
          <Stack.Screen name="car/[code]" options={{ title: 'รถ' }} />
          <Stack.Screen name="scan" options={{ title: 'สแกน QR รถ' }} />
          <Stack.Screen name="auth" options={{ headerShown: false }} />
        </Stack>
      </AuthProvider>
    </SafeAreaProvider>
  );
}
