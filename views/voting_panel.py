from datetime import datetime, timezone

import discord


class VotingPanelView(discord.ui.View):
    """Unban / Keep Banned buttons in the ban team voting channel."""

    def __init__(self, bot, appeal_id: int = 0):
        super().__init__(timeout=None)
        self.bot = bot
        self.appeal_id = appeal_id

    def _resolve_appeal_id(self, message: discord.Message) -> int | None:
        """Fall back to parsing the embed footer when the instance ID is 0 (post-restart)."""
        if self.appeal_id:
            return self.appeal_id
        try:
            footer = message.embeds[0].footer.text
            part = footer.split("Appeal ID:")[1].strip().split()[0].rstrip("|").strip()
            return int(part)
        except (IndexError, ValueError, AttributeError):
            return None

    async def _check_voter_role(self, interaction: discord.Interaction) -> bool:
        """Return True if the user has the ban team role (or no role is configured)."""
        db = self.bot.db
        config = await db.get_guild_config(interaction.guild_id)
        if not config or not config["ban_team_role"]:
            return True
        role = interaction.guild.get_role(config["ban_team_role"])
        if role is None:
            return True
        return role in interaction.user.roles

    @discord.ui.button(
        label="Unban",
        style=discord.ButtonStyle.success,
        custom_id="votes:unban",
    )
    async def vote_unban(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_vote(interaction, "unban")

    @discord.ui.button(
        label="Keep Banned",
        style=discord.ButtonStyle.danger,
        custom_id="votes:keep_banned",
    )
    async def vote_keep_banned(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_vote(interaction, "keep_banned")

    async def _handle_vote(self, interaction: discord.Interaction, vote: str):
        await interaction.response.defer(ephemeral=True)
        db = self.bot.db

        if not await self._check_voter_role(interaction):
            await interaction.followup.send(
                "You do not have the required role to vote on appeals.", ephemeral=True
            )
            return

        appeal_id = self._resolve_appeal_id(interaction.message)
        if not appeal_id:
            await interaction.followup.send(
                "Could not determine which appeal this belongs to. Please contact an admin.",
                ephemeral=True,
            )
            return

        appeal = await db.get_appeal(appeal_id)
        if not appeal or appeal["status"] != "voting":
            await interaction.followup.send(
                "This appeal is no longer accepting votes.", ephemeral=True
            )
            return

        if appeal["closes_at"]:
            closes_at = appeal["closes_at"]
            if closes_at.tzinfo is None:
                closes_at = closes_at.replace(tzinfo=timezone.utc)
            if closes_at < datetime.now(timezone.utc):
                await interaction.followup.send(
                    "The voting window for this appeal has closed.", ephemeral=True
                )
                return

        previous = await db.get_vote(appeal_id, interaction.user.id)
        await db.upsert_vote(appeal_id, interaction.user.id, vote)

        tally = await db.get_vote_tally(appeal_id)
        await _update_vote_fields(interaction.message, tally)

        label = "Unban" if vote == "unban" else "Keep Banned"

        if previous and previous["vote"] == vote:
            await interaction.followup.send(
                f"You have already voted **{label}**.", ephemeral=True
            )
        elif previous:
            old_label = "Unban" if previous["vote"] == "unban" else "Keep Banned"
            await interaction.followup.send(
                f"Your vote has been updated from **{old_label}** to **{label}**.", ephemeral=True
            )
        else:
            await interaction.followup.send(
                f"Your vote for **{label}** has been recorded.", ephemeral=True
            )


async def _update_vote_fields(message: discord.Message, tally: dict):
    """Update the Unban and Keep Banned count fields on the voting embed."""
    embed = message.embeds[0]
    new_fields = []
    for field in embed.fields:
        if field.name == "Unban":
            new_fields.append(
                discord.EmbedField(name="Unban", value=f"**{tally['unban']}** vote(s)", inline=True)
            )
        elif field.name == "Keep Banned":
            new_fields.append(
                discord.EmbedField(name="Keep Banned", value=f"**{tally['keep_banned']}** vote(s)", inline=True)
            )
        else:
            new_fields.append(field)

    embed.clear_fields()
    for field in new_fields:
        embed.add_field(name=field.name, value=field.value, inline=field.inline)

    await message.edit(embed=embed)
