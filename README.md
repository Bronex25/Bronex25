# Idealista → Telegram notifier

Polls a Gmail inbox every 15 minutes via GitHub Actions for Idealista alert emails, hands each email to Claude (Claude Max via OAuth) for listing extraction and Barcelona-specific analysis — including estimated metro commute to **Aticco Urquinaona** and **Aticco Diagrame** — and forwards a short summary per listing to a Telegram chat. Already-seen listing URLs are tracked in `seen.json`, which the workflow commits back so nothing is sent twice.

## Setup

### 1. Telegram bot + chat ID

1. In Telegram, message **@BotFather** with `/newbot`, save the token.
2. Send your bot any message.
3. Open `https://api.telegram.org/bot<TOKEN>/getUpdates` and copy the `chat.id` value.

### 2. Gmail app password

1. In Idealista, set your saved-search alerts to email `s.plaxn25@gmail.com` (or whatever inbox you want polled).
2. Enable 2-Step Verification at https://myaccount.google.com/security.
3. Go to **App passwords**, create one for "Mail", and copy the 16-character password.

### 3. Claude Max OAuth token (one-time desktop step)

On any computer:

```bash
curl -fsSL https://claude.ai/install.sh | bash   # macOS / Linux
# or: npm install -g @anthropic-ai/claude-code   # Windows
claude              # then /login → sign in with your Max account
claude setup-token  # prints sk-ant-oat...
```

Copy the printed token — it's a long-lived OAuth token tied to your Max plan.

### 4. Repo secrets

At https://github.com/bronex25/bronex25/settings/secrets/actions add:

| Name | Value |
| ---- | ----- |
| `GMAIL_USERNAME` | The Gmail address (e.g. `s.plaxn25@gmail.com`) |
| `GMAIL_APP_PASSWORD` | The 16-character app password (no spaces) |
| `TELEGRAM_BOT_TOKEN` | Token from BotFather |
| `TELEGRAM_CHAT_ID` | Chat ID from `getUpdates` |
| `CLAUDE_CODE_OAUTH_TOKEN` | `sk-ant-oat…` token from `claude setup-token` |

### 5. Trigger it

Wait up to 15 minutes for the next cron, or run **Actions → Idealista notifier → Run workflow** to test immediately.

## Local testing

```bash
pip install -r requirements.txt
export GMAIL_USERNAME="you@gmail.com"
export GMAIL_APP_PASSWORD="xxxxxxxxxxxxxxxx"
export TELEGRAM_BOT_TOKEN="123:abc"
export TELEGRAM_CHAT_ID="123456"
export CLAUDE_CODE_OAUTH_TOKEN="sk-ant-oat-..."
python idealista_notify.py
```

Requires the `claude` CLI on `PATH`. The OAuth token authenticates the CLI against your Max subscription (no per-call billing).

## Tweaks

- **Poll interval**: cron in `.github/workflows/notify.yml` (GitHub minimum is 5 min).
- **Commute destinations**: edit `ATICCO_URQUINAONA` and `ATICCO_DIAGRAME` in `idealista_notify.py`.
- **Message style/language**: edit `CLAUDE_PROMPT_TEMPLATE` in `idealista_notify.py`.
- **Sender filter or lookback window**: edit `GMAIL_SEARCH` (Gmail search syntax via `X-GM-RAW`).
