# Contributing to Nhạc

Small, fast-moving project. Keep it simple.

## Ground rules

- **Ship the MVP first.** Don't build Phase 2 features until Phase 1 works
  end-to-end (see [docs/ROADMAP.md](docs/ROADMAP.md)).
- **Keep it cheap.** Prefer free tiers and simple solutions; flag anything that
  adds recurring cost.
- **Types are the contract.** Shared shapes live in `@nhac/shared`. Change the
  type there, not ad hoc per app. After editing shared, run `npm run shared:build`.
- **Enums ↔ DB.** If you add an enum value in `packages/shared/src/enums.ts`,
  mirror it in `infra/supabase/migrations`.

## Workflow

```bash
git checkout -b feat/short-name
npm run typecheck && npm run format
# commit small, focused changes
```

Commit style: short imperative subject (`add manual tag route`). Reference a
roadmap item when relevant.

## Before opening a PR

- [ ] `npm run shared:build`
- [ ] `npm run typecheck`
- [ ] `npm run format:check`
- [ ] Updated `docs/ROADMAP.md` checkboxes if you completed a step

## Secrets

Never commit `.env` files or keys. Only `.env.example` templates belong in git.
The service-role key and R2 secret are server-only — never ship them to a client.
