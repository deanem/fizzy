# Digest Fizzy Integration (Separate Stack)

This folder runs a separate Fizzy instance for Digest planning and provides two-way sync between the Digest internal roadmap markdown and Fizzy cards.

## Purpose
Use this Fizzy instance as the operational board for Digest product work:
- View all open product tasks.
- Move tasks across planning columns.
- Mark tasks done in Fizzy and sync completion back to markdown.
- Add new tasks in Fizzy and sync them into the roadmap doc.

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
- Open columns map from roadmap `###` headings that still have open checklist items
- Completed checklist items use Fizzy native DONE (closed cards), not a custom workflow column
- Completed cards are prefixed with section context in title (for example: `[Milestone B] ...`)
- Empty sync-managed columns are automatically removed after sync
- Synced cards include a stable key in description:
  - `Digest Sync Key: digest-internal-...`

## Sync Behavior
### Markdown -> Fizzy
- `- [ ] item` creates/updates an open card in its mapped section column.
- `- [x] item` creates/updates a closed card in native DONE.
- Removed markdown items can close obsolete synced cards (`FIZZY_CLOSE_OBSOLETE=true`).

### Fizzy -> Markdown (Two-way)
- Card closed (native DONE) marks markdown item as `- [x]`.
- Card reopened marks markdown item as `- [ ]`.
- New card without sync key is appended into markdown as a checklist item in the mapped section, then linked with a generated sync key.

## Conflict Policy
- Sync key identity is authoritative.
- Completion state follows Fizzy closed/native DONE status in two-way mode.
- Title/details normalize back to markdown text on full sync.

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
- `FIZZY_TWO_WAY_SYNC`
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
- `--no-two-way` disables Fizzy -> markdown write-back
- `--no-close-obsolete` disables closing removed items

## 6) Optional Cron
Recommended every 5 minutes:
```bash
*/5 * * * * cd /srv/fizzy/ops/digest && /bin/bash -lc 'set -a; . ./.env; set +a; python3 sync_product_roadmap_internal.py' >> sync.log 2>&1
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
