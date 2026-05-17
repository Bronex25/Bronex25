#!/usr/bin/env python3
"""Poll Gmail for Idealista alert emails and forward each new listing to Telegram.

Pipeline:
  Gmail IMAP  →  HTML→text  →  Claude (extract + analyze)  →  Telegram

Claude both extracts listings from each alert email and produces a short
Telegram-ready summary including commute estimates to Aticco Urquinaona and
Aticco Diagrame. Listings are deduplicated against seen.json by canonical URL.
"""
from __future__ import annotations

import email
import imaplib
import json
import os
import re
import subprocess
import sys
from email.message import Message
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

GMAIL_USERNAME = os.environ["GMAIL_USERNAME"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]
TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

SEEN_PATH = Path(__file__).parent / "seen.json"
MAX_SEEN = 2000
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

GMAIL_HOST = "imap.gmail.com"
GMAIL_SEARCH = '(X-GM-RAW "from:idealista.com newer_than:3d")'

CLAUDE_BIN = os.environ.get("CLAUDE_BIN", "claude")
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")
CLAUDE_TIMEOUT = 180

ATICCO_URQUINAONA = "Aticco Urquinaona (Pl. d'Urquinaona, Eixample) — metro L1/L4 Urquinaona"
ATICCO_DIAGRAME = "Aticco Diagrame (Carrer de Pere IV 105, Poblenou / 22@) — metro L1 Glòries, L4 Llacuna"

CLAUDE_PROMPT_TEMPLATE = """You are processing an Idealista alert email for a Barcelona apartment hunter
who works at two coworking offices:
  * {urquinaona}
  * {diagrame}

For each distinct apartment listing in the email, produce one Telegram message.
The message is HTML (parse_mode=HTML). You may use <b>, <i>, <a>, real newlines,
and emojis. Do NOT use <br>, headings, or code fences.

Use this exact layout, OMITTING any line whose data is not visible in the email
(do not invent facts). Keep each line short — one line, no wrap-padding.

🏠 <b>{{TITLE in original Spanish/Catalan}}</b>
💶 {{price}}/mo · 📐 {{m²}} m² · 🛏 {{N}} bed · 🏢 {{floor}}
✨ {{up to 4 extras visible in the email, " · " separated: lift, furnished, terrace, balcony, parking, AC, heating, pets, exterior, renovated, etc.}}
💰 {{€/m²}} — <i>{{one word verdict vs Barcelona market for that neighborhood: cheap, fair, pricey, or skip the whole line if unknown}}</i>

📍 <i>{{one short sentence on the neighborhood; skip if you don't actually know it}}</i>

🚇 <b>Urquinaona</b> · ~{{N}} min — {{short route, e.g. "M L4 Jaume I, 4 stops" or "Rodalies R1 → Arc de Triomf → L1, +8 min walk"}}
🚇 <b>Diagrame</b> · ~{{N}} min — {{short route}}

🔗 <a href="{{URL}}">Ver anuncio</a>

Extra rules:
- Commute is door-to-door (walk + transit + walk), single integer minutes.
- If you genuinely cannot estimate a commute (no address visible at all), write "n/a" instead of a number and skip the route.
- If BOTH commutes are >50 min, prepend this line to the message:
  ⚠️ <i>Far from both offices</i>
- Price-per-m² verdict: only include it if you can compute €/m² AND have reasonable confidence about that neighborhood's rental market. Otherwise omit the whole 💰 line.
- Keep the message under 800 characters total.

Output strict JSON: an array of objects, each with keys:
  "listing_id"   -> canonical idealista.com URL of the listing (used for dedup)
  "telegram_html" -> the message body as described above

Output ONLY the JSON array, no prose, no code fences.
If the email contains zero listings, output [].

EMAIL SUBJECT: {subject}

EMAIL BODY:
{body}
"""


def load_seen() -> list[str]:
    if not SEEN_PATH.exists():
        return []
    return json.loads(SEEN_PATH.read_text())


def save_seen(seen: list[str]) -> None:
    SEEN_PATH.write_text(json.dumps(seen[-MAX_SEEN:], indent=2) + "\n")


