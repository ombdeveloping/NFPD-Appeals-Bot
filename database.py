import asyncpg


class Database:
    """Thin wrapper around an asyncpg connection pool."""

    def __init__(self, dsn: str):
        self._dsn = dsn
        self._pool: asyncpg.Pool = None

    async def initialise(self):
        self._pool = await asyncpg.create_pool(self._dsn, min_size=1, max_size=5)
        await self._create_tables()

    async def _create_tables(self):
        async with self._pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS guild_config (
                    guild_id         BIGINT PRIMARY KEY,
                    appeals_channel  BIGINT,
                    voting_channel   BIGINT,
                    results_channel  BIGINT,
                    ban_team_role    BIGINT,
                    dashboard_msg_id BIGINT
                )
            """)

            await conn.execute("""
                CREATE TABLE IF NOT EXISTS appeals (
                    id               SERIAL PRIMARY KEY,
                    guild_id         BIGINT NOT NULL,
                    appellant_id     BIGINT NOT NULL,
                    roblox_username  TEXT NOT NULL,
                    discord_tag      TEXT NOT NULL,
                    ban_reason       TEXT NOT NULL,
                    appeal_reason    TEXT NOT NULL,
                    ticket_channel   BIGINT,
                    voting_msg_id    BIGINT,
                    status           TEXT NOT NULL DEFAULT 'open',
                    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    closes_at        TIMESTAMPTZ
                )
            """)

            # Partial unique index: one open appeal per user per guild.
            # Unlike UNIQUE(guild_id, appellant_id, status), this only fires when status='open',
            # so closed/rejected/accepted appeals can accumulate freely.
            await conn.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS appeals_one_open_per_user
                ON appeals (guild_id, appellant_id)
                WHERE status = 'open'
            """)

            await conn.execute("""
                CREATE TABLE IF NOT EXISTS votes (
                    appeal_id  INT NOT NULL REFERENCES appeals(id) ON DELETE CASCADE,
                    voter_id   BIGINT NOT NULL,
                    vote       TEXT NOT NULL CHECK (vote IN ('unban', 'keep_banned')),
                    voted_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (appeal_id, voter_id)
                )
            """)

    # ------------------------------------------------------------------ #
    # Guild config                                                         #
    # ------------------------------------------------------------------ #

    async def get_guild_config(self, guild_id: int) -> asyncpg.Record | None:
        async with self._pool.acquire() as conn:
            return await conn.fetchrow(
                "SELECT * FROM guild_config WHERE guild_id = $1", guild_id
            )

    async def upsert_guild_config(self, guild_id: int, **fields):
        if not fields:
            return
        columns = ", ".join(fields.keys())
        placeholders = ", ".join(f"${i + 2}" for i in range(len(fields)))
        updates = ", ".join(f"{k} = EXCLUDED.{k}" for k in fields)
        values = list(fields.values())

        async with self._pool.acquire() as conn:
            await conn.execute(
                f"""
                INSERT INTO guild_config (guild_id, {columns})
                VALUES ($1, {placeholders})
                ON CONFLICT (guild_id) DO UPDATE SET {updates}
                """,
                guild_id,
                *values,
            )

    # ------------------------------------------------------------------ #
    # Appeals                                                              #
    # ------------------------------------------------------------------ #

    async def get_open_appeal_for_user(self, guild_id: int, user_id: int) -> asyncpg.Record | None:
        async with self._pool.acquire() as conn:
            return await conn.fetchrow(
                "SELECT * FROM appeals WHERE guild_id = $1 AND appellant_id = $2 AND status = 'open'",
                guild_id,
                user_id,
            )

    async def create_appeal(
        self,
        guild_id: int,
        appellant_id: int,
        roblox_username: str,
        discord_tag: str,
        ban_reason: str,
        appeal_reason: str,
    ) -> int:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO appeals
                    (guild_id, appellant_id, roblox_username, discord_tag, ban_reason, appeal_reason)
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING id
                """,
                guild_id,
                appellant_id,
                roblox_username,
                discord_tag,
                ban_reason,
                appeal_reason,
            )
            return row["id"]

    async def get_appeal(self, appeal_id: int) -> asyncpg.Record | None:
        async with self._pool.acquire() as conn:
            return await conn.fetchrow(
                "SELECT * FROM appeals WHERE id = $1", appeal_id
            )

    async def set_appeal_ticket_channel(self, appeal_id: int, channel_id: int):
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE appeals SET ticket_channel = $1 WHERE id = $2",
                channel_id,
                appeal_id,
            )

    async def set_appeal_voting(self, appeal_id: int, voting_msg_id: int, closes_at):
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE appeals SET voting_msg_id = $1, closes_at = $2, status = 'voting' WHERE id = $3",
                voting_msg_id,
                closes_at,
                appeal_id,
            )

    async def close_appeal(self, appeal_id: int, status: str):
        """
        Valid statuses:
          'accepted'       - vote result: unban won (awaiting staff action)
          'rejected'       - vote result: keep banned won (awaiting staff action)
          'closed'         - inconclusive vote, or staff manually closed before voting
          'actioned_unban' - staff pressed Execute Unban
          'actioned_close' - staff pressed Close Ticket after verdict
        """
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE appeals SET status = $1 WHERE id = $2",
                status,
                appeal_id,
            )

    async def get_appeals_due_for_verdict(self):
        """Returns all appeals in 'voting' status whose closes_at has passed."""
        async with self._pool.acquire() as conn:
            return await conn.fetch(
                "SELECT * FROM appeals WHERE status = 'voting' AND closes_at <= NOW()"
            )

    # ------------------------------------------------------------------ #
    # Votes                                                                #
    # ------------------------------------------------------------------ #

    async def get_vote(self, appeal_id: int, voter_id: int) -> asyncpg.Record | None:
        async with self._pool.acquire() as conn:
            return await conn.fetchrow(
                "SELECT * FROM votes WHERE appeal_id = $1 AND voter_id = $2",
                appeal_id,
                voter_id,
            )

    async def upsert_vote(self, appeal_id: int, voter_id: int, vote: str):
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO votes (appeal_id, voter_id, vote)
                VALUES ($1, $2, $3)
                ON CONFLICT (appeal_id, voter_id) DO UPDATE SET vote = EXCLUDED.vote
                """,
                appeal_id,
                voter_id,
                vote,
            )

    async def get_recent_appeals(self, guild_id: int, limit: int = 5) -> list:
        async with self._pool.acquire() as conn:
            return await conn.fetch(
                "SELECT id, status, roblox_username, appellant_id, created_at "
                "FROM appeals WHERE guild_id = $1 ORDER BY id DESC LIMIT $2",
                guild_id,
                limit,
            )

    async def get_vote_tally(self, appeal_id: int) -> dict:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT vote, COUNT(*) AS count FROM votes WHERE appeal_id = $1 GROUP BY vote",
                appeal_id,
            )
        tally = {"unban": 0, "keep_banned": 0}
        for row in rows:
            tally[row["vote"]] = row["count"]
        return tally
