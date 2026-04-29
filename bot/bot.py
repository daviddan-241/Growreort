import asyncio
import logging
import os
import sys
import time

import discord
from aiohttp import web
from discord import app_commands

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("baldwin-bot")

TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
if not TOKEN:
    log.error("DISCORD_BOT_TOKEN is not set")
    sys.exit(1)

WEBHOOK_NAME = "BaldwinHook"
DM_COOLDOWN_SECONDS = 10

_dm_cooldowns: dict[int, float] = {}


class BaldwinBot(discord.Client):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.guilds = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self) -> None:
        await self.tree.sync()
        log.info("Slash commands synced")


bot = BaldwinBot()


@bot.event
async def on_ready() -> None:
    log.info("Logged in as %s (id=%s)", bot.user, bot.user.id if bot.user else "?")
    log.info("Connected to %d guild(s):", len(bot.guilds))
    for g in bot.guilds:
        log.info("  - %s (id=%s, owner_id=%s)", g.name, g.id, g.owner_id)


def chunk_message(lines: list[str], limit: int = 1900) -> list[str]:
    chunks: list[str] = []
    current = ""
    for line in lines:
        if len(current) + len(line) + 1 > limit:
            chunks.append(current)
            current = ""
        current += line + "\n"
    if current:
        chunks.append(current)
    return chunks


async def send_dm_chunks(user: discord.abc.User, lines: list[str]) -> bool:
    chunks = chunk_message(lines)
    try:
        for chunk in chunks:
            await user.send(chunk)
        return True
    except discord.Forbidden:
        return False
    except Exception as exc:
        log.exception("Failed sending DM: %s", exc)
        return False


async def resolve_member(guild: discord.Guild, user_id: int) -> discord.Member | None:
    member = guild.get_member(user_id)
    if member is not None:
        return member
    try:
        return await guild.fetch_member(user_id)
    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        return None


async def user_can_manage(guild: discord.Guild, user_id: int) -> tuple[bool, str]:
    """Return (allowed, reason). reason is for debug logging when denied."""
    if guild.owner_id == user_id:
        return True, "owner"
    member = await resolve_member(guild, user_id)
    if member is None:
        return False, "not a member of the guild"
    perms = member.guild_permissions
    if perms.administrator:
        return True, "administrator"
    if perms.manage_webhooks:
        return True, "manage_webhooks"
    return (
        False,
        f"missing perms (admin={perms.administrator}, "
        f"manage_webhooks={perms.manage_webhooks}, "
        f"manage_guild={perms.manage_guild})",
    )


async def collect_webhooks(
    guild: discord.Guild,
) -> tuple[list[tuple[str, str, str]], list[tuple[str, str]]]:
    """For every text channel in the guild, ensure a BaldwinHook webhook exists.

    Returns:
      - list of (category_name, channel_name, webhook_url)
      - list of (channel_name, error_reason) for failures
    """
    results: list[tuple[str, str, str]] = []
    failed: list[tuple[str, str]] = []

    channels = sorted(
        guild.text_channels,
        key=lambda c: (c.category.position if c.category else -1, c.position),
    )

    for channel in channels:
        category_name = channel.category.name if channel.category else "(no category)"
        try:
            existing = await channel.webhooks()
            hook = next((h for h in existing if h.name == WEBHOOK_NAME), None)
            if hook is None:
                hook = await channel.create_webhook(name=WEBHOOK_NAME)
            results.append((category_name, channel.name, hook.url))
        except discord.Forbidden:
            failed.append((channel.name, "missing permission"))
        except discord.HTTPException as exc:
            failed.append((channel.name, f"HTTP {exc.status}"))
        except Exception as exc:
            log.exception("Unexpected error for %s", channel.name)
            failed.append((channel.name, str(exc)))

    return results, failed


def format_results(
    guild: discord.Guild,
    results: list[tuple[str, str, str]],
    failed: list[tuple[str, str]],
) -> list[str]:
    lines = [f"**Webhooks for `{guild.name}`** ({len(results)} channels)", ""]
    current_category: str | None = None
    for category, name, url in results:
        if category != current_category:
            lines.append(f"__**{category}**__")
            current_category = category
        lines.append(f"**{name}**\n{url}\n")
    if failed:
        lines.append("\n**Failed:**")
        for name, reason in failed:
            lines.append(f"- {name} ({reason})")
    return lines


