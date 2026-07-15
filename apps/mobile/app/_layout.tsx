import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { theme } from '../src/theme';

export default function RootLayout() {
  return (
    <SafeAreaProvider>
      <StatusBar style="light" />
      <Stack
        screenOptions={{
          headerStyle: { backgroundColor: theme.colors.bg },
          headerTintColor: theme.colors.text,
          contentStyle: { backgroundColor: theme.colors.bg },
        }}
      >
        <Stack.Screen name="index" options={{ title: 'Nhạc' }} />
        <Stack.Screen name="upload" options={{ title: 'Upload a clip', presentation: 'modal' }} />
        <Stack.Screen name="concert/[id]" options={{ title: 'Concert' }} />
        <Stack.Screen name="player/[clipId]" options={{ title: 'Now playing' }} />
      </Stack>
    </SafeAreaProvider>
  );
}
