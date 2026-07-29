import logging

import discord
from discord.ext import commands, tasks

logger = logging.getLogger("appeals-bot.voting")

MINIMUM_VOTES = 3


class VotingCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.check_expired_votes.start()

    def cog_unload(self):
        self.check_expired_votes.cancel()

    @tasks.loop(minutes=5)
    async def check_expired_votes(self):
        try:
            await self._process_expired_appeals()
        except Exception:
            logger.exception("Error in check_expired_votes loop")

    @check_expired_votes.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()

    async def _process_expired_appeals(self):
        db = self.bot.db
        expired_appeals = await db.get_appeals_due_for_verdict()

        for appeal in expired_appeals:
            try:
                await self._finalise_appeal(appeal)
            except Exception:
                logger.exception(f"Failed to finalise appeal {appeal['id']}")

    async def _finalise_appeal(self, appeal):
        db = self.bot.db
        appeal_id = appeal["id"]

        tally = await db.get_vote_tally(appeal_id)
        total_votes = tally["unban"] + tally["keep_banned"]

        config = await db.get_guild_config(appeal["guild_id"])
        if not config:
            logger.warning(f"No config for guild {appeal['guild_id']}, skipping appeal {appeal_id}")
            return

        guild = self.bot.get_guild(appeal["guild_id"])
        if not guild:
            return

        results_channel = guild.get_channel(config["results_channel"]) if config["results_channel"] else None
        ticket_channel = guild.get_channel(appeal["ticket_channel"]) if appeal["ticket_channel"] else None

        if total_votes < MINIMUM_VOTES:
            embed = _build_inconclusive_embed(appeal, tally, total_votes)
            if results_channel:
                await results_channel.send(embed=embed)
            if ticket_channel:
                await ticket_channel.send(embed=embed)
            await db.close_appeal(appeal_id, "closed")
            return

        unban_wins = tally["unban"] > tally["keep_banned"]
        verdict = "accepted" if unban_wins else "rejected"

        embed = _build_verdict_embed(appeal, tally, total_votes, unban_wins)

        from views.verdict_panel import VerdictPanelView
        view = VerdictPanelView(self.bot, appeal_id)

        if results_channel:
            ban_team_mention = f"<@&{config['ban_team_role']}>" if config["ban_team_role"] else ""
            await results_channel.send(
                content=ban_team_mention or None,
                embed=embed,
                view=view,
            )
        if ticket_channel:
            await ticket_channel.send(embed=embed, view=VerdictPanelView(self.bot, appeal_id))

        # Lock the voting message so buttons are disabled
        await _disable_voting_message(guild, config, appeal)

        # Status is set to the verdict but the ticket stays open until staff action
        await db.close_appeal(appeal_id, verdict)


def _build_verdict_embed(appeal, tally: dict, total_votes: int, unban_wins: bool) -> discord.Embed:
    color = 0x2ECC71 if unban_wins else 0xE74C3C
    outcome = "UNBAN APPROVED" if unban_wins else "KEEP BANNED"

    embed = discord.Embed(
        title=f"Appeal #{appeal['id']} - Voting Closed",
        description=f"**Outcome: {outcome}**",
        color=color,
    )
    embed.set_author(name="NFPD Ban Appeals - Verdict")
    embed.add_field(name="Roblox Username", value=appeal["roblox_username"], inline=True)
    embed.add_field(name="Discord", value=appeal["discord_tag"], inline=True)
    embed.add_field(name="\u200b", value="\u200b", inline=True)
    embed.add_field(name="Unban Votes", value=str(tally["unban"]), inline=True)
    embed.add_field(name="Keep Banned Votes", value=str(tally["keep_banned"]), inline=True)
    embed.add_field(name="Total Votes", value=str(total_votes), inline=True)

    if unban_wins:
        embed.add_field(
            name="Next Step",
            value="Press **Execute Unban** to remove the ban, or **Close Ticket** to dismiss.",
            inline=False,
        )
    else:
        embed.add_field(
            name="Next Step",
            value="Press **Close Ticket** to close this appeal.",
            inline=False,
        )

    embed.set_footer(text=f"Appeal ID: {appeal['id']} | Voting closed")
    embed.timestamp = discord.utils.utcnow()
    return embed


def _build_inconclusive_embed(appeal, tally: dict, total_votes: int) -> discord.Embed:
    embed = discord.Embed(
        title=f"Appeal #{appeal['id']} - Inconclusive",
        description=(
            f"This appeal did not receive the minimum **{MINIMUM_VOTES} votes** required for a valid result.\n"
            f"Only **{total_votes}** vote(s) were cast. The appeal has been closed without a verdict."
        ),
        color=0x95A5A6,
    )
    embed.set_author(name="NFPD Ban Appeals - Inconclusive")
    embed.add_field(name="Roblox Username", value=appeal["roblox_username"], inline=True)
    embed.add_field(name="Discord", value=appeal["discord_tag"], inline=True)
    embed.add_field(name="Unban Votes", value=str(tally["unban"]), inline=True)
    embed.add_field(name="Keep Banned Votes", value=str(tally["keep_banned"]), inline=True)
    embed.set_footer(text=f"Appeal ID: {appeal['id']}")
    embed.timestamp = discord.utils.utcnow()
    return embed


async def _disable_voting_message(guild: discord.Guild, config, appeal):
    """Edit the voting message to remove the vote buttons after a verdict."""
    if not config["voting_channel"] or not appeal["voting_msg_id"]:
        return
    voting_channel = guild.get_channel(config["voting_channel"])
    if not voting_channel:
        return
    try:
        msg = await voting_channel.fetch_message(appeal["voting_msg_id"])
        embed = msg.embeds[0]

        # Update embed color to grey to signal closed
        new_embed = embed.copy()
        new_embed.color = discord.Color.greys()[0] if hasattr(discord.Color, "greys") else discord.Color(0x95A5A6)

        await msg.edit(embed=new_embed, view=None)
    except (discord.NotFound, discord.HTTPException):
        pass
