import discord
from discord import app_commands
from discord.ext import commands


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
        await interaction.followup.send(
            f"Configuration saved.\n"
            f"- Appeals channel: {appeals_channel.mention}\n"
            f"- Voting channel: {voting_channel.mention}\n"
            f"- Results channel: {results_channel.mention}\n"
            f"- Ban team role: {ban_team_role.mention}\n\n"
            f"Run `/createdashboard` in the channel you want the appeal panel to appear.",
            ephemeral=True,
        )

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

        # Delete the old dashboard message if one exists
        if config["dashboard_msg_id"]:
            try:
                old_msg = await interaction.channel.fetch_message(config["dashboard_msg_id"])
                await old_msg.delete()
            except (discord.NotFound, discord.HTTPException):
                pass

        embed = _build_dashboard_embed()
        from views.appeal_panel import AppealPanelView
        msg = await interaction.channel.send(embed=embed, view=AppealPanelView(self.bot))

        await self.bot.db.upsert_guild_config(
            interaction.guild_id, dashboard_msg_id=msg.id
        )

        await interaction.followup.send(
            "Dashboard posted successfully.", ephemeral=True
        )


def _build_dashboard_embed() -> discord.Embed:
    embed = discord.Embed(
        title="NFPD Ban Appeals",
        description=(
            "If you believe your ban was issued in error or you have reflected on your actions "
            "and wish to request reconsideration, you may submit a ban appeal below.\n\n"
            "**Before submitting, please note:**\n"
            "- Appeals are reviewed by the NFPD Ban Team and may take up to **48 hours**.\n"
            "- You may only have **one open appeal** at a time.\n"
            "- Submitting a false or misleading appeal may result in a permanent ban.\n"
            "- Be honest, clear, and respectful in your appeal."
        ),
        color=0x1F2937,
    )
    embed.set_author(
        name="NFPD | National Force Police Department",
    )
    embed.set_footer(text="Tap the button below to begin your appeal.")
    return embed