def fetch_emails() -> list[Message]:
    with imaplib.IMAP4_SSL(GMAIL_HOST) as imap:
        imap.login(GMAIL_USERNAME, GMAIL_APP_PASSWORD)
        imap.select("INBOX", readonly=True)
        typ, data = imap.search(None, GMAIL_SEARCH)
        if typ != "OK" or not data or not data[0]:
            return []
        uids = data[0].split()
        messages: list[Message] = []
        for uid in uids:
            typ, fetched = imap.fetch(uid, "(BODY.PEEK[])")
            if typ != "OK" or not fetched:
                continue
            for part in fetched:
                if isinstance(part, tuple) and len(part) >= 2:
                    messages.append(email.message_from_bytes(part[1]))
                    break
        return messages


def extract_body_text(msg: Message) -> str:
    html_part: str | None = None
    text_part: str | None = None
    for part in msg.walk():
        ctype = part.get_content_type()
        if ctype not in ("text/html", "text/plain"):
            continue
        payload = part.get_payload(decode=True)
        if payload is None:
            continue
        charset = part.get_content_charset() or "utf-8"
        try:
            decoded = payload.decode(charset, errors="replace")
        except LookupError:
            decoded = payload.decode("utf-8", errors="replace")
        if ctype == "text/html" and html_part is None:
            html_part = decoded
        elif ctype == "text/plain" and text_part is None:
            text_part = decoded

    if html_part:
        soup = BeautifulSoup(html_part, "html.parser")
        for tag in soup(["script", "style"]):
            tag.decompose()
        # Preserve hrefs so Claude sees the canonical listing URLs.
        for a in soup.find_all("a", href=True):
            href = a["href"]
            label = a.get_text(strip=True)
            a.replace_with(f"{label} <{href}>" if label else f"<{href}>")
        text = soup.get_text("\n", strip=True)
        return re.sub(r"\n{3,}", "\n\n", text)
    return text_part or ""


def decode_header(value: str | None) -> str:
    if not value:
        return ""
    parts = email.header.decode_header(value)
    out = []
    for chunk, enc in parts:
        if isinstance(chunk, bytes):
            out.append(chunk.decode(enc or "utf-8", errors="replace"))
        else:
            out.append(chunk)
    return "".join(out).strip()


def call_claude(subject: str, body: str) -> list[dict]:
    prompt = CLAUDE_PROMPT_TEMPLATE.format(
        urquinaona=ATICCO_URQUINAONA,
        diagrame=ATICCO_DIAGRAME,
        subject=subject,
        body=body[:18000],  # keep prompt well under context limits
    )
    proc = subprocess.run(
        [CLAUDE_BIN, "-p", "--output-format", "text", "--model", CLAUDE_MODEL],
        input=prompt,
        capture_output=True,
        text=True,
        timeout=CLAUDE_TIMEOUT,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"claude exited {proc.returncode}: {proc.stderr.strip()[:500]}")

    raw = proc.stdout.strip()
    # Tolerate code fences in case Claude wraps despite instructions.
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", raw, flags=re.DOTALL)
    if fence:
        raw = fence.group(1).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Claude returned non-JSON: {e}\n---\n{raw[:500]}")


def canonical_listing_id(url: str) -> str:
    m = re.search(r"idealista\.com/(?:[a-z]+/)?inmueble/(\d+)", url)
    return f"idealista:{m.group(1)}" if m else url


def send_telegram(html: str) -> None:
    resp = httpx.post(
        f"{TELEGRAM_API}/sendMessage",
        json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": html,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        },
        timeout=30.0,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Telegram API {resp.status_code}: {resp.text}")


def main() -> int:
    seen = load_seen()
    seen_set = set(seen)

    messages = fetch_emails()
    print(f"Fetched {len(messages)} idealista email(s) from Gmail")

    sent = 0
    try:
        for msg in messages:
            subject = decode_header(msg.get("Subject"))
            body = extract_body_text(msg)
            if not body.strip():
                continue
            listings = call_claude(subject, body)
            print(f"  email '{subject[:60]}' → {len(listings)} listing(s)")
            for listing in listings:
                lid = canonical_listing_id(str(listing.get("listing_id", "")))
                if not lid or lid in seen_set:
                    continue
                send_telegram(listing["telegram_html"])
                seen.append(lid)
                seen_set.add(lid)
                sent += 1
    finally:
        save_seen(seen)

    print(f"Sent {sent} new listing(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
