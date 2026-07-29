import logging
import os

import discord
import config as _config
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
from cogs.debug import DebugCog
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
        # Wrap database setup so a connection failure gives a readable error
        # rather than a traceback that looks like the bot crashed for no reason.
        try:
            self.db = Database(DATABASE_URL)
            await self.db.initialise()
            logger.info("Database connected.")
        except Exception as exc:
            logger.error(
                "Database connection failed: %s\n"
                "Check DATABASE_URL in Railway's Variables tab. "
                "Make sure a PostgreSQL plugin is attached to this service.",
                exc,
            )
            raise

        await self.add_cog(DashboardCog(self))
        await self.add_cog(AppealsCog(self))
        await self.add_cog(VotingCog(self))
        await self.add_cog(DebugCog(self))

        try:
            synced = await self.tree.sync()
            logger.info("Synced %d slash command(s).", len(synced))
        except Exception as exc:
            logger.error("Slash command sync failed: %s", exc)

    async def on_ready(self):
        logger.info("Logged in as %s (%s)", self.user, self.user.id)
        _config.BOT_AVATAR_URL = self.user.display_avatar.url
        logger.info("In %d guild(s).", len(self.guilds))

        # Warn loudly if the allowlist is empty - this is the #1 reason the bot
        # appears offline (it joins then immediately leaves every server).
        if not APPROVED_GUILD_IDS:
            logger.error(
                "\n"
                "  *** APPROVED_GUILD_IDS IS EMPTY - BOT WILL LEAVE EVERY SERVER ***\n"
                "  Go to Railway -> your service -> Variables and add:\n"
                "  APPROVED_GUILD_IDS=<your server ID>\n"
                "  Right-click your server icon in Discord -> Copy Server ID\n"
            )

        # Register persistent views so buttons on old messages survive restarts.
        from views.appeal_panel import AppealPanelView
        from views.voting_panel import VotingPanelView
        from views.verdict_panel import VerdictPanelView
        from views.appeal_actions import AppealActionsView

        self.add_view(AppealPanelView(self))
        self.add_view(VotingPanelView(self))
        self.add_view(VerdictPanelView(self))
        self.add_view(AppealActionsView(self))

        # Audit current guilds. If the bot was added to an unapproved server
        # while offline, handle it now rather than silently sitting there.
        for guild in self.guilds:
            if _is_approved(guild):
                logger.info("Approved guild: %s (%s)", guild.name, guild.id)
            else:
                logger.warning("Unapproved guild on startup: %s (%s)", guild.name, guild.id)
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
    # An empty allowlist means nothing is approved - bot leaves everything.
    return bool(APPROVED_GUILD_IDS) and guild.id in APPROVED_GUILD_IDS


async def _alert_developers(bot: AppealsBot, message: str) -> None:
    for dev_id in DEVELOPER_IDS:
        try:
            dev = bot.get_user(dev_id) or await bot.fetch_user(dev_id)
            await dev.send(message)
        except discord.HTTPException:
            pass


async def _handle_unapproved_guild(bot: AppealsBot, guild: discord.Guild) -> None:
    """DM developers with full details then optionally leave."""
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

    action_note = (
        "Leaving automatically."
        if LEAVE_UNAPPROVED_GUILDS
        else "LEAVE_UNAPPROVED_GUILDS=false - bot is staying but is not approved."
    )

    embed = discord.Embed(
        title="Unapproved Server Join",
        color=0xDC2626,
        timestamp=discord.utils.utcnow(),
    )
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
            logger.warning("Could not leave %s (%s): %s", guild.name, guild.id, exc)


def main():
    bot = AppealsBot()
    bot.run(DISCORD_TOKEN, log_handler=None)


if __name__ == "__main__":
    main()
