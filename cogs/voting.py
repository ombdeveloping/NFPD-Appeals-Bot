import logging

import discord
from discord.ext import commands, tasks

from config import (
    BOT_AVATAR_URL,
    MINIMUM_VOTES,
    VOTING_HOURS,
    COLOUR_ACCEPTED,
    COLOUR_REJECTED,
    COLOUR_CLOSED,
    COLOUR_VOTING,
    COLOUR_PRIMARY,
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
            await _dm_appellant(self.bot, appeal, verdict="inconclusive")
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
        await _dm_appellant(self.bot, appeal, verdict=verdict)


async def _dm_appellant(bot, appeal, *, verdict: str) -> None:
    """DM the appellant with the outcome of their appeal."""
    try:
        user = await bot.fetch_user(appeal["appellant_id"])
    except discord.HTTPException:
        return

    if verdict == "accepted":
        embed = discord.Embed(
            title="Ban Appeal - Accepted",
            description=(
                "Your ban appeal has been reviewed by the NFPD Ban Team.\n\n"
                "**The vote was in your favour.** A staff member will action your unban shortly.\n\n"
                "You will regain access to North Florida City Police Department once the unban has been executed."
            ),
            color=COLOUR_ACCEPTED,
        )
        embed.set_footer(text=f"Appeal #{appeal['id']}  |  NFPD Ban Appeals")

    elif verdict == "rejected":
        embed = discord.Embed(
            title="Ban Appeal - Rejected",
            description=(
                "Your ban appeal has been reviewed by the NFPD Ban Team.\n\n"
                "**The vote did not go in your favour.** Your ban will remain in place.\n\n"
                "If you believe this outcome is incorrect, you may contact a senior staff member. "
                "Please be respectful in any further communication."
            ),
            color=COLOUR_REJECTED,
        )
        embed.set_footer(text=f"Appeal #{appeal['id']}  |  NFPD Ban Appeals")

    else:  # inconclusive
        embed = discord.Embed(
            title="Ban Appeal - Inconclusive",
            description=(
                "Your ban appeal did not receive enough votes within the 48-hour window to reach a valid result.\n\n"
                f"A minimum of **{MINIMUM_VOTES} votes** is required. Your appeal has been closed without a verdict.\n\n"
                "Staff may reopen your appeal manually. If you have questions, please contact a staff member."
            ),
            color=COLOUR_CLOSED,
        )
        embed.set_footer(text=f"Appeal #{appeal['id']}  |  NFPD Ban Appeals")

    embed.add_field(name="Roblox Username", value=f"`{appeal['roblox_username']}`", inline=True)
    embed.add_field(name="Appeal ID", value=str(appeal["id"]), inline=True)
    embed.timestamp = discord.utils.utcnow()

    try:
        await user.send(embed=embed)
    except discord.HTTPException:
        # DMs closed or blocked - not a fatal error
        logger.debug(f"Could not DM appellant {appeal['appellant_id']} for appeal {appeal['id']}")


def _build_verdict_embed(appeal, tally: dict, total_votes: int, unban_wins: bool) -> discord.Embed:
    from views.voting_panel import _build_vote_bar
    colour = COLOUR_ACCEPTED if unban_wins else COLOUR_REJECTED
    outcome = "UNBAN APPROVED" if unban_wins else "KEEP BANNED"
    icon = "🟢" if unban_wins else "🔴"
    bar = _build_vote_bar(tally["unban"], tally["keep_banned"])
    action = (
        "Use **Execute Unban** to lift the ban, or **Close Ticket** to dismiss."
        if unban_wins
        else "Use **Close Ticket** to formally close this appeal."
    )

    embed = discord.Embed(
        title=f"{icon}  Voting Closed  —  {outcome}",
        description=(
            f"The voting window for Appeal #{appeal['id']} has closed.\n\n"
            f"{action}"
        ),
        color=colour,
    )
    embed.set_author(name="North Florida Police Department  |  Verdict", icon_url=BOT_AVATAR_URL)
    embed.add_field(name="Roblox Username", value=f"`{appeal['roblox_username']}`", inline=True)
    embed.add_field(name="Discord", value=appeal["discord_tag"], inline=True)
    embed.add_field(name="Appellant", value=f"<@{appeal['appellant_id']}>", inline=True)
    embed.add_field(
        name=f"📊 Final Vote  ({total_votes} cast)",
        value=(
            f"🟢 {bar} 🔴\n"
            f"**{tally['unban']}** unban  •  **{tally['keep_banned']}** keep banned"
        ),
        inline=False,
    )
    embed.set_footer(text=f"Appeal ID: {appeal['id']}  •  Voting closed")
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
    embed.set_author(
        name="North Florida Police Department  |  Inconclusive",
        icon_url=BOT_AVATAR_URL,
    )
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
