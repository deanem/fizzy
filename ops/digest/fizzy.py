#!/usr/bin/env python3
"""Fizzy board management CLI for AI agents.

Reads env from the same .env used by the sync script.

Usage:
  fizzy.py board                                          # Full board overview (default)
  fizzy.py cards list                                     # Open cards by column
  fizzy.py cards create TITLE [--column COL] [--description DESC]  # Create card
  fizzy.py cards describe NUMBER DESCRIPTION              # Set/update description on a card
  fizzy.py cards close NUMBER                             # Close a card
  fizzy.py cards move NUMBER --column COL                 # Move card to a column
  fizzy.py columns list                                   # List columns in order
  fizzy.py columns add NAME [--color COLOR]               # Add a column
  fizzy.py columns delete NAME                            # Delete column (cards → triage)
  fizzy.py columns move NAME --position N                 # Move column to position (1-based)

Constraints:
  - Cards are never deleted (only closeable). Only the human can delete cards.
  - Card ordering within a column is not controllable via API (Fizzy orders by
    last_active_at). Reorder cards manually in the Fizzy UI.
  - Column deletion moves cards to triage (the uncolumned holding area), not trash.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Dict, List, Optional, Tuple
from urllib.error import HTTPError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BASE_URL   = os.environ.get("FIZZY_API_BASE_URL", "http://localhost:3333").rstrip("/")
TOKEN      = os.environ.get("FIZZY_API_TOKEN", "")
SLUG       = os.environ.get("FIZZY_ACCOUNT_SLUG", "1").lstrip("/")
BOARD_NAME = os.environ.get("FIZZY_BOARD_NAME", "Digest Product Action Items")
COLUMN_COLORS = [
    "var(--color-card-default)",
    "var(--color-card-1)",
    "var(--color-card-2)",
    "var(--color-card-3)",
    "var(--color-card-4)",
    "var(--color-card-5)",
    "var(--color-card-6)",
    "var(--color-card-7)",
    "var(--color-card-8)",
]

# ---------------------------------------------------------------------------
# HTTP client
# ---------------------------------------------------------------------------

def _request(
    method: str,
    path: str,
    payload: Optional[dict] = None,
    expected: Tuple[int, ...] = (200,),
) -> Tuple[int, dict, bytes]:
    url = f"{BASE_URL}{path}" if path.startswith("/") else path
    headers = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"}
    body = None
    if payload is not None:
        body = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    req = Request(url, data=body, headers=headers, method=method)
    try:
        with urlopen(req, timeout=30) as r:
            return r.status, dict(r.headers), r.read()
    except HTTPError as e:
        msg = e.read().decode("utf-8", errors="replace")
        print(f"ERROR: {method} {path} → {e.code}: {msg}", file=sys.stderr)
        sys.exit(1)


def _get_paginated(path: str) -> List[dict]:
    rows: List[dict] = []
    next_url: Optional[str] = path
    while next_url:
        _, headers, body = _request("GET", next_url)
        rows.extend(json.loads(body))
        link = headers.get("Link") or headers.get("link") or ""
        m = re.search(r'<([^>]+)>;\s*rel="next"', link)
        next_url = m.group(1) if m else None
        if next_url and next_url.startswith("http"):
            parsed = urlparse(next_url)
            next_url = parsed.path + (f"?{parsed.query}" if parsed.query else "")
    return rows


# ---------------------------------------------------------------------------
# Board / column / card helpers
# ---------------------------------------------------------------------------

def get_board_id() -> str:
    boards = _get_paginated(f"/{SLUG}/boards")
    for b in boards:
        if b.get("name") == BOARD_NAME:
            return b["id"]
    print(f"ERROR: Board '{BOARD_NAME}' not found.", file=sys.stderr)
    sys.exit(1)


def get_columns(board_id: str) -> List[dict]:
    """Return columns sorted by position."""
    return _get_paginated(f"/{SLUG}/boards/{board_id}/columns")


def resolve_column(board_id: str, name: str) -> dict:
    """Find a regular column by name (case-insensitive)."""
    cols = get_columns(board_id)
    for col in cols:
        if (col.get("name") or "").strip().lower() == name.strip().lower():
            return col
    print(f"ERROR: Column '{name}' not found.", file=sys.stderr)
    print(f"Available: {', '.join(c['name'] for c in cols)}", file=sys.stderr)
    sys.exit(1)


def get_open_cards(board_id: str) -> List[dict]:
    q = urlencode([("board_ids[]", board_id), ("indexed_by", "all")])
    return _get_paginated(f"/{SLUG}/cards?{q}")


def get_triage_cards(board_id: str) -> List[dict]:
    """Cards with no column assigned (awaiting triage)."""
    return [c for c in get_open_cards(board_id) if not c.get("column")]


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------

def _card_line(card: dict, indent: str = "  ") -> str:
    num   = card.get("number", "?")
    title = (card.get("title") or "").strip()
    return f"{indent}#{num:<4} {title}"


def print_board(board_id: str) -> None:
    cols  = get_columns(board_id)
    cards = get_open_cards(board_id)

    cards_by_col: Dict[str, List[dict]] = {}
    triage: List[dict] = []
    for card in cards:
        col = card.get("column") or {}
        col_id = (col.get("id") or "").strip()
        if col_id:
            cards_by_col.setdefault(col_id, []).append(card)
        else:
            triage.append(card)

    print(f"\n=== {BOARD_NAME} ===\n")
    for i, col in enumerate(cols, 1):
        col_id   = col.get("id", "")
        col_name = col.get("name", "")
        col_cards = cards_by_col.get(col_id, [])
        print(f"[{i}] {col_name}  ({len(col_cards)} open)")
        for card in col_cards:
            print(_card_line(card))
        print()

    if triage:
        print(f"MAYBE? / triage (no column)  ({len(triage)})")
        for card in triage:
            print(_card_line(card))
        print()


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_board(args: argparse.Namespace, board_id: str) -> None:
    print_board(board_id)


def cmd_cards_list(args: argparse.Namespace, board_id: str) -> None:
    print_board(board_id)


def cmd_cards_create(args: argparse.Namespace, board_id: str) -> None:
    card_payload: dict = {"title": args.title}
    if args.description:
        card_payload["description"] = args.description
    _, headers, _ = _request(
        "POST",
        f"/{SLUG}/boards/{board_id}/cards",
        payload={"card": card_payload},
        expected=(201,),
    )

    # Resolve card number from Location header
    location    = headers.get("Location") or headers.get("location") or ""
    m           = re.search(r"/cards/([^/.]+)", location)
    card_number = m.group(1) if m else None

    if not card_number:
        for card in get_open_cards(board_id):
            if card.get("title", "").strip() == args.title.strip():
                card_number = str(card["number"])
                break

    if args.column:
        col = resolve_column(board_id, args.column)
        if card_number:
            _request(
                "POST",
                f"/{SLUG}/cards/{card_number}/triage",
                payload={"column_id": col["id"]},
                expected=(204,),
            )
        destination = col["name"]
    else:
        destination = "MAYBE? (triage)"

    num_str = f"#{card_number}" if card_number else "(number unknown)"
    print(f"Created card {num_str}: {args.title!r} → {destination}")


def cmd_cards_describe(args: argparse.Namespace, board_id: str) -> None:
    _request(
        "PATCH",
        f"/{SLUG}/cards/{args.number}",
        payload={"card": {"description": args.description}},
        expected=(204,),
    )
    print(f"Updated description on card #{args.number}")


def cmd_cards_close(args: argparse.Namespace, board_id: str) -> None:
    _request("POST", f"/{SLUG}/cards/{args.number}/closure", expected=(204,))
    print(f"Closed card #{args.number}")


def cmd_cards_move(args: argparse.Namespace, board_id: str) -> None:
    col = resolve_column(board_id, args.column)
    _request(
        "POST",
        f"/{SLUG}/cards/{args.number}/triage",
        payload={"column_id": col["id"]},
        expected=(204,),
    )
    print(f"Moved card #{args.number} → {col['name']}")


def cmd_columns_list(args: argparse.Namespace, board_id: str) -> None:
    cols = get_columns(board_id)
    print(f"\nColumns in {BOARD_NAME}:\n")
    for i, col in enumerate(cols, 1):
        print(f"  [{i}] {col['name']}")
    print()


def cmd_columns_add(args: argparse.Namespace, board_id: str) -> None:
    cols  = get_columns(board_id)
    color = args.color or COLUMN_COLORS[len(cols) % len(COLUMN_COLORS)]
    _request(
        "POST",
        f"/{SLUG}/boards/{board_id}/columns",
        payload={"column": {"name": args.name, "color": color}},
        expected=(201,),
    )
    print(f"Added column: {args.name!r}")


def cmd_columns_delete(args: argparse.Namespace, board_id: str) -> None:
    col        = resolve_column(board_id, args.name)
    col_id     = col["id"]
    col_name   = col["name"]

    # Count cards that will move to triage
    cards      = get_open_cards(board_id)
    col_cards  = [c for c in cards if (c.get("column") or {}).get("id") == col_id]

    _request("DELETE", f"/{SLUG}/boards/{board_id}/columns/{col_id}", expected=(204,))

    if col_cards:
        print(f"Deleted column '{col_name}'. {len(col_cards)} card(s) moved to triage (not deleted).")
    else:
        print(f"Deleted column '{col_name}' (was empty).")


def cmd_columns_move(args: argparse.Namespace, board_id: str) -> None:
    target = args.position  # 1-based
    col    = resolve_column(board_id, args.name)
    cols   = get_columns(board_id)

    current = next((i + 1 for i, c in enumerate(cols) if c["id"] == col["id"]), None)
    if current is None:
        print(f"ERROR: Column '{args.name}' not found in position list.", file=sys.stderr)
        sys.exit(1)

    target = max(1, min(target, len(cols)))
    if current == target:
        print(f"Column '{args.name}' is already at position {target}.")
        return

    col_id = col["id"]
    steps  = target - current
    endpoint = "right_position" if steps > 0 else "left_position"
    for _ in range(abs(steps)):
        _request("POST", f"/{SLUG}/columns/{col_id}/{endpoint}", expected=(204,))

    print(f"Moved column '{args.name}' to position {target}.")


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fizzy.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command")

    # board (default)
    sub.add_parser("board", help="Show full board overview")

    # cards
    cards = sub.add_parser("cards", help="Card operations")
    cards_sub = cards.add_subparsers(dest="cards_command")

    cards_sub.add_parser("list", help="List open cards by column")

    p_create = cards_sub.add_parser("create", help="Create a card")
    p_create.add_argument("title", help="Card title")
    p_create.add_argument("--column", "-c", help="Target column name (omit to land in MAYBE? triage)")
    p_create.add_argument("--description", "-d", help="Card description (plain text)")

    p_describe = cards_sub.add_parser("describe", help="Set or update description on a card")
    p_describe.add_argument("number", help="Card number")
    p_describe.add_argument("description", help="New description text (plain text)")

    p_close = cards_sub.add_parser("close", help="Close a card")
    p_close.add_argument("number", help="Card number")

    p_move = cards_sub.add_parser("move", help="Move card to a column")
    p_move.add_argument("number", help="Card number")
    p_move.add_argument("--column", "-c", required=True, help="Target column name")

    # columns
    columns = sub.add_parser("columns", help="Column operations")
    cols_sub = columns.add_subparsers(dest="columns_command")

    cols_sub.add_parser("list", help="List columns in order")

    p_add = cols_sub.add_parser("add", help="Add a column")
    p_add.add_argument("name", help="Column name")
    p_add.add_argument("--color", help="Column color CSS var (optional)")

    p_del = cols_sub.add_parser("delete", help="Delete a column (cards go to triage)")
    p_del.add_argument("name", help="Column name")

    p_mv = cols_sub.add_parser("move", help="Move column to a position")
    p_mv.add_argument("name", help="Column name")
    p_mv.add_argument("--position", "-p", type=int, required=True, help="Target position (1-based)")

    return parser


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    if not TOKEN:
        print("ERROR: FIZZY_API_TOKEN not set.", file=sys.stderr)
        return 2

    parser = build_parser()
    args   = parser.parse_args()

    board_id = get_board_id()

    if args.command is None or args.command == "board":
        cmd_board(args, board_id)

    elif args.command == "cards":
        if not args.cards_command or args.cards_command == "list":
            cmd_cards_list(args, board_id)
        elif args.cards_command == "create":
            cmd_cards_create(args, board_id)
        elif args.cards_command == "describe":
            cmd_cards_describe(args, board_id)
        elif args.cards_command == "close":
            cmd_cards_close(args, board_id)
        elif args.cards_command == "move":
            cmd_cards_move(args, board_id)
        else:
            parser.print_help()

    elif args.command == "columns":
        if not args.columns_command or args.columns_command == "list":
            cmd_columns_list(args, board_id)
        elif args.columns_command == "add":
            cmd_columns_add(args, board_id)
        elif args.columns_command == "delete":
            cmd_columns_delete(args, board_id)
        elif args.columns_command == "move":
            cmd_columns_move(args, board_id)
        else:
            parser.print_help()

    else:
        parser.print_help()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
