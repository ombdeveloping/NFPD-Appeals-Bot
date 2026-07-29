import discord
from discord import app_commands
from discord.ext import commands

from constants import COLOUR_PRIMARY


class DashboardCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="setup", description="Configure the appeals bot for this server.")
    @app_commands.describe(
        appeals_channel="Channel where private ticket threads are created",
        voting_channel="Channel where the ban team votes on appeals",
        results_channel="Channel where verdict results are posted",
        ban_team_role="Role to ping when a new appeal is forwarded for voting",
    )
    @app_commands.default_permissions(administrator=True)
    async def setup(
        self,
        interaction: discord.Interaction,
        appeals_channel: discord.TextChannel,
        voting_channel: discord.TextChannel,
        results_channel: discord.TextChannel,
        ban_team_role: discord.Role,
    ):
        await interaction.response.defer(ephemeral=True)
        await self.bot.db.upsert_guild_config(
            interaction.guild_id,
            appeals_channel=appeals_channel.id,
            voting_channel=voting_channel.id,
            results_channel=results_channel.id,
            ban_team_role=ban_team_role.id,
        )

        embed = discord.Embed(
            title="Configuration Saved",
            description="The appeals bot is ready to use. Run `/createdashboard` in your public appeals channel to post the submission panel.",
            color=COLOUR_PRIMARY,
        )
        embed.add_field(name="Appeals Channel", value=appeals_channel.mention, inline=True)
        embed.add_field(name="Voting Channel", value=voting_channel.mention, inline=True)
        embed.add_field(name="Results Channel", value=results_channel.mention, inline=True)
        embed.add_field(name="Ban Team Role", value=ban_team_role.mention, inline=True)
        embed.set_footer(text="NFPD Appeals System")
        embed.timestamp = discord.utils.utcnow()

        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(
        name="createdashboard",
        description="Post the ban appeal dashboard panel in this channel.",
    )
    @app_commands.default_permissions(administrator=True)
    async def create_dashboard(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        config = await self.bot.db.get_guild_config(interaction.guild_id)
        if not config or not config["appeals_channel"]:
            await interaction.followup.send(
                "Please run `/setup` first to configure the appeals bot.",
                ephemeral=True,
            )
            return

        if config["dashboard_msg_id"]:
            try:
                old_msg = await interaction.channel.fetch_message(config["dashboard_msg_id"])
                await old_msg.delete()
            except (discord.NotFound, discord.HTTPException):
                pass

        from views.appeal_panel import AppealPanelView
        msg = await interaction.channel.send(
            embed=_build_dashboard_embed(),
            view=AppealPanelView(self.bot),
        )

        await self.bot.db.upsert_guild_config(interaction.guild_id, dashboard_msg_id=msg.id)
        await interaction.followup.send("Dashboard posted.", ephemeral=True)


def _build_dashboard_embed() -> discord.Embed:
    embed = discord.Embed(
        title="Ban Appeals",
        description=(
            "If you believe your ban was issued in error, or you have reflected on your conduct "
            "and wish to request reconsideration, you may submit a formal appeal below.\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "**Before you submit, read this carefully:**\n\n"
            "> Appeals are reviewed by the NFPD Ban Team.\n"
            "> You may only hold **one open appeal** at a time.\n"
            "> The review process takes up to **48 hours** after submission.\n"
            "> Dishonest or frivolous appeals may result in a permanent ban.\n"
            "> Be clear, honest, and respectful.\n"
            "━━━━━━━━━━━━━━━━━━━━━━"
        ),
        color=COLOUR_PRIMARY,
    )
    embed.set_author(name="NFPD  |  National Force Police Department")
    embed.set_footer(text="Tap the button below to begin  •  NFPD Ban Appeals")
    return embed
