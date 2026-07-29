from datetime import datetime, timezone

import discord

from config import BAN_TEAM_ROLE_IDS


class VotingPanelView(discord.ui.View):
    """Unban / Keep Banned buttons in the ban team voting channel."""

    def __init__(self, bot, appeal_id: int = 0):
        super().__init__(timeout=None)
        self.bot = bot
        self.appeal_id = appeal_id

    def _resolve_appeal_id(self, message: discord.Message) -> int | None:
        """Return the stored appeal ID, or parse it from the embed footer on restart."""
        if self.appeal_id:
            return self.appeal_id
        try:
            footer = message.embeds[0].footer.text
            # Footer format: "Appeal ID: 5  |  Minimum 3 votes required"
            part = footer.split("Appeal ID:")[1].strip().split()[0].rstrip("|").strip()
            return int(part)
        except (IndexError, ValueError, AttributeError):
            return None

    async def _can_vote(self, interaction: discord.Interaction) -> bool:
        """Return True if the member is permitted to vote.

        Allowed when ANY of:
          - No role restrictions are configured at all (open voting)
          - The member has a role listed in BAN_TEAM_ROLE_IDS (env var)
          - The member has the ban_team_role configured via /setup

        Denied when a role IS configured and the member has none of them.
        """
        member_role_ids = {role.id for role in interaction.user.roles}

        # Check env-var role list
        if BAN_TEAM_ROLE_IDS and (member_role_ids & BAN_TEAM_ROLE_IDS):
            return True

        # Check /setup role from database
        try:
            config = await self.bot.db.get_guild_config(interaction.guild_id)
            db_role_id = config["ban_team_role"] if config else None
        except Exception:
            db_role_id = None

        if db_role_id and db_role_id in member_role_ids:
            return True

        # If no restrictions at all are configured, allow anyone
        if not BAN_TEAM_ROLE_IDS and not db_role_id:
            return True

        return False

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

        if not await self._can_vote(interaction):
            await interaction.followup.send(
                "You do not have permission to vote on appeals.", ephemeral=True
            )
            return

        appeal_id = self._resolve_appeal_id(interaction.message)
        if not appeal_id:
            await interaction.followup.send(
                "Could not determine which appeal this belongs to. Please contact an admin.",
                ephemeral=True,
            )
            return

        db = self.bot.db
        appeal = await db.get_appeal(appeal_id)
        if not appeal:
            await interaction.followup.send(
                "This appeal could not be found in the database.", ephemeral=True
            )
            return

        if appeal["status"] != "voting":
            await interaction.followup.send(
                f"This appeal is **{appeal['status'].replace('_', ' ').title()}** and is no longer accepting votes.",
                ephemeral=True,
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

        # Update the live vote counters on the embed.
        # Wrapped so a permissions failure here doesn't prevent the confirmation reply.
        try:
            await _update_vote_fields(interaction.message, tally)
        except discord.HTTPException:
            pass

        label = "Unban" if vote == "unban" else "Keep Banned"

        if previous and previous["vote"] == vote:
            await interaction.followup.send(
                f"You have already voted **{label}**.", ephemeral=True
            )
        elif previous:
            old_label = "Unban" if previous["vote"] == "unban" else "Keep Banned"
            await interaction.followup.send(
                f"Vote updated from **{old_label}** to **{label}**.", ephemeral=True
            )
        else:
            await interaction.followup.send(
                f"Your **{label}** vote has been recorded.", ephemeral=True
            )


async def _update_vote_fields(message: discord.Message, tally: dict) -> None:
    """Rebuild the Unban / Keep Banned fields on the voting embed with fresh counts."""
    if not message.embeds:
        return
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