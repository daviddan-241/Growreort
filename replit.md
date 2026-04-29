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

### Deploy on Render (Background Worker)

The bot has no HTTP server — it must run as a **Background Worker**, not a Web Service.

1. New + → Background Worker → connect the GitHub repo.
2. Settings:
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python bot/bot.py`
   - **Branch**: `main`
3. Environment Variables:
   - `DISCORD_BOT_TOKEN` = your bot token (from Discord Developer Portal)
4. Click **Create Background Worker**. Render will install deps and start the bot. Watch the logs for `Logged in as Baldwin#9901`.

Notes:
- `requirements.txt` lists `discord.py>=2.7.1` for Render's Python builder.
- Render's free Background Worker tier has limited monthly hours; upgrade to Starter ($7/mo) for 24/7 uptime.
