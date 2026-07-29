import logging

import discord
from discord.ext import commands, tasks

from constants import (
    MINIMUM_VOTES,
    COLOUR_ACCEPTED,
    COLOUR_REJECTED,
    COLOUR_CLOSED,
    COLOUR_VOTING,
)

logger = logging.getLogger("appeals-bot.voting")


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
        expired = await self.bot.db.get_appeals_due_for_verdict()
        for appeal in expired:
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

        await _disable_voting_message(guild, config, appeal)

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

        ban_team_mention = f"<@&{config['ban_team_role']}>" if config["ban_team_role"] else None

        if results_channel:
            await results_channel.send(
                content=ban_team_mention,
                embed=embed,
                view=VerdictPanelView(self.bot, appeal_id),
            )
        if ticket_channel:
            await ticket_channel.send(
                embed=embed,
                view=VerdictPanelView(self.bot, appeal_id),
            )

        await db.close_appeal(appeal_id, verdict)


def _build_verdict_embed(appeal, tally: dict, total_votes: int, unban_wins: bool) -> discord.Embed:
    colour = COLOUR_ACCEPTED if unban_wins else COLOUR_REJECTED
    outcome_text = "UNBAN APPROVED" if unban_wins else "KEEP BANNED"
    outcome_icon = "🟢" if unban_wins else "🔴"
    next_step = (
        "Use **Execute Unban** to lift the ban, or **Close Ticket** to dismiss without action."
        if unban_wins
        else "Use **Close Ticket** to formally close this appeal."
    )

    from cogs.appeals import _build_vote_bar
    vote_bar = _build_vote_bar(tally["unban"], tally["keep_banned"])

    embed = discord.Embed(
        title=f"{outcome_icon}  Voting Closed  -  {outcome_text}",
        description=(
            f"The 48-hour voting window for Appeal #{appeal['id']} has ended.\n\n"
            f"{next_step}"
        ),
        color=colour,
    )
    embed.set_author(name="NFPD Ban Appeals  |  Verdict")
    embed.add_field(name="Roblox Username", value=f"`{appeal['roblox_username']}`", inline=True)
    embed.add_field(name="Discord", value=appeal["discord_tag"], inline=True)
    embed.add_field(name="Appellant", value=f"<@{appeal['appellant_id']}>", inline=True)

    embed.add_field(
        name=f"Final Vote  ({total_votes} cast)",
        value=(
            f"{vote_bar}\n"
            f"Unban: **{tally['unban']}**  |  Keep Banned: **{tally['keep_banned']}**"
        ),
        inline=False,
    )

    embed.set_footer(text=f"Appeal ID: {appeal['id']}  |  Voting closed")
    embed.timestamp = discord.utils.utcnow()
    return embed


def _build_inconclusive_embed(appeal, tally: dict, total_votes: int) -> discord.Embed:
    embed = discord.Embed(
        title="⚫  Voting Closed  -  INCONCLUSIVE",
        description=(
            f"Appeal #{appeal['id']} did not reach the minimum **{MINIMUM_VOTES} votes** required for a valid result.\n\n"
            f"Only **{total_votes}** vote(s) were cast within the 48-hour window. "
            "This appeal has been closed without a verdict. Staff may reopen it manually if required."
        ),
        color=COLOUR_CLOSED,
    )
    embed.set_author(name="NFPD Ban Appeals  |  Inconclusive")
    embed.add_field(name="Roblox Username", value=f"`{appeal['roblox_username']}`", inline=True)
    embed.add_field(name="Discord", value=appeal["discord_tag"], inline=True)
    embed.add_field(name="Unban Votes", value=str(tally["unban"]), inline=True)
    embed.add_field(name="Keep Banned Votes", value=str(tally["keep_banned"]), inline=True)
    embed.set_footer(text=f"Appeal ID: {appeal['id']}")
    embed.timestamp = discord.utils.utcnow()
    return embed


async def _disable_voting_message(guild: discord.Guild, config, appeal):
    if not config["voting_channel"] or not appeal["voting_msg_id"]:
        return
    voting_channel = guild.get_channel(config["voting_channel"])
    if not voting_channel:
        return
    try:
        msg = await voting_channel.fetch_message(appeal["voting_msg_id"])
        embed = msg.embeds[0]
        embed.color = discord.Color(COLOUR_CLOSED)
        await msg.edit(embed=embed, view=None)
    except (discord.NotFound, discord.HTTPException):
        pass
