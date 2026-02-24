# Digest Fizzy Integration

A separate Fizzy instance used as the operational task board for Digest product work,
with a CLI tool (`fizzy.py`) for AI agent access.

## Purpose

- Human manages tasks in the Fizzy UI (create, move, rename, reorder, delete)
- AI agents interact via `fizzy.py` (read board, create cards, close cards, manage columns)
- Fizzy is the single source of truth — no markdown sync

## What AI agents can do

| Operation | Command |
|---|---|
| Read full board | `fizzy.py board` |
| Create card (→ MAYBE? triage) | `fizzy.py cards create "Title"` |
| Create card in specific column | `fizzy.py cards create "Title" --column "Column Name"` |
| Close a card | `fizzy.py cards close NUMBER` |
| Move card to column | `fizzy.py cards move NUMBER --column "Column Name"` |
| List columns | `fizzy.py columns list` |
| Add column | `fizzy.py columns add "Name"` |
| Delete column (cards → MAYBE?) | `fizzy.py columns delete "Name"` |
| Reorder column | `fizzy.py columns move "Name" --position N` |

AI agents cannot delete cards — only the human can do that in the Fizzy UI.

## Setup

### 1) Start Fizzy container
```bash
cd /srv/fizzy/ops/digest
cp .env.example .env
openssl rand -hex 64   # paste result as FIZZY_SECRET_KEY_BASE
docker compose up -d
```

### 2) Create API token
In the Fizzy UI: profile → API → create a personal access token (read/write).
Set `FIZZY_API_TOKEN` in `.env`.

### 3) Run
```bash
cd /srv/fizzy/ops/digest
set -a; . ./.env; set +a
python3 fizzy.py board
```

## Environment variables

| Variable | Purpose |
|---|---|
| `FIZZY_API_BASE_URL` | URL of the Fizzy instance |
| `FIZZY_API_TOKEN` | Personal access token |
| `FIZZY_ACCOUNT_SLUG` | Account slug (auto-discovered if omitted) |
| `FIZZY_BOARD_NAME` | Board name (default: `Digest Product Action Items`) |

## Remote access

`fizzy.py` only needs network access to the Fizzy API — it does not need to run
on the same server as Fizzy. To run locally against the dev instance:

```bash
export FIZZY_API_BASE_URL=https://fizzy.dev.thedigest.co
export FIZZY_API_TOKEN=your_token
python3 fizzy.py board
```

## Fork upkeep (Basecamp → your fork)
```bash
cd /srv/fizzy
git fetch upstream
git checkout main
git merge --ff-only upstream/main
git push origin main
```
