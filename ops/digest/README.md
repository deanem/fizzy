# Digest Fizzy Integration (Separate Stack)

This folder runs a separate Fizzy instance for Digest planning and provides one-way sync from the Digest internal roadmap markdown into Fizzy cards.

## Purpose

Use this Fizzy instance as the operational board for Digest product work:
- View all open product tasks as a Fizzy board.
- Move, reorder, and manage tasks in Fizzy.
- Mark tasks done natively in Fizzy.
- Fizzy is the source of truth for task state.

## Scope and Ownership
- Integration code lives in `ops/digest` in the Fizzy repo.
- This is integration logic, not a Fizzy core feature.
- Source scope is intentionally narrow: internal roadmap only.

## Source Doc and Branch Guard
- Source doc candidates (in order):
  - `docs/PRODUCT_ROADMAP_INTERNAL.md`
  - `PRODUCT_ROADMAP_INTERNAL.md`
- The script refuses to sync unless the Digest repo branch is `dev`.

## Board Model
- Board name default: `Digest Product Action Items` (`FIZZY_BOARD_NAME` to override)
- Columns map from roadmap `###` headings that have at least one open item (`- [ ]`)
- Completed items (`- [x]`) are ignored; Fizzy manages completion natively
- Empty sync-managed columns are automatically removed after sync
- Synced cards include a stable key in description:
  - `Digest Sync Key: digest-internal-...`

## Sync Behavior (one-way: MD → Fizzy)
- `- [ ] item` creates/updates an open card in its mapped section column.
- `- [x] item` is ignored — completion is managed in Fizzy, not synced from MD.
- Open items removed from the markdown close the corresponding card (`FIZZY_CLOSE_OBSOLETE=true`).

## Conflict Policy
- Sync key identity is authoritative.
- Title/details normalise back to markdown text on each sync run.
- Card completion state is owned by Fizzy and never overwritten by the sync.

## 1) Start Fizzy Container
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

## 2) Create API Token
In Fizzy UI:
1. Sign in and create/select account.
2. Open profile API section.
3. Create a personal access token (read/write).
4. Set `FIZZY_API_TOKEN` in `.env`.

Set `FIZZY_ACCOUNT_SLUG` if auto-discovery is not possible.

## 3) Configure Environment
Primary env file:
- `/srv/fizzy/ops/digest/.env`

Key vars:
- `FIZZY_API_BASE_URL`
- `FIZZY_API_TOKEN`
- `FIZZY_ACCOUNT_SLUG`
- `FIZZY_BOARD_NAME`
- `FIZZY_CLOSE_OBSOLETE`
- `DIGEST_REPO_PATH`
- `DIGEST_ACTION_DOC` (optional explicit doc path)

## 4) Dry Run
```bash
cd /srv/fizzy/ops/digest
set -a; . ./.env; set +a
python3 sync_product_roadmap_internal.py --dry-run
```

## 5) Sync
```bash
cd /srv/fizzy/ops/digest
set -a; . ./.env; set +a
python3 sync_product_roadmap_internal.py
```

Useful flags:
- `--no-close-obsolete` — keep cards for items removed from the markdown

## 6) Automate with Cron
Run on a schedule to keep Fizzy up to date when the roadmap doc changes:
```bash
*/15 * * * * cd /srv/fizzy/ops/digest && /bin/bash -lc 'set -a; . ./.env; set +a; python3 sync_product_roadmap_internal.py' >> sync.log 2>&1
```

## Safety
- Use dry-run before major changes.
- Keep Digest repo history for rollback.
- Do not modify Fizzy core code for integration behavior.

## Fork Upkeep (Basecamp -> Your Fork)
Fast-forward when clean:
```bash
cd /srv/fizzy
git fetch upstream
git checkout main
git merge --ff-only upstream/main
git push origin main
```

If local commits exist on `main`, rebase:
```bash
git fetch upstream
git checkout main
git rebase upstream/main
git push --force-with-lease origin main
```
