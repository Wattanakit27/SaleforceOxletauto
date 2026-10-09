import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { AuthProvider } from '../lib/auth';
import { C } from '../lib/ui';

// โครงหน้า: (tabs) = แชท · สแกน QR · ฉัน (หน้าแรกหลัง login = แชท)
//           chat/[id] กับ car/[code] เปิดซ้อนเต็มจอเหนือแถบด้านล่าง
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
          <Stack.Screen name="car/[code]" options={{ title: 'รถ' }} />
          <Stack.Screen name="auth" options={{ headerShown: false }} />
        </Stack>
      </AuthProvider>
    </SafeAreaProvider>
  );
}
