-- ═══════════════════════════════════════════════════════════════════════════
-- Nhạc — demo seed (cold-start "demo mode")
-- Gives new users something alive to explore before they upload anything.
--
-- NOTE: seeding demo concerts/clips needs a demo owner profile. Because
-- profiles.id references auth.users, create a demo auth user first (via the
-- Supabase dashboard or admin API), then set :demo_user below.
--   psql: \set demo_user 'REPLACE-WITH-DEMO-AUTH-UID'
-- Demo rows use placeholder storage keys; wire real sample media later.
-- ═══════════════════════════════════════════════════════════════════════════

-- \set demo_user 'REPLACE-WITH-DEMO-AUTH-UID'

insert into songs (title, artist, album, artwork_url) values
  ('Coffee', 'Beabadoobee', 'Loveworm', null),
  ('The Perfect Pair', 'Beabadoobee', 'Beatopia', null),
  ('Lisztomania', 'Phoenix', 'Wolfgang Amadeus Phoenix', null)
on conflict (title, artist) do nothing;

-- Example concert (uncomment after setting :demo_user):
-- insert into concerts (id, owner_id, title, artist, venue, city, performed_on, is_demo)
-- values (
--   '00000000-0000-0000-0000-0000000000c1', :'demo_user',
--   'Beabadoobee — The Fonda', 'Beabadoobee', 'The Fonda Theatre', 'Los Angeles',
--   '2024-10-12', true
-- );
