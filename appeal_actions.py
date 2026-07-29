import discord
from datetime import datetime, timezone, timedelta


class AppealActionsView(discord.ui.View):
    """
    Shown inside the private ticket channel.
    Only visible to staff - forwards the appeal to the voting channel.
    """

    def __init__(self, bot, appeal_id: int):
        super().__init__(timeout=None)
        self.bot = bot
        self.appeal_id = appeal_id

    @discord.ui.button(
        label="Forward to Ban Team",
        style=discord.ButtonStyle.success,
        custom_id="appeals:forward",
        emoji="📨",
    )
    async def forward_to_ban_team(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True, thinking=True)

        db = self.bot.db
        config = await db.get_guild_config(interaction.guild_id)

        if not config or not config["voting_channel"]:
            await interaction.followup.send(
                "No voting channel is configured. Run `/setup` first.",
                ephemeral=True,
            )
            return

        appeal = await db.get_appeal(self.appeal_id)
        if not appeal:
            await interaction.followup.send("Could not find this appeal.", ephemeral=True)
            return

        if appeal["status"] != "open":
            await interaction.followup.send(
                "This appeal has already been forwarded or closed.", ephemeral=True
            )
            return

        voting_channel = interaction.guild.get_channel(config["voting_channel"])
        if not voting_channel:
            await interaction.followup.send(
                "Cannot find the voting channel. Please contact an admin.", ephemeral=True
            )
            return

        closes_at = datetime.now(timezone.utc) + timedelta(hours=48)

        ban_team_mention = ""
        if config["ban_team_role"]:
            ban_team_mention = f"<@&{config['ban_team_role']}>"

        embed = _build_voting_embed(appeal, closes_at)

        from views.voting_panel import VotingPanelView
        voting_msg = await voting_channel.send(
            content=ban_team_mention or None,
            embed=embed,
            view=VotingPanelView(self.bot, self.appeal_id),
        )

        await db.set_appeal_voting(self.appeal_id, voting_msg.id, closes_at)

        # Disable the forward button so it can't be pressed twice
        button.disabled = True
        button.label = "Forwarded to Ban Team"
        await interaction.message.edit(view=self)

        await interaction.followup.send(
            f"Appeal forwarded to {voting_channel.mention}. Voting closes <t:{int(closes_at.timestamp())}:R>.",
            ephemeral=True,
        )

    @discord.ui.button(
        label="Close Ticket",
        style=discord.ButtonStyle.danger,
        custom_id="appeals:close_ticket",
        emoji="🔒",
    )
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        db = self.bot.db
        appeal = await db.get_appeal(self.appeal_id)

        if appeal and appeal["status"] == "open":
            await db.close_appeal(self.appeal_id, "closed")

        await interaction.followup.send("Closing ticket in 5 seconds...", ephemeral=True)

        import asyncio
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete(reason=f"Appeal {self.appeal_id} closed by {interaction.user}")
        except discord.HTTPException:
            pass


def _build_voting_embed(appeal, closes_at: datetime) -> discord.Embed:
    embed = discord.Embed(
        title="Ban Appeal - Team Review",
        description=(
            "Review the appeal below and cast your vote. "
            "A minimum of **3 votes** is required for a valid result."
        ),
        color=0xFFA500,
    )
    embed.set_author(name="NFPD Ban Appeals")
    embed.add_field(name="Roblox Username", value=appeal["roblox_username"], inline=True)
    embed.add_field(name="Discord", value=appeal["discord_tag"], inline=True)
    embed.add_field(name="\u200b", value="\u200b", inline=True)
    embed.add_field(name="Reason for Ban", value=appeal["ban_reason"], inline=False)
    embed.add_field(name="Appeal Statement", value=appeal["appeal_reason"], inline=False)
    embed.add_field(
        name="Voting Closes",
        value=f"<t:{int(closes_at.timestamp())}:F> (<t:{int(closes_at.timestamp())}:R>)",
        inline=False,
    )
    embed.add_field(name="Unban", value="0 votes", inline=True)
    embed.add_field(name="Keep Banned", value="0 votes", inline=True)
    embed.set_footer(text=f"Appeal ID: {appeal['id']} - Minimum 3 votes required")
    embed.timestamp = discord.utils.utcnow()
    return embed
