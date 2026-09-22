import aiosqlite
from config import DB_PATH


async def init_db():
    """Создаёт таблицу при первом запуске"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                telegram_id INTEGER PRIMARY KEY,
                riot_id TEXT NOT NULL,
                tracker_url TEXT NOT NULL,
                rank TEXT DEFAULT 'Unranked',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()


async def save_user(telegram_id: int, riot_id: str, tracker_url: str):
    """Сохраняет или обновляет привязку"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO users (telegram_id, riot_id, tracker_url)
            VALUES (?, ?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET
                riot_id = excluded.riot_id,
                tracker_url = excluded.tracker_url
        """, (telegram_id, riot_id, tracker_url))
        await db.commit()


async def get_user(telegram_id: int):
    """Возвращает привязку или None"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def delete_user(telegram_id: int):
    """Удаляет привязку"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM users WHERE telegram_id = ?", (telegram_id,))
        await db.commit()


async def search_teammates(exclude_id: int, limit: int = 5):
    """Ищет других игроков, исключая себя"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT * FROM users 
            WHERE telegram_id != ? 
            ORDER BY RANDOM() 
            LIMIT ?
        """, (exclude_id, limit)) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]