# NFPD Ban Appeals Bot

A Discord bot for managing ban appeals with a voting system for the ban team.

## Setup

### 1. Railway Environment Variables

In your Railway service, set these environment variables:

| Variable | Value |
|---|---|
| `DISCORD_TOKEN` | Your bot token from the Discord Developer Portal |
| `DATABASE_URL` | Auto-injected by Railway when you add the Postgres plugin |

### 2. Add PostgreSQL to Railway

1. In your Railway project, click **+ New**
2. Select **Database > Add PostgreSQL**
3. Railway automatically injects `DATABASE_URL` into your service - no extra config needed.

### 3. Bot Permissions

When adding the bot to your server, it needs these permissions:

- Read Messages / View Channels
- Send Messages
- Manage Channels (to create ticket channels)
- Manage Messages
- Embed Links
- Ban Members (to execute unbans)
- Use Application Commands

Invite URL scopes: `bot` + `applications.commands`

### 4. Discord Developer Portal

Enable the **Server Members Intent** under your bot's Privileged Gateway Intents.

---

## First-Time Server Configuration

Run these commands once in your Discord server (requires Administrator):

**1. Configure channels and roles:**
```
/setup
  appeals_channel: #appeals-tickets
  voting_channel: #ban-team-voting
  results_channel: #appeal-results
  ban_team_role: @Ban Team
```

**2. Post the dashboard panel:**
```
/createdashboard
```
Run this in the public-facing channel where members submit appeals.

---

## Commands

| Command | Permission | Description |
|---|---|---|
| `/setup` | Administrator | Configure channels and ban team role |
| `/createdashboard` | Administrator | Post the appeal submission panel |
| `/forwardtobanteam` | Manage Guild | Manually forward an appeal to voting (run inside the ticket channel) |
| `/appealinfo <id>` | Manage Guild | View status and vote tally for any appeal |

---

## Appeal Flow

1. Member clicks **Submit a Ban Appeal** on the dashboard
2. A modal pops up asking for: Roblox username, Discord tag, ban reason, appeal statement
3. A private ticket channel is created for the member
4. Staff click **Forward to Ban Team** inside the ticket (or use `/forwardtobanteam`)
5. The appeal posts in the voting channel with **Unban** / **Keep Banned** buttons
6. After 48 hours, the bot checks votes:
   - If fewer than 3 votes: appeal closes as inconclusive
   - If Unban wins: verdict posted with **Execute Unban** and **Close Ticket** buttons
   - If Keep Banned wins: verdict posted with **Close Ticket** button only
7. Staff action the verdict; ticket channel is deleted automatically

---

## File Structure

```
bot.py           - Entry point
database.py      - PostgreSQL layer (asyncpg)
cogs/
  dashboard.py   - /setup and /createdashboard
  appeals.py     - /forwardtobanteam and /appealinfo
  voting.py      - Background task that finalises expired votes
views/
  appeal_panel.py    - Persistent dashboard button
  appeal_modal.py    - The modal form + ticket creation
  appeal_actions.py  - Forward/Close buttons inside ticket
  voting_panel.py    - Unban/Keep Banned vote buttons
  verdict_panel.py   - Execute Unban/Close Ticket after voting ends
```
"# NFPD-Appeals-Bot" 
