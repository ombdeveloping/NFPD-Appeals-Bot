import discord
from datetime import datetime, timezone


class VotingPanelView(discord.ui.View):
    """Voting buttons attached to the appeal in the ban team channel."""

    def __init__(self, bot, appeal_id: int):
        super().__init__(timeout=None)
        self.bot = bot
        self.appeal_id = appeal_id

    @discord.ui.button(
        label="Unban",
        style=discord.ButtonStyle.success,
        custom_id="votes:unban",
        emoji="✅",
    )
    async def vote_unban(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_vote(interaction, "unban")

    @discord.ui.button(
        label="Keep Banned",
        style=discord.ButtonStyle.danger,
        custom_id="votes:keep_banned",
        emoji="🚫",
    )
    async def vote_keep_banned(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_vote(interaction, "keep_banned")

    async def _handle_vote(self, interaction: discord.Interaction, vote: str):
        await interaction.response.defer(ephemeral=True)
        db = self.bot.db

        appeal = await db.get_appeal(self.appeal_id)
        if not appeal or appeal["status"] != "voting":
            await interaction.followup.send(
                "This appeal is no longer accepting votes.", ephemeral=True
            )
            return

        if appeal["closes_at"] and appeal["closes_at"].replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
            await interaction.followup.send(
                "The voting window for this appeal has closed.", ephemeral=True
            )
            return

        previous = await db.get_vote(self.appeal_id, interaction.user.id)
        await db.upsert_vote(self.appeal_id, interaction.user.id, vote)

        tally = await db.get_vote_tally(self.appeal_id)
        await _update_voting_embed(interaction.message, tally)

        label = "Unban" if vote == "unban" else "Keep Banned"
        if previous:
            previous_label = "Unban" if previous["vote"] == "unban" else "Keep Banned"
            if previous["vote"] == vote:
                await interaction.followup.send(
                    f"You have already voted **{label}**.", ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"Your vote has been changed from **{previous_label}** to **{label}**.",
                    ephemeral=True,
                )
        else:
            await interaction.followup.send(
                f"Your vote for **{label}** has been recorded.", ephemeral=True
            )


async def _update_voting_embed(message: discord.Message, tally: dict):
    """Edits the vote count fields on the voting embed in place."""
    embed = message.embeds[0]
    new_fields = []
    for field in embed.fields:
        if field.name == "Unban":
            new_fields.append(
                discord.EmbedField(name="Unban", value=f"{tally['unban']} vote(s)", inline=True)
            )
        elif field.name == "Keep Banned":
            new_fields.append(
                discord.EmbedField(name="Keep Banned", value=f"{tally['keep_banned']} vote(s)", inline=True)
            )
        else:
            new_fields.append(field)

    embed.clear_fields()
    for field in new_fields:
        embed.add_field(name=field.name, value=field.value, inline=field.inline)

    await message.edit(embed=embed)
