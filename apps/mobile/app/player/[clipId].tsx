import { useLocalSearchParams } from 'expo-router';
import { StyleSheet, Text, View } from 'react-native';
import { theme } from '../../src/theme';

/**
 * Playback screen. MVP plays the clip's video (expo-av <Video>) with a warm
 * gradient/visualizer behind it.
 * TODO: fetch clip + presigned playback URL from GET /clips/:id, then render
 *       <Video source={{ uri }} /> with basic controls. Keeping this a visual
 *       shell for now so the scaffold has no runtime media dependency.
 */
export default function PlayerScreen() {
  const { clipId } = useLocalSearchParams<{ clipId: string }>();

  return (
    <View style={styles.container}>
      <View style={styles.stage}>
        <Text style={styles.placeholder}>▶</Text>
      </View>
      <Text style={styles.title}>Now playing</Text>
      <Text style={styles.meta}>clip {clipId}</Text>
      <Text style={styles.note}>
        Video player + audio-reactive visualizer render here (expo-av). Wire to GET /clips/:id.
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: theme.colors.bg, padding: theme.spacing(2), alignItems: 'center' },
  stage: {
    width: '100%',
    aspectRatio: 9 / 16,
    maxHeight: 420,
    borderRadius: theme.radius.lg,
    backgroundColor: theme.colors.surfaceAlt,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: theme.spacing(2),
  },
  placeholder: { color: theme.colors.accent, fontSize: 56 },
  title: { color: theme.colors.text, fontSize: 20, fontWeight: '800', marginTop: theme.spacing(3) },
  meta: { color: theme.colors.textMuted, fontSize: 13, marginTop: 4 },
  note: { color: theme.colors.textMuted, fontSize: 12, textAlign: 'center', marginTop: theme.spacing(3), lineHeight: 18 },
});
