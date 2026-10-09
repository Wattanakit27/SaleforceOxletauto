import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { AuthProvider } from '../lib/auth';
import { C } from '../lib/ui';

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
          <Stack.Screen name="index" options={{ title: 'Oxlet' }} />
          <Stack.Screen name="chat/index" options={{ title: 'แชทลูกค้า' }} />
          <Stack.Screen name="chat/[id]" options={{ title: 'แชท' }} />
          <Stack.Screen name="scan" options={{ title: 'สแกน QR รถ' }} />
          <Stack.Screen name="car/[code]" options={{ title: 'รถ' }} />
          <Stack.Screen name="auth" options={{ headerShown: false }} />
        </Stack>
      </AuthProvider>
    </SafeAreaProvider>
  );
}
