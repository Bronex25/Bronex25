# Idealista → Telegram notifier

Polls an Idealista RSS feed every 15 minutes via GitHub Actions and sends new listings to a Telegram chat. Already-seen listing IDs are tracked in `seen.json`, which the workflow commits back to the repo, so you never get the same listing twice.

## Setup

### 1. Create a Telegram bot and get your chat ID

1. Open Telegram, search for **@BotFather**, send `/newbot` and follow the prompts. Save the bot token it gives you (looks like `123456789:ABC-DEF...`).
2. Open a chat with your new bot and send it any message (e.g. `hi`).
3. In a browser, visit `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` and look for `"chat":{"id":<NUMBER>,...}` — that number is your chat ID. (For a group, add the bot to the group first; the chat ID will be negative.)

### 2. Get your Idealista RSS feed URL

1. Run the search you want on idealista.com (set city, price, rooms, etc.).
2. On the results page, click **Receive new properties** / "Recibir nuevos inmuebles" to save the search.
3. From the saved searches page, copy the RSS link (the orange RSS icon next to the saved search).

### 3. Add the three secrets to this repo

Go to **Settings → Secrets and variables → Actions** and add:

| Name | Value |
| ---- | ----- |
| `IDEALISTA_RSS_URL` | The RSS URL from step 2 |
| `TELEGRAM_BOT_TOKEN` | The bot token from step 1 |
| `TELEGRAM_CHAT_ID` | The chat ID from step 1 |

### 4. Enable the workflow

The first scheduled run can take up to 15 minutes. To test immediately, go to **Actions → Idealista notifier → Run workflow**.

## Local testing

```bash
pip install -r requirements.txt
export IDEALISTA_RSS_URL="https://..."
export TELEGRAM_BOT_TOKEN="123:abc"
export TELEGRAM_CHAT_ID="123456"
python idealista_notify.py
```

## Tweaks

- **Poll interval**: edit the cron in `.github/workflows/notify.yml`. Note GitHub's minimum is 5 minutes and scheduled runs can be delayed under load.
- **Multiple searches**: add more secrets (`IDEALISTA_RSS_URL_2`, ...) and extend `idealista_notify.py` to loop over them, or duplicate the workflow file.
- **Message format**: see `format_message` in `idealista_notify.py`.
