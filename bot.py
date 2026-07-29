import logging
import os

import discord
from discord.ext import commands

from config import (
    APPROVED_GUILD_IDS,
    DATABASE_URL,
    DEVELOPER_IDS,
    DISCORD_TOKEN,
    LEAVE_UNAPPROVED_GUILDS,
    UNAUTHORISED_GUILD_MESSAGE,
)
from database import Database
from cogs.appeals import AppealsCog
from cogs.dashboard import DashboardCog
from cogs.voting import VotingCog

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("appeals-bot")


class AppealsBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        super().__init__(command_prefix="!", intents=intents)
        self.db: Database = None

    async def setup_hook(self):
        self.db = Database(DATABASE_URL)
        await self.db.initialise()

        await self.add_cog(DashboardCog(self))
        await self.add_cog(AppealsCog(self))
        await self.add_cog(VotingCog(self))

        await self.tree.sync()
        logger.info("Slash commands synced.")

    async def on_ready(self):
        logger.info("Logged in as %s (%s)", self.user, self.user.id)

        if not APPROVED_GUILD_IDS:
            logger.error(
                "\n"
                "  *** APPROVED_GUILD_IDS IS EMPTY ***\n"
                "  The bot will leave every server it joins.\n"
                "  Set APPROVED_GUILD_IDS in Railway's Variables tab.\n"
                "  Example: APPROVED_GUILD_IDS=123456789012345678,987654321098765432\n"
            )

        # Register persistent views so buttons survive restarts.
        from views.appeal_panel import AppealPanelView
        from views.voting_panel import VotingPanelView
        from views.verdict_panel import VerdictPanelView
        from views.appeal_actions import AppealActionsView

        self.add_view(AppealPanelView(self))
        self.add_view(VotingPanelView(self))
        self.add_view(VerdictPanelView(self))
        self.add_view(AppealActionsView(self))

        # Audit every guild the bot is already in on startup.
        # If the bot was added to an unapproved server while offline, handle it now.
        for guild in self.guilds:
            if not _is_approved(guild):
                logger.warning(
                    "Currently in unapproved guild %s (%s) - handling now",
                    guild.name, guild.id,
                )
                await _handle_unapproved_guild(self, guild)

    async def on_guild_join(self, guild: discord.Guild):
        if _is_approved(guild):
            logger.info("Joined approved guild: %s (%s)", guild.name, guild.id)
            await _alert_developers(self, f"Joined approved server **{guild.name}** (`{guild.id}`).")
            return

        logger.warning("Joined unapproved guild: %s (%s)", guild.name, guild.id)
        await _handle_unapproved_guild(self, guild)


# ---------------------------------------------------------------------------
# Guild guard helpers
# ---------------------------------------------------------------------------

def _is_approved(guild: discord.Guild) -> bool:
    return bool(APPROVED_GUILD_IDS) and guild.id in APPROVED_GUILD_IDS


async def _alert_developers(bot: AppealsBot, message: str) -> None:
    for dev_id in DEVELOPER_IDS:
        try:
            dev = bot.get_user(dev_id) or await bot.fetch_user(dev_id)
            await dev.send(message)
        except discord.HTTPException:
            pass


async def _handle_unapproved_guild(bot: AppealsBot, guild: discord.Guild) -> None:
    """Alert developers with full details then optionally leave the guild."""
    inviter_name, inviter_id = "Unknown", "Unknown"
    try:
        async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.bot_add):
            if entry.target and entry.target.id == bot.user.id:
                inviter_name = str(entry.user)
                inviter_id = str(entry.user.id)
                break
    except discord.Forbidden:
        pass

    invite_url = "Unable to generate invite"
    for channel in guild.text_channels:
        try:
            invite = await channel.create_invite(
                max_age=86400, max_uses=1, reason="Unapproved guild report"
            )
            invite_url = invite.url
            break
        except discord.HTTPException:
            continue

    action_note = "Leaving automatically." if LEAVE_UNAPPROVED_GUILDS else "Auto-leave is disabled - bot will remain."

    embed = discord.Embed(title="Unapproved Server Join", color=0xDC2626, timestamp=discord.utils.utcnow())
    embed.add_field(name="Server", value=f"{guild.name}\n`{guild.id}`", inline=True)
    embed.add_field(name="Members", value=str(guild.member_count), inline=True)
    embed.add_field(name="Added by", value=f"{inviter_name}\n`{inviter_id}`", inline=True)
    embed.add_field(name="Invite (24h)", value=invite_url, inline=False)
    embed.set_footer(text=action_note)

    for dev_id in DEVELOPER_IDS:
        try:
            dev = bot.get_user(dev_id) or await bot.fetch_user(dev_id)
            await dev.send(embed=embed)
        except discord.HTTPException:
            pass

    if LEAVE_UNAPPROVED_GUILDS:
        # Post notice before leaving so the server owner sees why.
        try:
            channel = guild.system_channel or next(
                (ch for ch in guild.text_channels if ch.permissions_for(guild.me).send_messages),
                None,
            )
            if channel:
                await channel.send(UNAUTHORISED_GUILD_MESSAGE)
        except discord.HTTPException:
            pass

        try:
            await guild.leave()
            logger.info("Left unapproved guild %s (%s)", guild.name, guild.id)
        except discord.HTTPException as exc:
            logger.warning("Failed to leave unapproved guild %s (%s): %s", guild.name, guild.id, exc)


def main():
    bot = AppealsBot()
    bot.run(DISCORD_TOKEN, log_handler=None)


if __name__ == "__main__":
    main()
