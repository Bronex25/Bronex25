# Idealista → Telegram notifier

Polls a Gmail inbox every 15 minutes for Idealista alert emails, asks Claude (via your Max-plan OAuth token) to extract each listing and produce a short Barcelona-specific summary — including estimated metro commute to **Aticco Urquinaona** and **Aticco Diagrame** — and posts one message per listing to a Telegram chat with photos as an album. Runs entirely on GitHub Actions, no server.

```
Gmail IMAP  →  HTML→text  →  Claude (extract + analyze)  →  Telegram
```

Already-seen listing URLs are tracked in `seen.json`, which the workflow commits back so nothing is sent twice.

## What you get per listing

```
🏠 Piso en alquiler · 2 hab · Gràcia
💶 1450 €/mo · 📐 68 m² · 🛏 2 bed · 🏢 3rd floor
✨ Lift · Furnished · Balcony · Exterior
💰 21 €/m² — fair

📍 Gràcia is a low-rise, lively neighbourhood with plazas and indie bars.

🚇 Urquinaona · ~14 min — M L3 Fontana, +3 min walk + L1 transfer
🚇 Diagrame · ~22 min — M L4 Joanic to Llacuna, +6 min walk

🔗 Ver anuncio
```

…with up to 8 listing photos attached as a Telegram album. If both commutes are >50 min the message is prefixed `⚠️ Far from both offices`.

## Setup

### 1. Telegram bot + chat ID

1. Message **@BotFather** with `/newbot` and save the token.
2. Send your bot any message (or, for a group, add it and `@mention` it).
3. Open `https://api.telegram.org/bot<TOKEN>/getUpdates` and copy the `chat.id`. Groups have negative IDs.

### 2. Gmail app password

1. Point your Idealista saved-search alerts at the Gmail address that will be polled.
2. Enable 2-Step Verification at https://myaccount.google.com/security.
3. Open https://myaccount.google.com/apppasswords, create a password called `idealista-bot`, copy the 16 characters with **no spaces**.

### 3. Claude Max OAuth token (one-time, on a desktop)

```bash
# macOS / Linux
curl -fsSL https://claude.ai/install.sh | bash
# or Windows
npm install -g @anthropic-ai/claude-code

claude              # /login → sign in with your Max account
claude setup-token  # prints a long-lived sk-ant-oat... token
```

The token authenticates the CLI against your Max subscription, so per-call cost is zero.

### 4. Repo secrets

Under **Settings → Secrets and variables → Actions**, add:

| Name | Value |
| ---- | ----- |
| `GMAIL_USERNAME` | The Gmail address polled for alerts |
| `GMAIL_APP_PASSWORD` | The 16-character app password (no spaces) |
| `TELEGRAM_BOT_TOKEN` | Token from BotFather |
| `TELEGRAM_CHAT_ID` | Chat or group ID from `getUpdates` |
| `CLAUDE_CODE_OAUTH_TOKEN` | `sk-ant-oat…` token from `claude setup-token` |

### 5. Trigger

Wait up to 15 min for the next cron, or run **Actions → Idealista notifier → Run workflow**.

## Local development

```bash
pip install -r requirements.txt
export GMAIL_USERNAME="you@gmail.com"
export GMAIL_APP_PASSWORD="xxxxxxxxxxxxxxxx"
export TELEGRAM_BOT_TOKEN="123:abc"
export TELEGRAM_CHAT_ID="-100123456789"
export CLAUDE_CODE_OAUTH_TOKEN="sk-ant-oat-..."
python idealista_notify.py
```

Requires the `claude` CLI on `PATH` (see step 3).

## Customization

| What | Where |
| ---- | ----- |
| Commute destinations | `ATICCO_URQUINAONA` / `ATICCO_DIAGRAME` in `idealista_notify.py` |
| Message layout / language | `CLAUDE_PROMPT_TEMPLATE` in `idealista_notify.py` |
| Gmail sender filter / lookback | `GMAIL_SEARCH` (Gmail `X-GM-RAW` syntax) |
| Poll interval | `cron` in `.github/workflows/notify.yml` (GitHub minimum 5 min) |
| Claude model | `CLAUDE_MODEL` env var (defaults to `claude-sonnet-4-6`) |

## Robustness

The notifier survives common failure modes:

- **Per-email isolation** — a Claude timeout on one email doesn't drop the rest of the batch.
- **Per-listing isolation** — a single bad Telegram send is logged and skipped.
- **Photo-fetch fallback** — if Telegram can't pull a listing's images from the Idealista CDN, the message is re-sent as text-only so it isn't lost.
- **Telegram 429 / 5xx retry** — honours `retry_after` from rate-limit responses, exponential backoff on transient 5xx.
- **Concurrent `seen.json` push** — rebases onto the latest `main` and retries with backoff if the push is rejected (PR merges, queued runs).
- **Caption HTML safety** — long messages are truncated at a newline and any dangling `<b>` / `<i>` / `<a>` tags are auto-closed before sending.
