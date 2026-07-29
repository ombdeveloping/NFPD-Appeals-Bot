"""
Central configuration constants for the NFPD Appeals Bot.
All guild IDs, owner IDs, and brand values live here.
"""

# The Discord user ID that receives DMs when the bot joins an unapproved server.
DEVELOPER_ID = 1285998518213017663

# Servers the bot is permitted to operate in.
# Add guild IDs here as integers to approve them.
APPROVED_GUILD_IDS: set[int] = {
    # Example: 123456789012345678
}

# Sent to the guild before the bot leaves an unapproved server.
UNAUTHORISED_GUILD_MESSAGE = (
    "This server is not an approved NFPD server. "
    "If you believe this is a mistake, please DM the developer.\n\n"
    "**Developer:** omb\n"
    "**Username:** ombdeveloping\n"
    "**Discord ID:** `1285998518213017663`"
)

# ── Brand palette ────────────────────────────────────────────────────────────
# Primary dark navy used on most embeds.
COLOUR_PRIMARY = 0x0D1117

# Steel blue for informational / open-state embeds.
COLOUR_INFO = 0x2563EB

# Amber for voting / pending state.
COLOUR_VOTING = 0xD97706

# Green for accepted / positive outcomes.
COLOUR_ACCEPTED = 0x16A34A

# Red for rejected / negative outcomes.
COLOUR_REJECTED = 0xDC2626

# Neutral grey for closed / inconclusive states.
COLOUR_CLOSED = 0x6B7280

# ── Minimum vote threshold ───────────────────────────────────────────────────
MINIMUM_VOTES = 3
