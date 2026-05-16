#!/usr/bin/env python3
"""Poll an Idealista RSS feed and forward new listings to a Telegram chat."""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

import httpx

RSS_URL = os.environ["IDEALISTA_RSS_URL"]
TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

SEEN_PATH = Path(__file__).parent / "seen.json"
MAX_SEEN = 2000
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def load_seen() -> list[str]:
    if not SEEN_PATH.exists():
        return []
    return json.loads(SEEN_PATH.read_text())


def save_seen(seen: list[str]) -> None:
    trimmed = seen[-MAX_SEEN:]
    SEEN_PATH.write_text(json.dumps(trimmed, indent=2) + "\n")


def fetch_feed() -> list[dict]:
    resp = httpx.get(
        RSS_URL,
        headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/xml;q=0.9, */*;q=0.8"},
        timeout=30.0,
        follow_redirects=True,
    )
    resp.raise_for_status()
    root = ET.fromstring(resp.content)
    items: list[dict] = []
    for item in root.iter("item"):
        guid = (item.findtext("guid") or item.findtext("link") or "").strip()
        if not guid:
            continue
        items.append({
            "id": guid,
            "title": (item.findtext("title") or "").strip(),
            "link": (item.findtext("link") or "").strip(),
            "description": (item.findtext("description") or "").strip(),
            "pub_date": (item.findtext("pubDate") or "").strip(),
        })
    return items


def strip_html(text: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</p>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def escape_html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def format_message(item: dict) -> str:
    title = escape_html(item["title"])[:200]
    desc = escape_html(strip_html(item["description"]))[:600]
    link = item["link"]

    parts = [f"<b>{title}</b>"]
    if desc:
        parts.append(desc)
    if link:
        parts.append(f'<a href="{escape_html(link)}">View on Idealista</a>')
    return "\n\n".join(parts)


def send_telegram(item: dict) -> None:
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": format_message(item),
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }
    resp = httpx.post(f"{TELEGRAM_API}/sendMessage", json=payload, timeout=30.0)
    if resp.status_code != 200:
        raise RuntimeError(f"Telegram API {resp.status_code}: {resp.text}")


def main() -> int:
    seen = load_seen()
    seen_set = set(seen)

    feed = fetch_feed()
    new_items = [item for item in feed if item["id"] not in seen_set]
    new_items.reverse()  # oldest first so chat order matches publication order

    print(f"Feed items: {len(feed)} | new: {len(new_items)}")

    sent = 0
    try:
        for item in new_items:
            send_telegram(item)
            seen.append(item["id"])
            sent += 1
    finally:
        save_seen(seen)

    print(f"Sent {sent} new listing(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
