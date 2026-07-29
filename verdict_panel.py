import discord


class VerdictPanelView(discord.ui.View):
    """
    Shown in the results channel after voting ends.
    Staff either execute the unban or close the ticket.
    """

    def __init__(self, bot, appeal_id: int = 0):
        super().__init__(timeout=None)
        self.bot = bot
        self.appeal_id = appeal_id
        # custom_id must be static for persistent views - appeal_id carried via embed footer
        self._appeal_id_override = appeal_id

    @discord.ui.button(
        label="Execute Unban",
        style=discord.ButtonStyle.success,
        custom_id="verdict:execute_unban",
        emoji="✅",
    )
    async def execute_unban(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        appeal_id = self._resolve_appeal_id(interaction.message)
        if not appeal_id:
            await interaction.followup.send("Could not resolve appeal ID.", ephemeral=True)
            return

        db = self.bot.db
        appeal = await db.get_appeal(appeal_id)
        if not appeal:
            await interaction.followup.send("Appeal not found.", ephemeral=True)
            return

        try:
            await interaction.guild.unban(
                discord.Object(id=appeal["appellant_id"]),
                reason=f"Ban appeal {appeal_id} accepted by {interaction.user}",
            )
            unban_note = f"<@{appeal['appellant_id']}> (`{appeal['roblox_username']}`) has been unbanned."
        except discord.NotFound:
            unban_note = f"User `{appeal['roblox_username']}` was not found in the ban list - they may have already been unbanned."
        except discord.Forbidden:
            await interaction.followup.send(
                "I don't have permission to unban members. Please check my role permissions.",
                ephemeral=True,
            )
            return

        await db.close_appeal(appeal_id, "accepted")
        button.disabled = True
        self._disable_other_button(interaction.message, "verdict:close_ticket")
        await interaction.message.edit(view=self)

        await interaction.followup.send(unban_note, ephemeral=False)

        await _close_ticket_channel(self.bot, appeal)

    @discord.ui.button(
        label="Close Ticket",
        style=discord.ButtonStyle.secondary,
        custom_id="verdict:close_ticket",
        emoji="🔒",
    )
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        appeal_id = self._resolve_appeal_id(interaction.message)
        if not appeal_id:
            await interaction.followup.send("Could not resolve appeal ID.", ephemeral=True)
            return

        db = self.bot.db
        appeal = await db.get_appeal(appeal_id)
        await db.close_appeal(appeal_id, "rejected")

        button.disabled = True
        self._disable_other_button(interaction.message, "verdict:execute_unban")
        await interaction.message.edit(view=self)

        await interaction.followup.send("Appeal closed.", ephemeral=True)

        if appeal:
            await _close_ticket_channel(self.bot, appeal)

    def _resolve_appeal_id(self, message: discord.Message) -> int | None:
        """Extract appeal ID from the embed footer text."""
        if self._appeal_id_override:
            return self._appeal_id_override
        try:
            footer = message.embeds[0].footer.text
            # Footer format: "Appeal ID: 42 | ..."
            part = footer.split("Appeal ID:")[1].strip().split()[0]
            return int(part)
        except (IndexError, ValueError, AttributeError):
            return None

    def _disable_other_button(self, message: discord.Message, custom_id: str):
        for child in self.children:
            if getattr(child, "custom_id", None) == custom_id:
                child.disabled = True


async def _close_ticket_channel(bot, appeal):
    """Attempt to delete the original ticket channel after a verdict."""
    if not appeal["ticket_channel"]:
        return
    for guild in bot.guilds:
        channel = guild.get_channel(appeal["ticket_channel"])
        if channel:
            try:
                await channel.send(
                    "This appeal has been resolved. The ticket will be deleted in 10 seconds."
                )
                import asyncio
                await asyncio.sleep(10)
                await channel.delete(reason=f"Appeal {appeal['id']} resolved.")
            except discord.HTTPException:
                pass
            return
