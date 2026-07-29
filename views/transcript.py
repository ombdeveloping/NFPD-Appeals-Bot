import io
from datetime import datetime, timezone

import discord

from config import BOT_AVATAR_URL, COLOUR_CLOSED


async def generate_transcript(channel: discord.TextChannel, appeal: dict) -> discord.File:
    lines = [
        "NFPD Ban Appeals - Ticket Transcript",
        "=" * 60,
        f"Appeal ID   : {appeal['id']}",
        f"Roblox User : {appeal['roblox_username']}",
        f"Discord     : {appeal['discord_tag']}",
        f"Status      : {appeal['status'].replace('_', ' ').title()}",
        f"Generated   : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
        "=" * 60,
        "",
    ]

    try:
        async for message in channel.history(limit=500, oldest_first=True):
            ts = message.created_at.strftime("%Y-%m-%d %H:%M")
            author = f"{message.author} [BOT]" if message.author.bot else str(message.author)
            content = message.content or ""
            for embed in message.embeds:
                title = embed.title or ""
                desc = (embed.description or "")[:300]
                content += f"\n  [Embed] {title}: {desc}" if title else f"\n  [Embed] {desc}"
            if content.strip():
                lines.append(f"[{ts}] {author}: {content.strip()}")
    except discord.HTTPException:
        lines.append("[Could not fetch full message history]")

    return discord.File(
        io.BytesIO("\n".join(lines).encode("utf-8")),
        filename=f"appeal-{appeal['id']}-transcript.txt",
    )


def build_transcript_embed(appeal: dict, actioned_by: discord.Member | discord.User, reason: str) -> discord.Embed:
    embed = discord.Embed(
        title=f"Transcript - Appeal #{appeal['id']}",
        color=COLOUR_CLOSED,
        timestamp=discord.utils.utcnow(),
    )
    embed.set_author(name="North Florida Police Department  |  Ban Appeals", icon_url=BOT_AVATAR_URL)
    embed.add_field(name="Roblox Username", value=f"`{appeal['roblox_username']}`", inline=True)
    embed.add_field(name="Discord", value=appeal["discord_tag"], inline=True)
    embed.add_field(name="Appellant", value=f"<@{appeal['appellant_id']}>", inline=True)
    embed.add_field(name="Actioned by", value=actioned_by.mention, inline=True)
    embed.add_field(name="Reason", value=reason, inline=True)
    embed.set_footer(text=f"Appeal ID: {appeal['id']}  |  NFPD Ban Appeals")
    return embed
