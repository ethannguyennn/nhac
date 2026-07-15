# Supabase (metadata DB + auth)

Nhạc uses Supabase for Postgres, auth, and RLS — **not** for video storage
(video lives in Cloudflare R2; the free Supabase tier caps ~1 GB, unusable for
video). See [../../docs/DECISIONS.md](../../docs/DECISIONS.md).

## Layout

```
infra/supabase/
├── migrations/
│   ├── 0001_init.sql   # tables, enums, triggers
│   └── 0002_rls.sql    # row-level security policies
├── seed.sql            # demo-mode content for cold start
└── README.md
```

## Apply the schema

**Option A — Supabase CLI (recommended)**

```bash
npm i -g supabase
supabase login
supabase link --project-ref <your-project-ref>
supabase db push        # applies migrations/
```

**Option B — SQL editor**

Paste `0001_init.sql` then `0002_rls.sql` into the dashboard SQL editor and run,
in that order.

## Auth

Enable Email (magic link) auth in the dashboard. The `on_auth_user_created`
trigger auto-creates a `profiles` row for every new user.

## Keys

- **anon key** → mobile/web clients (safe, gated by RLS).
- **service-role key** → the API server only (`services/api`). It bypasses RLS;
  never ship it to a client.

## Regenerating shared enums

Enum values in `0001_init.sql` must stay in sync with
[`packages/shared/src/enums.ts`](../../packages/shared/src/enums.ts). If you add
a status, update both.
