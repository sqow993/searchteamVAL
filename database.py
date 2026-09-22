import asyncpg
from config import DATABASE_URL, RANKS, RANK_TOLERANCE

_pool = None


async def init_db():
    """Создаёт пул соединений и таблицу"""
    global _pool
    print(f"[DB] Подключение к Supabase...")

    _pool = await asyncpg.create_pool(
        DATABASE_URL,
        min_size=1,
        max_size=5,
        statement_cache_size=0,  # для Session pooler
    )

    async with _pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS public.users (
                telegram_id BIGINT PRIMARY KEY,
                riot_id TEXT NOT NULL,
                tracker_url TEXT NOT NULL,
                rank TEXT DEFAULT 'Unranked',
                bio TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
    print("[DB] Таблица готова")


async def save_user(telegram_id: int, riot_id: str, tracker_url: str,
                    rank: str = "Unranked"):
    print(f"[DB] save_user: tg={telegram_id}, riot={riot_id}, rank={rank}")
    async with _pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO public.users (telegram_id, riot_id, tracker_url, rank)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (telegram_id) DO UPDATE SET
                riot_id = EXCLUDED.riot_id,
                tracker_url = EXCLUDED.tracker_url,
                rank = EXCLUDED.rank
        """, telegram_id, riot_id, tracker_url, rank)
    print("[DB] save_user OK")


async def update_bio(telegram_id: int, bio: str):
    async with _pool.acquire() as conn:
        await conn.execute(
            "UPDATE public.users SET bio = $1 WHERE telegram_id = $2",
            bio, telegram_id
        )
    print("[DB] update_bio OK")


async def update_rank(telegram_id: int, rank: str):
    async with _pool.acquire() as conn:
        await conn.execute(
            "UPDATE public.users SET rank = $1 WHERE telegram_id = $2",
            rank, telegram_id
        )
    print(f"[DB] update_rank OK: {rank}")


async def get_user(telegram_id: int):
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM public.users WHERE telegram_id = $1",
            telegram_id
        )
        return dict(row) if row else None


async def delete_user(telegram_id: int):
    async with _pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM public.users WHERE telegram_id = $1",
            telegram_id
        )
    print("[DB] delete_user OK")


async def count_users() -> int:
    async with _pool.acquire() as conn:
        return await conn.fetchval("SELECT COUNT(*) FROM public.users")


def _rank_range(rank: str, tolerance: int = RANK_TOLERANCE):
    if rank not in RANKS:
        return None
    idx = RANKS.index(rank)
    start = max(0, idx - tolerance)
    end = min(len(RANKS), idx + tolerance + 1)
    return RANKS[start:end]


async def search_teammates(exclude_id: int, rank: str = None, limit: int = 5):
    rank_list = _rank_range(rank) if rank else None

    async with _pool.acquire() as conn:
        if rank_list:
            rows = await conn.fetch("""
                SELECT * FROM public.users 
                WHERE telegram_id != $1 
                  AND rank = ANY($2::text[])
                ORDER BY RANDOM() 
                LIMIT $3
            """, exclude_id, rank_list, limit)
        else:
            rows = await conn.fetch("""
                SELECT * FROM public.users 
                WHERE telegram_id != $1 
                ORDER BY RANDOM() 
                LIMIT $2
            """, exclude_id, limit)

        return [dict(row) for row in rows]


async def search_team_of_five(exclude_id: int, rank: str = None):
    rank_list = _rank_range(rank) if rank else None

    async with _pool.acquire() as conn:
        if rank_list:
            rows = await conn.fetch("""
                SELECT * FROM public.users 
                WHERE telegram_id != $1 
                  AND rank = ANY($2::text[])
                ORDER BY RANDOM() 
                LIMIT 4
            """, exclude_id, rank_list)
        else:
            rows = await conn.fetch("""
                SELECT * FROM public.users 
                WHERE telegram_id != $1 
                ORDER BY RANDOM() 
                LIMIT 4
            """, exclude_id)

        return [dict(row) for row in rows]