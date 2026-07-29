import logging
import os

import discord
from discord.ext import commands

from constants import APPROVED_GUILD_IDS, DEVELOPER_ID, UNAUTHORISED_GUILD_MESSAGE
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
        self.db = Database(os.environ["DATABASE_URL"])
        await self.db.initialise()

        await self.add_cog(DashboardCog(self))
        await self.add_cog(AppealsCog(self))
        await self.add_cog(VotingCog(self))

        await self.tree.sync()
        logger.info("Slash commands synced.")

    async def on_ready(self):
        logger.info(f"Logged in as {self.user} (ID: {self.user.id})")

        from views.appeal_panel import AppealPanelView
        from views.voting_panel import VotingPanelView
        from views.verdict_panel import VerdictPanelView

        self.add_view(AppealPanelView(self))
        self.add_view(VotingPanelView(self))
        self.add_view(VerdictPanelView(self))

    async def on_guild_join(self, guild: discord.Guild):
        if guild.id in APPROVED_GUILD_IDS:
            logger.info(f"Joined approved guild: {guild.name} ({guild.id})")
            return

        logger.warning(f"Joined unapproved guild: {guild.name} ({guild.id}) - notifying developer and leaving.")

        # Find who added the bot by checking the audit log.
        inviter_name = "Unknown"
        inviter_id = "Unknown"
        try:
            async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.bot_add):
                if entry.target and entry.target.id == self.user.id:
                    inviter_name = str(entry.user)
                    inviter_id = entry.user.id
                    break
        except discord.Forbidden:
            pass

        # Generate a temporary invite so the developer can inspect the server.
        invite_url = "Unable to generate invite"
        try:
            # Use the first text channel we can create an invite in.
            for channel in guild.text_channels:
                try:
                    invite = await channel.create_invite(max_age=86400, max_uses=1, reason="Unapproved guild report")
                    invite_url = invite.url
                    break
                except discord.Forbidden:
                    continue
        except Exception:
            pass

        # DM the developer.
        try:
            developer = await self.fetch_user(DEVELOPER_ID)
            embed = discord.Embed(
                title="Unapproved Server Join",
                color=0xDC2626,
            )
            embed.add_field(name="Server Name", value=guild.name, inline=True)
            embed.add_field(name="Server ID", value=str(guild.id), inline=True)
            embed.add_field(name="Member Count", value=str(guild.member_count), inline=True)
            embed.add_field(name="Added By", value=inviter_name, inline=True)
            embed.add_field(name="Adder ID", value=str(inviter_id), inline=True)
            embed.add_field(name="Invite (24h)", value=invite_url, inline=False)
            embed.set_footer(text="The bot has left this server.")
            embed.timestamp = discord.utils.utcnow()
            await developer.send(embed=embed)
        except discord.HTTPException as exc:
            logger.error(f"Failed to DM developer about unapproved guild {guild.id}: {exc}")

        # Warn the server, then leave.
        try:
            system_channel = guild.system_channel or next(
                (ch for ch in guild.text_channels if ch.permissions_for(guild.me).send_messages),
                None,
            )
            if system_channel:
                await system_channel.send(UNAUTHORISED_GUILD_MESSAGE)
        except discord.HTTPException:
            pass

        await guild.leave()


def main():
    token = os.environ.get("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_TOKEN environment variable is not set.")

    bot = AppealsBot()
    bot.run(token, log_handler=None)


if __name__ == "__main__":
    main()
