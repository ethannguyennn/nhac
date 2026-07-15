import { Link } from 'expo-router';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { theme } from '../src/theme';

/**
 * Library / home screen.
 * TODO: fetch concerts via api.listConcerts(); render real cards + demo data.
 * For now this is a static shell so the app boots and navigates.
 */
export default function LibraryScreen() {
  const insets = useSafeAreaInsets();

  return (
    <View style={styles.container}>
      <ScrollView contentContainerStyle={{ padding: theme.spacing(2), paddingBottom: insets.bottom + 96 }}>
        <Text style={styles.hero}>Relive the moment.</Text>
        <Text style={styles.subtitle}>
          Your concert clips, identified and organized into replayable sets.
        </Text>

        {/* Placeholder concert cards — replace with fetched data. */}
        {DEMO_CONCERTS.map((c) => (
          <Link key={c.id} href={`/concert/${c.id}`} asChild>
            <Pressable style={styles.card}>
              <View style={styles.cardArt} />
              <View style={{ flex: 1 }}>
                <Text style={styles.cardTitle}>{c.title}</Text>
                <Text style={styles.cardMeta}>
                  {c.venue} · {c.date}
                </Text>
              </View>
            </Pressable>
          </Link>
        ))}
      </ScrollView>

      <Link href="/upload" asChild>
        <Pressable style={[styles.fab, { bottom: insets.bottom + 20 }]}>
          <Text style={styles.fabText}>＋ Upload</Text>
        </Pressable>
      </Link>
    </View>
  );
}

const DEMO_CONCERTS = [
  { id: 'demo-1', title: 'Beabadoobee', venue: 'The Fonda', date: 'Oct 2024' },
  { id: 'demo-2', title: 'Phoenix', venue: 'Greek Theatre', date: 'Aug 2024' },
];

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: theme.colors.bg },
  hero: { color: theme.colors.text, fontSize: 30, fontWeight: '800', marginTop: theme.spacing(1) },
  subtitle: { color: theme.colors.textMuted, fontSize: 15, marginTop: 6, marginBottom: theme.spacing(3) },
  card: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: theme.spacing(1.5),
    backgroundColor: theme.colors.surface,
    borderRadius: theme.radius.md,
    borderWidth: 1,
    borderColor: theme.colors.border,
    padding: theme.spacing(1.5),
    marginBottom: theme.spacing(1.5),
  },
  cardArt: { width: 56, height: 56, borderRadius: theme.radius.sm, backgroundColor: theme.colors.accent },
  cardTitle: { color: theme.colors.text, fontSize: 17, fontWeight: '700' },
  cardMeta: { color: theme.colors.textMuted, fontSize: 13, marginTop: 2 },
  fab: {
    position: 'absolute',
    right: theme.spacing(2),
    backgroundColor: theme.colors.accent,
    paddingHorizontal: theme.spacing(2.5),
    paddingVertical: theme.spacing(1.5),
    borderRadius: theme.radius.lg,
  },
  fabText: { color: '#1a1206', fontWeight: '800', fontSize: 16 },
});
