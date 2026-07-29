import discord

from constants import COLOUR_INFO, COLOUR_PRIMARY


class AppealModal(discord.ui.Modal, title="NFPD Ban Appeal"):
    roblox_username = discord.ui.TextInput(
        label="Roblox Username",
        placeholder="Your exact Roblox username",
        min_length=3,
        max_length=20,
    )
    discord_tag = discord.ui.TextInput(
        label="Discord Username",
        placeholder="e.g. username or username#0000",
        min_length=2,
        max_length=37,
    )
    ban_reason = discord.ui.TextInput(
        label="Reason You Were Banned",
        placeholder="What reason were you given for your ban?",
        style=discord.TextStyle.paragraph,
        max_length=500,
    )
    appeal_reason = discord.ui.TextInput(
        label="Why Should You Be Unbanned?",
        placeholder="Explain your case clearly and honestly. Be specific.",
        style=discord.TextStyle.paragraph,
        max_length=1000,
    )

    def __init__(self, bot):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)

        db = self.bot.db
        guild_id = interaction.guild_id
        user_id = interaction.user.id

        existing = await db.get_open_appeal_for_user(guild_id, user_id)
        if existing:
            await interaction.followup.send(
                "You already have an open appeal. Please wait for it to be resolved before submitting another.",
                ephemeral=True,
            )
            return

        config = await db.get_guild_config(guild_id)
        if not config or not config["appeals_channel"]:
            await interaction.followup.send(
                "Appeals are not configured on this server. Please contact an administrator.",
                ephemeral=True,
            )
            return

        roblox_username = self.roblox_username.value.strip()
        discord_tag = self.discord_tag.value.strip()
        ban_reason = self.ban_reason.value.strip()
        appeal_reason = self.appeal_reason.value.strip()

        appeal_id = await db.create_appeal(
            guild_id=guild_id,
            appellant_id=user_id,
            roblox_username=roblox_username,
            discord_tag=discord_tag,
            ban_reason=ban_reason,
            appeal_reason=appeal_reason,
        )

        appeals_channel = interaction.guild.get_channel(config["appeals_channel"])
        if not appeals_channel:
            await interaction.followup.send(
                "Could not find the appeals channel. Please contact an administrator.",
                ephemeral=True,
            )
            return

        ticket_channel = await interaction.guild.create_text_channel(
            name=f"appeal-{interaction.user.name}",
            category=appeals_channel.category,
            topic=f"Ban appeal submitted by {interaction.user} | Appeal ID: {appeal_id}",
            overwrites={
                interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
                interaction.user: discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                ),
                interaction.guild.me: discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    manage_channels=True,
                    manage_messages=True,
                ),
            },
        )

        await db.set_appeal_ticket_channel(appeal_id, ticket_channel.id)

        # Opening notice inside the ticket visible to the appellant.
        notice_embed = discord.Embed(
            title="Appeal Received",
            description=(
                "Your appeal has been submitted and is awaiting review by the NFPD Ban Team.\n\n"
                "A staff member will forward it to the team shortly. "
                "You will be notified in this channel when a verdict is reached.\n\n"
                "**Do not submit duplicate appeals.** Please be patient."
            ),
            color=COLOUR_INFO,
        )
        notice_embed.set_footer(text=f"Appeal ID: {appeal_id}  |  NFPD Ban Appeals")
        notice_embed.timestamp = discord.utils.utcnow()

        # Full case embed visible to staff.
        case_embed = _build_appeal_embed(
            appeal_id=appeal_id,
            appellant=interaction.user,
            roblox_username=roblox_username,
            discord_tag=discord_tag,
            ban_reason=ban_reason,
            appeal_reason=appeal_reason,
        )

        from views.appeal_actions import AppealActionsView
        await ticket_channel.send(
            content=interaction.user.mention,
            embeds=[notice_embed, case_embed],
            view=AppealActionsView(self.bot, appeal_id),
        )

        await interaction.followup.send(
            f"Your appeal has been submitted. You can track its progress in {ticket_channel.mention}.",
            ephemeral=True,
        )

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        await interaction.response.send_message(
            "Something went wrong while submitting your appeal. Please try again.",
            ephemeral=True,
        )
        raise error


def _build_appeal_embed(
    appeal_id: int,
    appellant: discord.Member,
    roblox_username: str,
    discord_tag: str,
    ban_reason: str,
    appeal_reason: str,
) -> discord.Embed:
    embed = discord.Embed(
        title=f"Case File  |  Appeal #{appeal_id}",
        color=COLOUR_PRIMARY,
    )
    embed.set_author(name="NFPD Ban Appeals  |  Staff Review")
    embed.add_field(name="Roblox Username", value=f"`{roblox_username}`", inline=True)
    embed.add_field(name="Discord Tag", value=discord_tag, inline=True)
    embed.add_field(name="Submitted By", value=appellant.mention, inline=True)
    embed.add_field(name="Reason for Ban", value=ban_reason, inline=False)
    embed.add_field(name="Appeal Statement", value=appeal_reason, inline=False)
    embed.set_footer(
        text=f"Appeal ID: {appeal_id}  |  Awaiting staff review",
    )
    embed.timestamp = discord.utils.utcnow()
    return embed
