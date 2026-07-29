import discord
from discord import app_commands
from discord.ext import commands


class AppealsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="forwardtobanteam",
        description="Manually forward the current ticket's appeal to the ban team for voting.",
    )
    @app_commands.default_permissions(manage_guild=True)
    async def forward_to_ban_team(self, interaction: discord.Interaction):
        """
        Alternative to clicking the button in the ticket - useful if the button
        message was deleted or the view failed to load.
        """
        await interaction.response.defer(ephemeral=True)
        db = self.bot.db

        # Identify the appeal from the channel topic
        channel = interaction.channel
        if not channel.topic or "Appeal ID:" not in channel.topic:
            await interaction.followup.send(
                "This channel does not appear to be an appeal ticket. "
                "The channel topic must contain 'Appeal ID: <number>'.",
                ephemeral=True,
            )
            return

        try:
            appeal_id = int(channel.topic.split("Appeal ID:")[1].strip())
        except (ValueError, IndexError):
            await interaction.followup.send(
                "Could not parse the appeal ID from this channel's topic.",
                ephemeral=True,
            )
            return

        appeal = await db.get_appeal(appeal_id)
        if not appeal:
            await interaction.followup.send("No appeal found with that ID.", ephemeral=True)
            return

        if appeal["status"] != "open":
            await interaction.followup.send(
                f"This appeal is currently **{appeal['status']}** and cannot be forwarded.",
                ephemeral=True,
            )
            return

        config = await db.get_guild_config(interaction.guild_id)
        if not config or not config["voting_channel"]:
            await interaction.followup.send(
                "No voting channel configured. Run `/setup` first.", ephemeral=True
            )
            return

        voting_channel = interaction.guild.get_channel(config["voting_channel"])
        if not voting_channel:
            await interaction.followup.send(
                "Cannot find the configured voting channel.", ephemeral=True
            )
            return

        from datetime import datetime, timezone, timedelta
        closes_at = datetime.now(timezone.utc) + timedelta(hours=48)

        ban_team_mention = f"<@&{config['ban_team_role']}>" if config["ban_team_role"] else ""

        from views.appeal_actions import _build_voting_embed
        embed = _build_voting_embed(appeal, closes_at)

        from views.voting_panel import VotingPanelView
        voting_msg = await voting_channel.send(
            content=ban_team_mention or None,
            embed=embed,
            view=VotingPanelView(self.bot, appeal_id),
        )

        await db.set_appeal_voting(appeal_id, voting_msg.id, closes_at)

        await interaction.followup.send(
            f"Appeal forwarded to {voting_channel.mention}. "
            f"Voting closes <t:{int(closes_at.timestamp())}:R>.",
            ephemeral=True,
        )

    @app_commands.command(
        name="appealinfo",
        description="Show the current status and details of an appeal by ID.",
    )
    @app_commands.describe(appeal_id="The numeric appeal ID")
    @app_commands.default_permissions(manage_guild=True)
    async def appeal_info(self, interaction: discord.Interaction, appeal_id: int):
        await interaction.response.defer(ephemeral=True)
        appeal = await self.bot.db.get_appeal(appeal_id)
        if not appeal or appeal["guild_id"] != interaction.guild_id:
            await interaction.followup.send("No appeal found with that ID.", ephemeral=True)
            return

        tally = await self.bot.db.get_vote_tally(appeal_id)

        embed = discord.Embed(
            title=f"Appeal #{appeal_id}",
            color=_status_color(appeal["status"]),
        )
        embed.add_field(name="Status", value=appeal["status"].replace("_", " ").title(), inline=True)
        embed.add_field(name="Roblox Username", value=appeal["roblox_username"], inline=True)
        embed.add_field(name="Discord", value=appeal["discord_tag"], inline=True)
        embed.add_field(name="Reason for Ban", value=appeal["ban_reason"], inline=False)
        embed.add_field(name="Appeal Statement", value=appeal["appeal_reason"], inline=False)
        embed.add_field(
            name="Votes",
            value=f"Unban: {tally['unban']} | Keep Banned: {tally['keep_banned']}",
            inline=False,
        )
        if appeal["closes_at"]:
            embed.add_field(
                name="Voting Closes",
                value=f"<t:{int(appeal['closes_at'].timestamp())}:R>",
                inline=False,
            )
        embed.set_footer(text=f"Submitted by user ID {appeal['appellant_id']}")
        embed.timestamp = appeal["created_at"]

        await interaction.followup.send(embed=embed, ephemeral=True)


def _status_color(status: str) -> int:
    return {
        "open": 0x3498DB,
        "voting": 0xFFA500,
        "accepted": 0x2ECC71,
        "rejected": 0xE74C3C,
        "closed": 0x95A5A6,
    }.get(status, 0x2C2F33)
