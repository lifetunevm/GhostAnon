import os
import ssl
import asyncpg

_pool: asyncpg.Pool | None = None


def _get_ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _clean_dsn(dsn: str) -> str:
    return dsn.split("?")[0]


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        dsn = os.environ.get("DATABASE_URL", "")
        _pool = await asyncpg.create_pool(
            _clean_dsn(dsn),
            ssl=_get_ssl_context(),
        )
    return _pool


async def init_db():
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS questions (
                id SERIAL PRIMARY KEY,
                target_user_id BIGINT NOT NULL REFERENCES users(user_id),
                sender_user_id BIGINT,
                text TEXT NOT NULL,
                answered BOOLEAN DEFAULT FALSE,
                answer_text TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            );
        """)


async def register_user(user_id: int, username: str | None, first_name: str | None):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO users (user_id, username, first_name)
               VALUES ($1, $2, $3)
               ON CONFLICT (user_id) DO UPDATE SET username=EXCLUDED.username, first_name=EXCLUDED.first_name""",
            user_id, username, first_name,
        )


async def get_user(user_id: int) -> dict | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM users WHERE user_id=$1", user_id)
        return dict(row) if row else None


async def save_question(target_user_id: int, sender_user_id: int | None, text: str) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        q_id = await conn.fetchval(
            "INSERT INTO questions (target_user_id, sender_user_id, text) VALUES ($1, $2, $3) RETURNING id",
            target_user_id, sender_user_id, text,
        )
        return q_id


async def save_answer(question_id: int, answer_text: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE questions SET answered=TRUE, answer_text=$1 WHERE id=$2",
            answer_text, question_id,
        )


async def get_unanswered_questions(user_id: int) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM questions WHERE target_user_id=$1 AND answered=FALSE ORDER BY created_at DESC",
            user_id,
        )
        return [dict(r) for r in rows]


async def get_question_by_id(question_id: int) -> dict | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM questions WHERE id=$1", question_id)
        return dict(row) if row else None


async def get_user_stats(user_id: int) -> tuple[int, int, int]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        total = await conn.fetchval(
            "SELECT COUNT(*) FROM questions WHERE target_user_id=$1", user_id,
        )
        answered = await conn.fetchval(
            "SELECT COUNT(*) FROM questions WHERE target_user_id=$1 AND answered=TRUE", user_id,
        )
        unanswered = await conn.fetchval(
            "SELECT COUNT(*) FROM questions WHERE target_user_id=$1 AND answered=FALSE", user_id,
        )
        return total or 0, answered or 0, unanswered or 0
