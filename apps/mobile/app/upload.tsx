import { useState } from 'react';
import * as ImagePicker from 'expo-image-picker';
import { router } from 'expo-router';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';
import { api } from '../src/lib/api';
import { theme } from '../src/theme';

type Phase = 'idle' | 'uploading' | 'processing' | 'done' | 'error';

/**
 * Upload flow: pick video → get presigned URL → PUT to R2 → complete → process.
 * Wired against the real API client; needs a running API + storage to fully work.
 */
export default function UploadScreen() {
  const [phase, setPhase] = useState<Phase>('idle');
  const [message, setMessage] = useState<string>('');

  async function pickAndUpload() {
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ImagePicker.MediaTypeOptions.Videos,
      quality: 1,
    });
    if (result.canceled || !result.assets[0]) return;
    const asset = result.assets[0];

    try {
      setPhase('uploading');
      setMessage('Getting upload URL…');
      const { clipId, uploadUrl } = await api.createUpload({
        fileName: asset.fileName ?? `clip-${Date.now()}.mp4`,
        mimeType: asset.mimeType ?? 'video/mp4',
        sizeBytes: asset.fileSize ?? 0,
        durationSeconds: asset.duration ? asset.duration / 1000 : undefined,
      });

      setMessage('Uploading your clip…');
      await api.uploadToStorage(uploadUrl, asset.uri, asset.mimeType ?? 'video/mp4');

      setPhase('processing');
      setMessage('Identifying the song…');
      const { identified } = await api.completeUpload({ clipId });

      setPhase('done');
      setMessage(identified ? 'Song identified! 🎶' : 'Couldn’t auto-detect — tag it manually.');
      // TODO: if !identified, route to a manual-tag screen for clipId.
      setTimeout(() => router.back(), 1200);
    } catch (err) {
      setPhase('error');
      setMessage(err instanceof Error ? err.message : 'Upload failed');
    }
  }

  const busy = phase === 'uploading' || phase === 'processing';

  return (
    <View style={styles.container}>
      <Text style={styles.title}>Add a concert clip</Text>
      <Text style={styles.body}>
        Pick a video from your camera roll. Nhạc will pull the audio, find the song, and file it
        under the right show.
      </Text>

      <Pressable style={[styles.button, busy && styles.buttonDisabled]} disabled={busy} onPress={pickAndUpload}>
        {busy ? <ActivityIndicator color="#1a1206" /> : <Text style={styles.buttonText}>Choose a video</Text>}
      </Pressable>

      {!!message && <Text style={styles.status}>{message}</Text>}

      <Text style={styles.disclaimer}>
        For personal use. You’re responsible for the footage you upload and share.
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: theme.colors.bg, padding: theme.spacing(3), gap: theme.spacing(2) },
  title: { color: theme.colors.text, fontSize: 24, fontWeight: '800' },
  body: { color: theme.colors.textMuted, fontSize: 15, lineHeight: 21 },
  button: {
    backgroundColor: theme.colors.accent,
    borderRadius: theme.radius.md,
    paddingVertical: theme.spacing(2),
    alignItems: 'center',
    marginTop: theme.spacing(1),
  },
  buttonDisabled: { opacity: 0.6 },
  buttonText: { color: '#1a1206', fontWeight: '800', fontSize: 16 },
  status: { color: theme.colors.text, fontSize: 15, textAlign: 'center' },
  disclaimer: { color: theme.colors.textMuted, fontSize: 12, marginTop: 'auto', textAlign: 'center' },
});
