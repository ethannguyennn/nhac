-- ═══════════════════════════════════════════════════════════════════════════
-- Nhạc — Row Level Security (0002)
-- The API server uses the service-role key and BYPASSES these. RLS protects
-- direct client access (mobile/web using the anon key + a user session).
--
-- Model (MVP):
--  * A user can read/write their own profile, clips, playlists, favorites.
--  * A user can read a concert if they own it, are a member, or it's a demo.
--  * Songs + demo content are world-readable.
-- Tighten/extend for collaborative concerts in Phase 2.
-- ═══════════════════════════════════════════════════════════════════════════

alter table profiles        enable row level security;
alter table songs           enable row level security;
alter table concerts        enable row level security;
alter table concert_members enable row level security;
alter table clips           enable row level security;
alter table recognitions    enable row level security;
alter table playlists       enable row level security;
alter table playlist_items  enable row level security;
alter table favorites       enable row level security;
alter table tags            enable row level security;
alter table clip_tags       enable row level security;

-- ─── profiles ────────────────────────────────────────────────────────────────
create policy profiles_read_all on profiles for select using (true);
create policy profiles_write_own on profiles for all
  using (id = auth.uid()) with check (id = auth.uid());

-- ─── songs + tags: world-readable, server-managed writes ─────────────────────
create policy songs_read_all on songs for select using (true);
create policy tags_read_all  on tags  for select using (true);

-- ─── concerts ────────────────────────────────────────────────────────────────
create policy concerts_read on concerts for select using (
  is_demo
  or owner_id = auth.uid()
  or exists (
    select 1 from concert_members m
    where m.concert_id = concerts.id and m.user_id = auth.uid()
  )
);
create policy concerts_write_own on concerts for all
  using (owner_id = auth.uid()) with check (owner_id = auth.uid());

-- ─── concert_members ─────────────────────────────────────────────────────────
create policy members_read on concert_members for select using (
  user_id = auth.uid()
  or exists (select 1 from concerts c where c.id = concert_id and c.owner_id = auth.uid())
);
create policy members_owner_manage on concert_members for all using (
  exists (select 1 from concerts c where c.id = concert_id and c.owner_id = auth.uid())
) with check (
  exists (select 1 from concerts c where c.id = concert_id and c.owner_id = auth.uid())
);

-- ─── clips ───────────────────────────────────────────────────────────────────
create policy clips_read on clips for select using (
  uploader_id = auth.uid()
  or exists (
    select 1 from concerts c
    where c.id = clips.concert_id
      and (c.is_demo or c.owner_id = auth.uid()
        or exists (select 1 from concert_members m where m.concert_id = c.id and m.user_id = auth.uid()))
  )
);
create policy clips_write_own on clips for all
  using (uploader_id = auth.uid()) with check (uploader_id = auth.uid());

-- ─── recognitions: readable by the clip's uploader ───────────────────────────
create policy recognitions_read on recognitions for select using (
  exists (select 1 from clips c where c.id = clip_id and c.uploader_id = auth.uid())
);

-- ─── playlists + items ───────────────────────────────────────────────────────
create policy playlists_read on playlists for select using (
  owner_id = auth.uid()
  or exists (select 1 from concerts c where c.id = playlists.concert_id and c.is_demo)
);
create policy playlists_write_own on playlists for all
  using (owner_id = auth.uid()) with check (owner_id = auth.uid());

create policy playlist_items_read on playlist_items for select using (
  exists (
    select 1 from playlists p
    where p.id = playlist_id
      and (p.owner_id = auth.uid()
        or exists (select 1 from concerts c where c.id = p.concert_id and c.is_demo))
  )
);
create policy playlist_items_write on playlist_items for all using (
  exists (select 1 from playlists p where p.id = playlist_id and p.owner_id = auth.uid())
) with check (
  exists (select 1 from playlists p where p.id = playlist_id and p.owner_id = auth.uid())
);

-- ─── favorites ───────────────────────────────────────────────────────────────
create policy favorites_own on favorites for all
  using (user_id = auth.uid()) with check (user_id = auth.uid());

-- ─── clip_tags: readable with the clip ───────────────────────────────────────
create policy clip_tags_read on clip_tags for select using (
  exists (select 1 from clips c where c.id = clip_id and c.uploader_id = auth.uid())
);
