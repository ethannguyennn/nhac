-- ═══════════════════════════════════════════════════════════════════════════
-- Nhạc — initial schema (0001)
-- Postgres / Supabase. Enum values mirror packages/shared/src/enums.ts.
-- Apply with: supabase db push   (or paste into the SQL editor)
-- ═══════════════════════════════════════════════════════════════════════════

create extension if not exists "pgcrypto"; -- gen_random_uuid()

-- ─── Enums ───────────────────────────────────────────────────────────────────
create type clip_status as enum (
  'uploading', 'processing', 'identified', 'unidentified', 'manually_tagged', 'failed'
);
create type match_source as enum ('fingerprint', 'manual', 'inherited');
create type fingerprint_provider as enum ('audd', 'acrcloud', 'acoustid');
create type concert_role as enum ('owner', 'contributor', 'viewer');
create type playlist_type as enum ('concert', 'greatest_hits', 'custom');

-- ─── Helper: keep updated_at fresh ───────────────────────────────────────────
create or replace function set_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end; $$;

-- ─── profiles (1:1 with auth.users) ──────────────────────────────────────────
create table profiles (
  id           uuid primary key references auth.users (id) on delete cascade,
  username     text unique,
  display_name text,
  avatar_url   text,
  created_at   timestamptz not null default now()
);

-- ─── songs (deduped canonical tracks) ────────────────────────────────────────
create table songs (
  id           uuid primary key default gen_random_uuid(),
  title        text not null,
  artist       text not null,
  album        text,
  artwork_url  text,
  isrc         text,
  external_ids jsonb not null default '{}'::jsonb,
  created_at   timestamptz not null default now(),
  unique (title, artist)
);

-- ─── concerts ────────────────────────────────────────────────────────────────
create table concerts (
  id              uuid primary key default gen_random_uuid(),
  owner_id        uuid not null references profiles (id) on delete cascade,
  title           text not null,
  artist          text,
  venue           text,
  city            text,
  performed_on    date,
  cover_image_url text,
  is_demo         boolean not null default false,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now()
);
create trigger concerts_updated_at before update on concerts
  for each row execute function set_updated_at();
create index concerts_owner_idx on concerts (owner_id);

-- ─── concert_members (collaborative — Phase 2) ───────────────────────────────
create table concert_members (
  concert_id uuid not null references concerts (id) on delete cascade,
  user_id    uuid not null references profiles (id) on delete cascade,
  role       concert_role not null default 'contributor',
  invited_by uuid references profiles (id) on delete set null,
  created_at timestamptz not null default now(),
  primary key (concert_id, user_id)
);

-- ─── clips (the central entity) ──────────────────────────────────────────────
create table clips (
  id               uuid primary key default gen_random_uuid(),
  concert_id       uuid references concerts (id) on delete set null,
  uploader_id      uuid not null references profiles (id) on delete cascade,
  status           clip_status not null default 'uploading',

  raw_video_key    text,
  audio_key        text,
  transcoded_key   text,
  thumbnail_key    text,

  duration_seconds numeric,
  recorded_at      timestamptz,
  width            int,
  height           int,
  size_bytes       bigint,

  song_id          uuid references songs (id) on delete set null,
  match_source     match_source,
  match_confidence numeric check (match_confidence between 0 and 1),
  manual_artist    text,
  manual_title     text,

  audio_quality_score numeric, -- Phase 2 cleanest-audio ranking

  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now()
);
create trigger clips_updated_at before update on clips
  for each row execute function set_updated_at();
create index clips_uploader_idx on clips (uploader_id);
create index clips_concert_idx  on clips (concert_id);
create index clips_song_idx     on clips (song_id);

-- ─── recognitions (audit of every fingerprint attempt) ───────────────────────
create table recognitions (
  id              uuid primary key default gen_random_uuid(),
  clip_id         uuid not null references clips (id) on delete cascade,
  provider        fingerprint_provider not null,
  matched_song_id uuid references songs (id) on delete set null,
  confidence      numeric,
  raw_response    jsonb,
  created_at      timestamptz not null default now()
);
create index recognitions_clip_idx on recognitions (clip_id);

-- ─── playlists ───────────────────────────────────────────────────────────────
create table playlists (
  id          uuid primary key default gen_random_uuid(),
  owner_id    uuid not null references profiles (id) on delete cascade,
  concert_id  uuid references concerts (id) on delete cascade,
  type        playlist_type not null default 'custom',
  title       text not null,
  description text,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);
create trigger playlists_updated_at before update on playlists
  for each row execute function set_updated_at();
-- Exactly one auto playlist per concert.
create unique index playlists_concert_unique
  on playlists (concert_id) where type = 'concert';

create table playlist_items (
  id          uuid primary key default gen_random_uuid(),
  playlist_id uuid not null references playlists (id) on delete cascade,
  clip_id     uuid not null references clips (id) on delete cascade,
  position    int not null default 0,
  created_at  timestamptz not null default now(),
  unique (playlist_id, clip_id)
);
create index playlist_items_playlist_idx on playlist_items (playlist_id, position);

-- ─── favorites / ratings ─────────────────────────────────────────────────────
create table favorites (
  user_id    uuid not null references profiles (id) on delete cascade,
  clip_id    uuid not null references clips (id) on delete cascade,
  stars      int not null default 5 check (stars between 1 and 5),
  created_at timestamptz not null default now(),
  primary key (user_id, clip_id)
);

-- ─── tags ────────────────────────────────────────────────────────────────────
create table tags (
  id    uuid primary key default gen_random_uuid(),
  label text unique not null
);
create table clip_tags (
  clip_id uuid not null references clips (id) on delete cascade,
  tag_id  uuid not null references tags (id) on delete cascade,
  primary key (clip_id, tag_id)
);

-- ─── auto-create a profile row when an auth user signs up ────────────────────
create or replace function handle_new_user()
returns trigger language plpgsql security definer set search_path = public as $$
begin
  insert into public.profiles (id, display_name)
  values (new.id, coalesce(new.raw_user_meta_data ->> 'display_name', split_part(new.email, '@', 1)))
  on conflict (id) do nothing;
  return new;
end; $$;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function handle_new_user();