async def find_eligible_guilds(user_id: int) -> list[discord.Guild]:
    eligible: list[discord.Guild] = []
    for guild in bot.guilds:
        allowed, reason = await user_can_manage(guild, user_id)
        log.info("guild=%s eligible=%s reason=%s", guild.name, allowed, reason)
        if allowed:
            eligible.append(guild)
    return eligible


async def run_for_guild(user: discord.abc.User, guild: discord.Guild) -> None:
    me = guild.me
    if me is None or not me.guild_permissions.manage_webhooks:
        await send_dm_chunks(
            user,
            [
                f"I don't have **Manage Webhooks** permission in `{guild.name}`. "
                "Please grant the bot that permission and try again."
            ],
        )
        return

    results, failed = await collect_webhooks(guild)
    lines = format_results(guild, results, failed)
    await send_dm_chunks(user, lines)


async def handle_dm_request(user: discord.abc.User) -> None:
    eligible = await find_eligible_guilds(user.id)

    if not eligible:
        await send_dm_chunks(
            user,
            [
                "I couldn't find any server we share where you have **Manage "
                "Webhooks** permission or are the owner.\n\n"
                "Checks I run, in order:\n"
                "1. Are you the server owner?\n"
                "2. Do you have Administrator or Manage Webhooks permission?\n\n"
                "Make sure I'm in your server and you have one of those."
            ],
        )
        return

    if len(eligible) > 1:
        names = "\n".join(f"- {g.name}" for g in eligible)
        await send_dm_chunks(
            user,
            [
                f"Generating webhooks for **{len(eligible)}** server(s):\n{names}"
            ],
        )

    for guild in eligible:
        await run_for_guild(user, guild)


@bot.event
async def on_message(message: discord.Message) -> None:
    if message.author.bot:
        return
    if message.guild is not None:
        return

    user = message.author
    now = time.time()
    last = _dm_cooldowns.get(user.id, 0)
    if now - last < DM_COOLDOWN_SECONDS:
        return
    _dm_cooldowns[user.id] = now

    log.info("DM trigger from user_id=%s", user.id)
    await handle_dm_request(user)


@bot.tree.command(
    name="webhooks",
    description="Create webhooks for the configured channels and DM the URLs to you.",
)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.allowed_installs(guilds=True, users=True)
async def webhooks(interaction: discord.Interaction) -> None:
    if interaction.guild is None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        await handle_dm_request(interaction.user)
        await interaction.followup.send(
            "Done — check your DMs.", ephemeral=True
        )
        return

    allowed, reason = await user_can_manage(interaction.guild, interaction.user.id)
    log.info(
        "/webhooks invoked by user_id=%s in guild=%s allowed=%s reason=%s",
        interaction.user.id,
        interaction.guild.name,
        allowed,
        reason,
    )
    if not allowed:
        await interaction.response.send_message(
            "You need **Manage Webhooks** permission (or be the server owner) "
            f"to use this command.\n_Debug:_ `{reason}`",
            ephemeral=True,
        )
        return

    me = interaction.guild.me
    if me is None or not me.guild_permissions.manage_webhooks:
        await interaction.response.send_message(
            "I don't have the **Manage Webhooks** permission in this server.",
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True, thinking=True)

    results, failed = await collect_webhooks(interaction.guild)
    lines = format_results(interaction.guild, results, failed)
    delivered = await send_dm_chunks(interaction.user, lines)

    if delivered:
        await interaction.followup.send(
            f"Done. Created/refreshed **{len(results)}** webhook(s). "
            f"Sent the URLs to your DMs."
            + (f"\nFailed: {len(failed)}." if failed else ""),
            ephemeral=True,
        )
    else:
        await interaction.followup.send(
            "I couldn't DM you — please enable DMs from server members and run "
            "the command again.",
            ephemeral=True,
        )


async def _health(_request: web.Request) -> web.Response:
    return web.Response(text="ok")


async def start_http_server() -> None:
    """Tiny HTTP server so the bot can run as a Render Web Service (free tier)."""
    port = int(os.environ.get("PORT", "0"))
    if port == 0:
        return
    app = web.Application()
    app.router.add_get("/", _health)
    app.router.add_get("/healthz", _health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    log.info("HTTP keep-alive server listening on :%s", port)


async def run_bot() -> None:
    async with bot:
        await start_http_server()
        await bot.start(TOKEN)


def main() -> None:
    try:
        asyncio.run(run_bot())
    except discord.LoginFailure:
        log.error(
            "Invalid bot token. Reset it in the Discord Developer Portal "
            "and update the DISCORD_BOT_TOKEN secret."
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
