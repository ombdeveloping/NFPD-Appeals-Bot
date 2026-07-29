import discord


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
        placeholder="Explain your case clearly and honestly.",
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

        appeal_id = await db.create_appeal(
            guild_id=guild_id,
            appellant_id=user_id,
            roblox_username=self.roblox_username.value.strip(),
            discord_tag=self.discord_tag.value.strip(),
            ban_reason=self.ban_reason.value.strip(),
            appeal_reason=self.appeal_reason.value.strip(),
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
            topic=f"Ban appeal for {interaction.user} | Appeal ID: {appeal_id}",
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

        embed = _build_appeal_embed(
            appeal_id=appeal_id,
            appellant=interaction.user,
            roblox_username=self.roblox_username.value.strip(),
            discord_tag=self.discord_tag.value.strip(),
            ban_reason=self.ban_reason.value.strip(),
            appeal_reason=self.appeal_reason.value.strip(),
        )

        from views.appeal_actions import AppealActionsView
        await ticket_channel.send(
            content=interaction.user.mention,
            embed=embed,
            view=AppealActionsView(self.bot, appeal_id),
        )

        await interaction.followup.send(
            f"Your appeal has been submitted. Head to {ticket_channel.mention} to track its progress.",
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
        title="Ban Appeal",
        color=0x2C2F33,
    )
    embed.set_author(
        name="NFPD Ban Appeals",
        icon_url="https://i.imgur.com/4M34hi2.png",
    )
    embed.add_field(name="Roblox Username", value=roblox_username, inline=True)
    embed.add_field(name="Discord", value=discord_tag, inline=True)
    embed.add_field(name="Submitted By", value=appellant.mention, inline=True)
    embed.add_field(name="Reason for Ban", value=ban_reason, inline=False)
    embed.add_field(name="Appeal Statement", value=appeal_reason, inline=False)
    embed.set_footer(text=f"Appeal ID: {appeal_id}")
    embed.timestamp = discord.utils.utcnow()
    return embed
