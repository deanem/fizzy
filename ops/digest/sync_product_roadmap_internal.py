#!/usr/bin/env python3
"""Sync digest PRODUCT_ROADMAP_INTERNAL.md actionable items to a Fizzy board.

This script is intentionally locked to:
- digest doc: PRODUCT_ROADMAP_INTERNAL.md
- digest branch: dev
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

ACTION_DOC_NAME = "PRODUCT_ROADMAP_INTERNAL.md"
REQUIRED_BRANCH = "dev"
SYNC_KEY_PREFIX = "Digest Sync Key: "
SYNC_KEY_RE = re.compile(r"^Digest Sync Key:\s*(\S+)\s*$", re.MULTILINE)
HEADING_RE = re.compile(r"^###\s+(.+?)\s*$")
OPEN_ITEM_RE = re.compile(r"^\s*-\s+\[ \]\s+(.+?)\s*$")

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


@dataclass(frozen=True)
class ActionItem:
    key: str
    title: str
    details: str
    heading: str
    column: str
    source_line: int
    order: int


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def clean_text(value: str) -> str:
    text = value.strip()
    text = text.replace("**", "").replace("__", "")
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\[(.*?)\]\((.*?)\)", r"\1", text)
    text = text.replace("—", "-")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def heading_to_column(heading: str) -> str:
    h = clean_text(heading)
    h = h.replace("✅", "")
    h = re.sub(r"^\d+\)\s*", "", h)
    return h.strip() or "Uncategorized"


def make_title(item_text: str) -> str:
    first_clause = re.split(r"\s+-\s+", item_text, maxsplit=1)[0]
    title = clean_text(first_clause)
    if not title:
        title = clean_text(item_text)
    if len(title) > 160:
        return title[:157].rstrip() + "..."
    return title


def make_key(heading: str, item_text: str) -> str:
    normalized = f"{clean_text(heading).lower()}|{clean_text(item_text).lower()}"
    digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:16]
    return f"digest-internal-{digest}"


def parse_action_items(action_doc_path: str) -> Tuple[List[ActionItem], List[str]]:
    with open(action_doc_path, "r", encoding="utf-8") as handle:
        lines = handle.readlines()

    current_heading = "Uncategorized"
    section_order: List[str] = []
    seen_sections = set()
    items: List[ActionItem] = []
    order = 0

    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.rstrip("\n")

        heading_match = HEADING_RE.match(line)
        if heading_match:
            current_heading = clean_text(heading_match.group(1))
            continue

        item_match = OPEN_ITEM_RE.match(line)
        if not item_match:
            continue

        details = clean_text(item_match.group(1))
        if not details:
            continue

        column = heading_to_column(current_heading)
        if column not in seen_sections:
            seen_sections.add(column)
            section_order.append(column)

        order += 1
        items.append(
            ActionItem(
                key=make_key(current_heading, details),
                title=make_title(details),
                details=details,
                heading=current_heading,
                column=column,
                source_line=line_number,
                order=order,
            )
        )

    return items, section_order


def parse_next_link(link_header: Optional[str]) -> Optional[str]:
    if not link_header:
        return None

    for part in link_header.split(","):
        chunk = part.strip()
        if 'rel="next"' not in chunk:
            continue
        match = re.search(r"<([^>]+)>", chunk)
        if match:
            return match.group(1)

    return None


def current_git_branch(repo_path: str) -> Optional[str]:
    try:
        output = subprocess.check_output(
            ["git", "-C", repo_path, "rev-parse", "--abbrev-ref", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None

    return output.strip()


def extract_sync_key(description: str) -> Optional[str]:
    if not description:
        return None
    match = SYNC_KEY_RE.search(description)
    return match.group(1) if match else None


class FizzyClient:
    def __init__(self, base_url: str, token: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token

    def request(
        self,
        method: str,
        path_or_url: str,
        payload: Optional[dict] = None,
        expected: Iterable[int] = (200,),
    ) -> Tuple[int, Dict[str, str], bytes]:
        if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
            url = path_or_url
        else:
            url = f"{self.base_url}{path_or_url}"

        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
        }
        body = None
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"

        request = Request(url, data=body, headers=headers, method=method)

        try:
            with urlopen(request, timeout=30) as response:
                status = response.status
                response_body = response.read()
                response_headers = dict(response.headers.items())
        except HTTPError as error:
            error_body = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"{method} {path_or_url} failed: {error.code} {error.reason}; body={error_body}"
            ) from error
        except URLError as error:
            raise RuntimeError(f"{method} {path_or_url} failed: {error.reason}") from error

        if status not in set(expected):
            decoded = response_body.decode("utf-8", errors="replace")
            raise RuntimeError(
                f"{method} {path_or_url} returned {status}, expected {sorted(set(expected))}; body={decoded}"
            )

        return status, response_headers, response_body

    def get_json(self, path: str):
        _, _, body = self.request("GET", path, expected=(200,))
        if not body:
            return None
        return json.loads(body.decode("utf-8"))

    def get_paginated(self, path: str) -> List[dict]:
        rows: List[dict] = []
        next_target: Optional[str] = path

        while next_target:
            _, headers, body = self.request("GET", next_target, expected=(200,))
            payload = json.loads(body.decode("utf-8"))
            if not isinstance(payload, list):
                raise RuntimeError(f"Expected list payload from {next_target}")
            rows.extend(payload)

            link_header = headers.get("Link") or headers.get("link")
            next_target = parse_next_link(link_header)
            if next_target and next_target.startswith("http"):
                parsed = urlparse(next_target)
                path_part = parsed.path or "/"
                if parsed.query:
                    path_part = f"{path_part}?{parsed.query}"
                next_target = path_part

        return rows

    def discover_account_slug(self) -> str:
        identity = self.get_json("/my/identity")
        accounts = identity.get("accounts", []) if isinstance(identity, dict) else []
        if len(accounts) != 1:
            raise RuntimeError(
                "Unable to auto-detect account slug: set FIZZY_ACCOUNT_SLUG (multiple/no accounts found)."
            )

        slug = accounts[0].get("slug", "")
        return str(slug).lstrip("/")


def ensure_board(client: FizzyClient, account_slug: str, board_name: str) -> str:
    boards = client.get_paginated(f"/{account_slug}/boards")
    for board in boards:
        if board.get("name") == board_name:
            return board["id"]

    client.request(
        "POST",
        f"/{account_slug}/boards",
        payload={"board": {"name": board_name, "all_access": True}},
        expected=(201,),
    )

    boards = client.get_paginated(f"/{account_slug}/boards")
    for board in boards:
        if board.get("name") == board_name:
            return board["id"]

    raise RuntimeError(f"Board create/lookup failed for '{board_name}'")


def ensure_columns(
    client: FizzyClient,
    account_slug: str,
    board_id: str,
    ordered_columns: List[str],
) -> Dict[str, str]:
    existing = client.get_paginated(f"/{account_slug}/boards/{board_id}/columns")
    existing_names = {column["name"] for column in existing}

    for index, name in enumerate(ordered_columns):
        if name in existing_names:
            continue
        color = COLUMN_COLORS[index % len(COLUMN_COLORS)]
        client.request(
            "POST",
            f"/{account_slug}/boards/{board_id}/columns",
            payload={"column": {"name": name, "color": color}},
            expected=(201,),
        )

    refreshed = client.get_paginated(f"/{account_slug}/boards/{board_id}/columns")
    return {column["name"]: column["id"] for column in refreshed}


def get_existing_synced_cards(
    client: FizzyClient,
    account_slug: str,
    board_id: str,
) -> Dict[str, dict]:
    query = urlencode([("board_ids[]", board_id), ("indexed_by", "all")])
    cards = client.get_paginated(f"/{account_slug}/cards?{query}")

    by_key: Dict[str, dict] = {}
    for card in cards:
        key = extract_sync_key(card.get("description") or "")
        if key:
            by_key[key] = card

    return by_key


def parse_created_card_number(headers: Dict[str, str]) -> Optional[str]:
    location = headers.get("Location") or headers.get("location")
    if not location:
        return None
    match = re.search(r"/cards/([^/.]+)", location)
    return match.group(1) if match else None


def reopen_card(client: FizzyClient, account_slug: str, card_number: str) -> None:
    client.request("DELETE", f"/{account_slug}/cards/{card_number}/closure", expected=(204,))


def close_card(client: FizzyClient, account_slug: str, card_number: str) -> None:
    client.request("POST", f"/{account_slug}/cards/{card_number}/closure", expected=(204,))


def move_card_to_column(
    client: FizzyClient,
    account_slug: str,
    card_number: str,
    column_id: str,
) -> None:
    client.request(
        "POST",
        f"/{account_slug}/cards/{card_number}/triage",
        payload={"column_id": column_id},
        expected=(204,),
    )


def build_description(
    item: ActionItem,
    action_doc_path: str,
    digest_branch: str,
) -> str:
    return "\n".join(
        [
            "Digest actionable item sync",
            f"Source doc: {action_doc_path}:{item.source_line}",
            f"Section: {item.heading}",
            f"Digest branch: {digest_branch}",
            "",
            item.details,
            "",
            f"{SYNC_KEY_PREFIX}{item.key}",
        ]
    )


def sync(
    client: FizzyClient,
    account_slug: str,
    board_id: str,
    column_ids: Dict[str, str],
    action_doc_path: str,
    digest_branch: str,
    items: List[ActionItem],
    close_obsolete: bool,
) -> Dict[str, int]:
    stats = {
        "created": 0,
        "updated": 0,
        "reopened": 0,
        "moved": 0,
        "closed_obsolete": 0,
        "unchanged": 0,
    }

    existing_by_key = get_existing_synced_cards(client, account_slug, board_id)
    desired_keys = {item.key for item in items}

    for item in items:
        card = existing_by_key.get(item.key)
        description = build_description(item, action_doc_path, digest_branch)
        column_id = column_ids[item.column]

        if card:
            card_number = str(card["number"])

            if card.get("closed"):
                reopen_card(client, account_slug, card_number)
                stats["reopened"] += 1

            needs_update = (
                card.get("title") != item.title
                or (card.get("description") or "") != description
            )
            if needs_update:
                client.request(
                    "PUT",
                    f"/{account_slug}/cards/{card_number}",
                    payload={"card": {"title": item.title, "description": description}},
                    expected=(200,),
                )
                stats["updated"] += 1
            else:
                stats["unchanged"] += 1

            move_card_to_column(client, account_slug, card_number, column_id)
            stats["moved"] += 1
            continue

        _, headers, _ = client.request(
            "POST",
            f"/{account_slug}/boards/{board_id}/cards",
            payload={"card": {"title": item.title, "description": description}},
            expected=(201,),
        )
        card_number = parse_created_card_number(headers)
        if not card_number:
            refreshed = get_existing_synced_cards(client, account_slug, board_id)
            created = refreshed.get(item.key)
            if not created:
                raise RuntimeError(f"Could not resolve new card number for '{item.title}'")
            card_number = str(created["number"])

        move_card_to_column(client, account_slug, card_number, column_id)
        stats["created"] += 1
        stats["moved"] += 1

    if close_obsolete:
        for key, card in existing_by_key.items():
            if key in desired_keys:
                continue
            if card.get("closed"):
                continue
            close_card(client, account_slug, str(card["number"]))
            stats["closed_obsolete"] += 1

    return stats


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--digest-repo",
        default=os.getenv("DIGEST_REPO_PATH", "/srv/digest"),
        help="Path to digest repo checkout (must be on dev branch)",
    )
    parser.add_argument(
        "--fizzy-api-base-url",
        default=os.getenv("FIZZY_API_BASE_URL", "http://localhost:3333"),
        help="Fizzy base URL",
    )
    parser.add_argument(
        "--fizzy-api-token",
        default=os.getenv("FIZZY_API_TOKEN"),
        help="Fizzy personal access token",
    )
    parser.add_argument(
        "--fizzy-account-slug",
        default=os.getenv("FIZZY_ACCOUNT_SLUG"),
        help="Fizzy account slug (numeric). Auto-discovered if omitted and only one account exists.",
    )
    parser.add_argument(
        "--fizzy-board-name",
        default=os.getenv("FIZZY_BOARD_NAME", "Digest Product Action Items"),
        help="Destination board name",
    )
    parser.add_argument(
        "--close-obsolete",
        dest="close_obsolete",
        action="store_true",
        default=env_bool("FIZZY_CLOSE_OBSOLETE", True),
        help="Close synced cards that no longer exist as unchecked items",
    )
    parser.add_argument(
        "--no-close-obsolete",
        dest="close_obsolete",
        action="store_false",
        help="Do not close cards that disappear from source doc",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only parse and print items; do not call Fizzy API",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    action_doc_path = os.path.join(args.digest_repo, ACTION_DOC_NAME)
    if not os.path.exists(action_doc_path):
        print(f"ERROR: Missing doc: {action_doc_path}", file=sys.stderr)
        return 2

    branch = current_git_branch(args.digest_repo)
    if not branch:
        print(f"ERROR: Could not determine git branch for {args.digest_repo}", file=sys.stderr)
        return 2

    if branch != REQUIRED_BRANCH:
        print(
            f"ERROR: Branch mismatch. Expected {REQUIRED_BRANCH}, found {branch}. "
            f"Refusing to sync from non-dev branch.",
            file=sys.stderr,
        )
        return 2

    items, section_order = parse_action_items(action_doc_path)
    if not items:
        print(f"No unchecked action items found in {action_doc_path}")
        return 0

    print(f"Found {len(items)} actionable items in {action_doc_path}")
    for section in section_order:
        count = sum(1 for item in items if item.column == section)
        print(f"- {section}: {count}")

    if args.dry_run:
        return 0

    if not args.fizzy_api_token:
        print("ERROR: Missing FIZZY_API_TOKEN / --fizzy-api-token", file=sys.stderr)
        return 2

    client = FizzyClient(args.fizzy_api_base_url, args.fizzy_api_token)
    account_slug = (args.fizzy_account_slug or client.discover_account_slug()).lstrip("/")

    board_id = ensure_board(client, account_slug, args.fizzy_board_name)
    column_ids = ensure_columns(client, account_slug, board_id, section_order)
    stats = sync(
        client=client,
        account_slug=account_slug,
        board_id=board_id,
        column_ids=column_ids,
        action_doc_path=action_doc_path,
        digest_branch=branch,
        items=items,
        close_obsolete=args.close_obsolete,
    )

    print("Sync complete")
    for key in ("created", "updated", "reopened", "moved", "closed_obsolete", "unchanged"):
        print(f"- {key}: {stats[key]}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
