# Kurtex CRM Panel

A web-based admin panel for managing Kurtex bot cases, users, and reports.
Connects to the **same MongoDB database** as the Telegram bot — no extra setup.

## Features

- 📊 **Dashboard** — Today's and weekly stats at a glance
- 📋 **Cases** — Full table with search, status filters, date range, agent filter, pagination
- 🔍 **Case Detail Drawer** — Click any case to see full details instantly
- 👥 **Team Members** — All users with roles and case counts
- 🏆 **Leaderboard** — Weekly agent performance ranking
- 🔐 **Telegram Login** — Users authenticate via Telegram Login Widget
- 📱 **Mobile Responsive** — Collapsible sidebar, works on all screen sizes
- 🔒 **Role-based Access** — Agents see only their cases; managers/TLs/devs see everything

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env
# Edit .env with your MongoDB URI, bot token, etc.

# 3. Run
python app.py
```

Open http://localhost:5000

## Setup: Telegram Login Widget

1. Message @BotFather → `/setdomain` → select your bot → enter your domain
   - For local dev: `localhost` works for testing with the dev login bypass
2. Set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_BOT_USERNAME` in `.env`
3. The login page will show the Telegram Login Button automatically

## Development / Local Testing

If `TELEGRAM_BOT_TOKEN` is **not** set in `.env`, the panel runs in **dev mode**:
- A "Development Mode" fallback appears on the login page
- Enter any user's Telegram ID to log in without Telegram verification
- This is safe — it only works when no bot token is configured

## Deploy to Railway

1. Add this as a **new service** in your Railway project
2. Set the same environment variables as the bot (`MONGODB_URI`, `MONGODB_DB`)
3. Add `SECRET_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_BOT_USERNAME`
4. Railway auto-detects Python → runs `python app.py`
5. Set the Railway domain in @BotFather via `/setdomain`

## Role Permissions

| Role        | Cases visible | Users panel | Leaderboard |
|-------------|---------------|-------------|-------------|
| agent       | Own only      | ✗           | ✗           |
| team_leader | All           | ✓           | ✓           |
| manager     | All           | ✓           | ✓           |
| developer   | All           | ✓           | ✓           |

## Project Structure

```
kurtex-crm/
├── app.py              # Flask backend + all API routes
├── requirements.txt
├── .env.example
└── templates/
    ├── login.html      # Telegram login page
    └── dashboard.html  # Full CRM SPA
```
