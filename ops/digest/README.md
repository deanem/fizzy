# Digest Fizzy Instance (Separate Stack)

This folder runs a separate Fizzy instance for Digest planning and syncs actionable cards from the Digest internal roadmap.

## What is synced

Only unchecked action items from:

- `/srv/digest/PRODUCT_ROADMAP_INTERNAL.md`

The sync script refuses to run unless `/srv/digest` is on branch `dev`.

## 1) Start Fizzy container

```bash
cd /srv/fizzy/ops/digest
cp .env.example .env
```

Generate a secret and set it in `.env`:

```bash
openssl rand -hex 64
```

Then run:

```bash
docker compose up -d
```

Fizzy will be available at `http://<dev-server-ip-or-domain>:3333` unless you changed `FIZZY_PORT`.

## 2) Create token

In Fizzy UI:

1. Sign in and create/select your account
2. Go to profile API section
3. Create a personal access token (read/write)
4. Put it in `.env` as `FIZZY_API_TOKEN`

If needed, set `FIZZY_ACCOUNT_SLUG` to the numeric account slug from the URL.

## 3) Dry-run parse

```bash
cd /srv/fizzy/ops/digest
python3 sync_product_roadmap_internal.py --dry-run
```

## 4) Sync to board

```bash
cd /srv/fizzy/ops/digest
python3 sync_product_roadmap_internal.py
```

Default board name:

- `Digest Product Action Items`

Set `FIZZY_BOARD_NAME` in `.env` to override.

## 5) Optional cron (hourly)

```bash
0 * * * * cd /srv/fizzy/ops/digest && /bin/bash -lc 'set -a; . ./.env; set +a; python3 sync_product_roadmap_internal.py' >> sync.log 2>&1
```

## Fork upkeep (keep up with basecamp/fizzy)

From repo root:

```bash
cd /srv/fizzy
git fetch upstream
git checkout main
git merge --ff-only upstream/main
git push origin main
```

If you have local commits on `main`, rebase instead:

```bash
git fetch upstream
git checkout main
git rebase upstream/main
git push --force-with-lease origin main
```
