"""
Runtime configuration loaded entirely from environment variables.

Set these in Railway's Variables tab - no code changes needed to approve servers,
add developers, or change vote thresholds.

  DISCORD_TOKEN          Your bot token (required)
  DATABASE_URL           Injected automatically by Railway's PostgreSQL plugin (required)

  APPROVED_GUILD_IDS     Comma-separated guild IDs the bot is allowed to stay in.
                         Leave empty and the bot leaves every server it joins.
                         Example: 123456789012345678,987654321098765432

  LEAVE_UNAPPROVED_GUILDS  Set to true to auto-leave unapproved servers (default: true).
                           Set to false to stay but still alert developers.

  DEVELOPER_IDS          Comma-separated Discord user IDs to DM when an unapproved
                         server join is detected. Default: 1285998518213017663 (omb).

  MINIMUM_VOTES          Votes needed for a valid appeal result (default: 3).

  VOTING_HOURS           How many hours the voting window stays open (default: 48).

  BAN_TEAM_ROLE_IDS      Comma-separated role IDs whose members are allowed to vote.
                         If empty, anyone in the voting channel can vote.
                         These supplement (not replace) the ban_team_role set via /setup.
"""
import os
import sys


def _fail(message: str) -> None:
    print(f"Configuration error: {message}", file=sys.stderr)
    raise SystemExit(1)


def _parse_id_list(name: str, *, default: str = "") -> set[int]:
    raw = os.environ.get(name, default).strip()
    if not raw:
        return set()
    try:
        return {int(piece.strip()) for piece in raw.split(",") if piece.strip()}
    except ValueError:
        _fail(f"{name} must be a comma-separated list of numeric Discord IDs, got: {raw!r}")


def _parse_bool(name: str, *, default: bool = True) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes"}


def _parse_int(name: str, *, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        _fail(f"{name} must be an integer, got: {raw!r}")


# ── Required ─────────────────────────────────────────────────────────────────

DISCORD_TOKEN: str = os.environ.get("DISCORD_TOKEN", "").strip()
if not DISCORD_TOKEN:
    _fail("DISCORD_TOKEN is required. Set it in Railway's Variables tab.")

DATABASE_URL: str = os.environ.get("DATABASE_URL", "").strip()
if not DATABASE_URL:
    _fail(
        "DATABASE_URL is required. "
        "Add a PostgreSQL plugin to your Railway project and it will be injected automatically."
    )

# ── Guild allowlist ───────────────────────────────────────────────────────────

APPROVED_GUILD_IDS: set[int] = _parse_id_list("APPROVED_GUILD_IDS")

# When True (the default), the bot leaves any server not in APPROVED_GUILD_IDS.
# Set LEAVE_UNAPPROVED_GUILDS=false in Railway to stay but still alert developers.
LEAVE_UNAPPROVED_GUILDS: bool = _parse_bool("LEAVE_UNAPPROVED_GUILDS", default=True)

# ── Developer alerts ──────────────────────────────────────────────────────────

# Defaults to omb's ID. Add more IDs separated by commas.
DEVELOPER_IDS: set[int] = _parse_id_list("DEVELOPER_IDS", default="1285998518213017663")

# ── Appeal settings ───────────────────────────────────────────────────────────

MINIMUM_VOTES: int = _parse_int("MINIMUM_VOTES", default=3)
VOTING_HOURS: int  = _parse_int("VOTING_HOURS", default=48)
BAN_TEAM_ROLE_IDS: set[int] = _parse_id_list("BAN_TEAM_ROLE_IDS")

# ── Brand ─────────────────────────────────────────────────────────────────────

COLOUR_PRIMARY  = 0x0D1117
COLOUR_INFO     = 0x2563EB
COLOUR_VOTING   = 0xD97706
COLOUR_ACCEPTED = 0x16A34A
COLOUR_REJECTED = 0xDC2626
COLOUR_CLOSED   = 0x6B7280

UNAUTHORISED_GUILD_MESSAGE = (
    "This server is not an approved NFPD server. "
    "If you believe this is a mistake, please DM the developer.\n\n"
    "**Developer:** omb\n"
    "**Username:** ombdeveloping\n"
    "**Discord ID:** `1285998518213017663`"
)
