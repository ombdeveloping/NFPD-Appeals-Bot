from datetime import datetime, timezone

import discord

from config import BAN_TEAM_ROLE_IDS, BOT_AVATAR_URL, COLOUR_ACCEPTED, COLOUR_REJECTED, COLOUR_VOTING


def _build_vote_bar(unban: int, keep: int) -> str:
    total = unban + keep
    if total == 0:
        return "`▱▱▱▱▱▱▱▱▱▱`"
    filled = round((unban / total) * 10)
    return f"`{'▰' * filled}{'▱' * (10 - filled)}`"


class VotingPanelView(discord.ui.View):
    def __init__(self, bot, appeal_id: int = 0):
        super().__init__(timeout=None)
        self.bot = bot
        self.appeal_id = appeal_id

    def _resolve_appeal_id(self, message: discord.Message) -> int | None:
        if self.appeal_id:
            return self.appeal_id
        try:
            footer = message.embeds[0].footer.text
            part = footer.split("Appeal ID:")[1].strip().split()[0].rstrip("|").strip()
            return int(part)
        except (IndexError, ValueError, AttributeError):
            return None

    async def _can_vote(self, interaction: discord.Interaction) -> bool:
        member_role_ids = {role.id for role in interaction.user.roles}
        if BAN_TEAM_ROLE_IDS and (member_role_ids & BAN_TEAM_ROLE_IDS):
            return True
        try:
            config = await self.bot.db.get_guild_config(interaction.guild_id)
            db_role_id = config["ban_team_role"] if config else None
        except Exception:
            db_role_id = None
        if db_role_id and db_role_id in member_role_ids:
            return True
        if not BAN_TEAM_ROLE_IDS and not db_role_id:
            return True
        return False

    @discord.ui.button(label="Unban", style=discord.ButtonStyle.success, custom_id="votes:unban", emoji="🟢")
    async def vote_unban(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_vote(interaction, "unban")

    @discord.ui.button(label="Keep Banned", style=discord.ButtonStyle.danger, custom_id="votes:keep_banned", emoji="🔴")
    async def vote_keep_banned(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_vote(interaction, "keep_banned")

    async def _handle_vote(self, interaction: discord.Interaction, vote: str):
        await interaction.response.defer(ephemeral=True)

        if not await self._can_vote(interaction):
            await interaction.followup.send(
                "❌ You do not have permission to vote on appeals.", ephemeral=True
            )
            return

        appeal_id = self._resolve_appeal_id(interaction.message)
        if not appeal_id:
            await interaction.followup.send(
                "Could not determine which appeal this belongs to. Contact an admin.", ephemeral=True
            )
            return

        db = self.bot.db
        appeal = await db.get_appeal(appeal_id)
        if not appeal:
            await interaction.followup.send("This appeal could not be found.", ephemeral=True)
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
                await interaction.followup.send("The voting window for this appeal has closed.", ephemeral=True)
                return

        previous = await db.get_vote(appeal_id, interaction.user.id)
        await db.upsert_vote(appeal_id, interaction.user.id, vote)
        tally = await db.get_vote_tally(appeal_id)

        # Fetch a fresh message reference - using the stale interaction.message can fail silently.
        try:
            fresh = await interaction.channel.fetch_message(interaction.message.id)
            await _update_vote_embed(fresh, tally)
        except Exception:
            pass

        label = "Unban" if vote == "unban" else "Keep Banned"
        total = tally["unban"] + tally["keep_banned"]
        bar = _build_vote_bar(tally["unban"], tally["keep_banned"])

        if previous and previous["vote"] == vote:
            msg = f"You have already voted **{label}**."
        elif previous:
            old = "Unban" if previous["vote"] == "unban" else "Keep Banned"
            msg = f"Vote updated from **{old}** → **{label}**."
        else:
            msg = f"✅ **{label}** vote recorded."

        color = COLOUR_ACCEPTED if vote == "unban" else COLOUR_REJECTED
        embed = discord.Embed(color=color)
        embed.set_author(name="North Florida Police Department  |  Ban Team Vote", icon_url=BOT_AVATAR_URL)
        embed.description = msg
        embed.add_field(
            name="Current Tally",
            value=(
                f"🟢 Unban: **{tally['unban']}**  •  🔴 Keep Banned: **{tally['keep_banned']}**\n"
                f"🟢 {bar} 🔴  •  **{total}** total"
            ),
            inline=False,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)


async def _update_vote_embed(message: discord.Message, tally: dict) -> None:
    if not message or not message.embeds:
        return

    embed = message.embeds[0]
    bar = _build_vote_bar(tally["unban"], tally["keep_banned"])
    total = tally["unban"] + tally["keep_banned"]

    new_fields = []
    for field in embed.fields:
        # Match with or without emoji prefix - the embed uses emoji names, older messages may not
        name = field.name
        if name in ("Unban", "🟢 Unban", "\U0001F7E2 Unban"):
            new_fields.append(discord.EmbedField(
                name="🟢 Unban", value=f"**{tally['unban']}** vote(s)", inline=True
            ))
        elif name in ("Keep Banned", "🔴 Keep Banned", "\U0001F534 Keep Banned"):
            new_fields.append(discord.EmbedField(
                name="🔴 Keep Banned", value=f"**{tally['keep_banned']}** vote(s)", inline=True
            ))
        elif name in ("Vote Progress", "📊 Vote Progress", "\U0001F4CA Vote Progress"):
            new_fields.append(discord.EmbedField(
                name="📊 Vote Progress",
                value=f"🟢 {bar} 🔴\n**{total}** vote(s) cast",
                inline=False,
            ))
        else:
            new_fields.append(field)

    embed.clear_fields()
    for field in new_fields:
        embed.add_field(name=field.name, value=field.value, inline=field.inline)

    await message.edit(embed=embed)
