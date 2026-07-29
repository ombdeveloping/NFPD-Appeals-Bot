# NFPD Ban Appeals Bot

A Discord bot for managing ban appeals with a structured voting system, guild allowlist, and automatic developer notification for unauthorised server joins.

## Setup

### 1. Approve your server(s)

Open `constants.py` and add your guild ID(s) to `APPROVED_GUILD_IDS`:

```python
APPROVED_GUILD_IDS: set[int] = {
    123456789012345678,  # Your server ID
}
```

If the bot joins any server not in this set, it will:
1. Try to pull the inviter from the audit log
2. Generate a temporary server invite
3. DM the developer (ID `1285998518213017663`) with all details
4. Send an unauthorised notice in the server
5. Leave immediately

### 2. Railway - add PostgreSQL

In your Railway project: **+ New > Database > Add PostgreSQL**.
`DATABASE_URL` is injected automatically - no config needed.

### 3. Set environment variables

| Variable | Value |
|---|---|
| `DISCORD_TOKEN` | Your bot token from the Discord Developer Portal |
| `DATABASE_URL` | Auto-injected by Railway Postgres plugin |

### 4. Enable Members Intent

In the Discord Developer Portal, under your bot > Privileged Gateway Intents, enable **Server Members Intent**.

### 5. Bot permissions

The bot needs these permissions when added to a server:

- View Channels / Read Messages
- Send Messages
- Manage Channels
- Manage Messages
- Embed Links
- Ban Members
- View Audit Log
- Use Application Commands

Invite scopes: `bot` + `applications.commands`

---

## First-time server setup

```
/setup
  appeals_channel: #appeals-tickets
  voting_channel:  #ban-team-votes
  results_channel: #appeal-results
  ban_team_role:   @Ban Team

/createdashboard   <- run this in your public-facing appeals channel
```

Tables create themselves on first boot.

---

## Commands

| Command | Permission | Description |
|---|---|---|
| `/setup` | Administrator | Set channels and ban team role |
| `/createdashboard` | Administrator | Post the public appeal submission panel |
| `/forwardtobanteam` | Manage Guild | Manually forward appeal to voting (run inside ticket channel) |
| `/appealinfo <id>` | Manage Guild | View full case file and live vote tally |

---

## Appeal flow

1. Member clicks **Submit a Ban Appeal** on the dashboard panel
2. A modal pops up - Roblox username, Discord tag, reason for ban, appeal statement
3. A private ticket channel is created; the member and bot can see it
4. Staff click **Forward to Ban Team** (or use `/forwardtobanteam`)
5. Appeal posts in the voting channel with a ban team role ping and live vote counters
6. After 48 hours the background task checks votes:
   - Fewer than 3 votes: inconclusive, appeal closed
   - Unban wins: verdict posted with **Execute Unban** + **Close Ticket**
   - Keep Banned wins: verdict posted with **Close Ticket** only
7. Staff action the verdict; ticket channel deletes itself

---

## File structure

```
bot.py             - Entry point, guild guard (on_guild_join)
constants.py       - APPROVED_GUILD_IDS, brand colours, thresholds
database.py        - asyncpg PostgreSQL layer
cogs/
  dashboard.py     - /setup, /createdashboard
  appeals.py       - /forwardtobanteam, /appealinfo
  voting.py        - Background task that finalises expired votes
views/
  appeal_panel.py  - Persistent dashboard button
  appeal_modal.py  - Modal form + ticket channel creation
  appeal_actions.py- Forward / Close Ticket buttons in ticket
  voting_panel.py  - Unban / Keep Banned vote buttons
  verdict_panel.py - Execute Unban / Close Ticket after voting ends
```
