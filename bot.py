import asyncio
import logging
import os

import discord
from discord.ext import commands

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

        # Re-attach persistent views so buttons survive restarts
        from views.appeal_panel import AppealPanelView
        from views.voting_panel import VotingPanelView
        from views.verdict_panel import VerdictPanelView

        self.add_view(AppealPanelView(self))
        self.add_view(VotingPanelView(self))
        self.add_view(VerdictPanelView(self))


def main():
    token = os.environ.get("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_TOKEN environment variable is not set.")

    bot = AppealsBot()
    bot.run(token, log_handler=None)


if __name__ == "__main__":
    main()
