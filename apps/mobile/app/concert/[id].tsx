import { Link, useLocalSearchParams } from 'expo-router';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { theme } from '../../src/theme';

/**
 * Concert detail — the "album" view: songs identified from this show, each a
 * row that opens the player.
 * TODO: fetch ConcertWithClips from GET /concerts/:id.
 */
export default function ConcertScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();

  return (
    <ScrollView style={styles.container} contentContainerStyle={{ padding: theme.spacing(2) }}>
      <View style={styles.header}>
        <View style={styles.art} />
        <Text style={styles.title}>Concert {id}</Text>
        <Text style={styles.meta}>Tap a song to relive it</Text>
      </View>

      {DEMO_TRACKS.map((t, i) => (
        <Link key={t.clipId} href={`/player/${t.clipId}`} asChild>
          <Pressable style={styles.row}>
            <Text style={styles.index}>{i + 1}</Text>
            <View style={{ flex: 1 }}>
              <Text style={styles.song}>{t.title}</Text>
              <Text style={styles.artist}>{t.artist}</Text>
            </View>
            <Text style={styles.duration}>{t.duration}</Text>
          </Pressable>
        </Link>
      ))}
    </ScrollView>
  );
}

const DEMO_TRACKS = [
  { clipId: 'demo-clip-1', title: 'Coffee', artist: 'Beabadoobee', duration: '2:41' },
  { clipId: 'demo-clip-2', title: 'The Perfect Pair', artist: 'Beabadoobee', duration: '3:12' },
];

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: theme.colors.bg },
  header: { alignItems: 'center', marginBottom: theme.spacing(3) },
  art: { width: 140, height: 140, borderRadius: theme.radius.lg, backgroundColor: theme.colors.accent },
  title: { color: theme.colors.text, fontSize: 22, fontWeight: '800', marginTop: theme.spacing(2) },
  meta: { color: theme.colors.textMuted, fontSize: 13, marginTop: 4 },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: theme.spacing(1.5),
    paddingVertical: theme.spacing(1.5),
    borderBottomWidth: 1,
    borderBottomColor: theme.colors.border,
  },
  index: { color: theme.colors.textMuted, width: 20, textAlign: 'center', fontSize: 15 },
  song: { color: theme.colors.text, fontSize: 16, fontWeight: '600' },
  artist: { color: theme.colors.textMuted, fontSize: 13, marginTop: 2 },
  duration: { color: theme.colors.textMuted, fontSize: 13 },
});
