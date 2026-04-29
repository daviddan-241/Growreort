# Workspace

## Overview

pnpm workspace monorepo using TypeScript. Each package manages its own dependencies.

## Stack

- **Monorepo tool**: pnpm workspaces
- **Node.js version**: 24
- **Package manager**: pnpm
- **TypeScript version**: 5.9
- **API framework**: Express 5
- **Database**: PostgreSQL + Drizzle ORM
- **Validation**: Zod (`zod/v4`), `drizzle-zod`
- **API codegen**: Orval (from OpenAPI spec)
- **Build**: esbuild (CJS bundle)

## Key Commands

- `pnpm run typecheck` — full typecheck across all packages
- `pnpm run build` — typecheck + build all packages
- `pnpm --filter @workspace/api-spec run codegen` — regenerate API hooks and Zod schemas from OpenAPI spec
- `pnpm --filter @workspace/db run push` — push DB schema changes (dev only)
- `pnpm --filter @workspace/api-server run dev` — run API server locally

See the `pnpm-workspace` skill for workspace structure, TypeScript setup, and package details.

## Discord Bot (`bot/`)

- `bot/bot.py` — Discord bot using discord.py 2.x (Python 3.11). Reads `DISCORD_BOT_TOKEN` from secrets.
- Slash command `/webhooks` (admin-only) creates a webhook named `BaldwinHook` for each configured channel and DMs the URLs to the invoker.
- DM trigger: any DM message to the bot also triggers webhook generation (10s cooldown per user).
- Run by the `Discord Bot` workflow.

### Deploy on Render (Free Web Service)

Render's free tier doesn't include Background Workers, so the bot also runs a tiny HTTP server (port `$PORT`, route `/healthz`) so it can deploy as a free **Web Service**.

The repo includes `render.yaml` — Render auto-detects it (Blueprint deploy):

1. Render dashboard → **New +** → **Blueprint** → connect repo `daviddan-241/Growreort`.
2. Render reads `render.yaml`. When prompted, paste your `DISCORD_BOT_TOKEN`.
3. Click **Apply**. Build runs `pip install -r requirements.txt`, then `python bot/bot.py` starts. Logs show `Logged in as Baldwin#9901` and `HTTP keep-alive server listening on :<port>`.

Manual fallback (no Blueprint):
- New + → **Web Service** → connect repo
- Runtime: `Python 3`
- Build Command: `pip install -r requirements.txt`
- Start Command: `python bot/bot.py`
- Health Check Path: `/healthz`
- Env Vars: `DISCORD_BOT_TOKEN` = your token

Free tier sleep:
- Render free Web Services sleep after **15 min of no inbound HTTP traffic**. The Discord gateway connection alone won't keep it awake.
- To stay online 24/7, ping the Render URL every ~10 min from a free uptime monitor (UptimeRobot, cron-job.org, BetterStack). Use the public URL Render gives you (e.g. `https://baldwin-discord-bot.onrender.com/healthz`).
