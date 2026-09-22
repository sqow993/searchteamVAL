import aiosqlite
import os
from config import DB_PATH, RANKS, RANK_TOLERANCE


async def init_db():
    """Создаёт таблицу при первом запуске + миграции"""
    print(f"[DB] Инициализация БД: {os.path.abspath(DB_PATH)}")

    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    telegram_id INTEGER PRIMARY KEY,
                    riot_id TEXT NOT NULL,
                    tracker_url TEXT NOT NULL,
                    rank TEXT DEFAULT 'Unranked',
                    bio TEXT DEFAULT '',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.commit()

            # Миграция: добавляем bio, если её нет (для старой БД)
            try:
                await db.execute("ALTER TABLE users ADD COLUMN bio TEXT DEFAULT ''")
                await db.commit()
                print("[DB] Миграция: добавлена колонка bio")
            except Exception:
                pass

        print(f"[DB] Таблица готова. Файл существует: {os.path.exists(DB_PATH)}")

    except Exception as e:
        print(f"[DB] ОШИБКА init_db: {e}")


async def save_user(telegram_id: int, riot_id: str, tracker_url: str,
                    rank: str = "Unranked"):
    """Сохраняет или обновляет привязку пользователя"""
    print(f"[DB] save_user: tg={telegram_id}, riot={riot_id}, rank={rank}")
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                INSERT INTO users (telegram_id, riot_id, tracker_url, rank)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(telegram_id) DO UPDATE SET
                    riot_id = excluded.riot_id,
                    tracker_url = excluded.tracker_url,
                    rank = excluded.rank
            """, (telegram_id, riot_id, tracker_url, rank))
            await db.commit()
        print(f"[DB] save_user OK")
    except Exception as e:
        print(f"[DB] ОШИБКА save_user: {e}")


async def update_bio(telegram_id: int, bio: str):
    """Обновляет описание «Обо мне»"""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE users SET bio = ? WHERE telegram_id = ?",
                (bio, telegram_id)
            )
            await db.commit()
        print(f"[DB] update_bio OK")
    except Exception as e:
        print(f"[DB] ОШИБКА update_bio: {e}")


async def update_rank(telegram_id: int, rank: str):
    """Обновляет ранг"""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE users SET rank = ? WHERE telegram_id = ?",
                (rank, telegram_id)
            )
            await db.commit()
        print(f"[DB] update_rank OK: {rank}")
    except Exception as e:
        print(f"[DB] ОШИБКА update_rank: {e}")


async def get_user(telegram_id: int):
    """Возвращает привязку или None"""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None
    except Exception as e:
        print(f"[DB] ОШИБКА get_user: {e}")
        return None


async def delete_user(telegram_id: int):
    """Удаляет привязку"""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM users WHERE telegram_id = ?", (telegram_id,))
            await db.commit()
    except Exception as e:
        print(f"[DB] ОШИБКА delete_user: {e}")


async def count_users() -> int:
    """Считает всех пользователей"""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT COUNT(*) FROM users") as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0
    except Exception as e:
        print(f"[DB] ОШИБКА count_users: {e}")
        return -1


def _rank_range(rank: str, tolerance: int = RANK_TOLERANCE):
    """Возвращает список рангов ±tolerance от указанного"""
    if rank not in RANKS:
        return None
    idx = RANKS.index(rank)
    start = max(0, idx - tolerance)
    end = min(len(RANKS), idx + tolerance + 1)
    return RANKS[start:end]


async def search_teammates(exclude_id: int, rank: str = None, limit: int = 5):
    """Ищет других игроков с подходящим рангом"""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            rank_list = _rank_range(rank) if rank else None

            if rank_list:
                placeholders = ",".join("?" for _ in rank_list)
                query = f"""
                    SELECT * FROM users 
                    WHERE telegram_id != ? 
                      AND rank IN ({placeholders})
                    ORDER BY RANDOM() 
                    LIMIT ?
                """
                params = [exclude_id] + rank_list + [limit]
            else:
                query = """
                    SELECT * FROM users 
                    WHERE telegram_id != ? 
                    ORDER BY RANDOM() 
                    LIMIT ?
                """
                params = [exclude_id, limit]

            async with db.execute(query, params) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
    except Exception as e:
        print(f"[DB] ОШИБКА search_teammates: {e}")
        return []


async def search_team_of_five(exclude_id: int, rank: str = None):
    """Ищет 4 других игроков для команды"""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            rank_list = _rank_range(rank) if rank else None

            if rank_list:
                placeholders = ",".join("?" for _ in rank_list)
                query = f"""
                    SELECT * FROM users 
                    WHERE telegram_id != ? 
                      AND rank IN ({placeholders})
                    ORDER BY RANDOM() 
                    LIMIT 4
                """
                params = [exclude_id] + rank_list
            else:
                query = """
                    SELECT * FROM users 
                    WHERE telegram_id != ? 
                    ORDER BY RANDOM() 
                    LIMIT 4
                """
                params = [exclude_id]

            async with db.execute(query, params) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
    except Exception as e:
        print(f"[DB] ОШИБКА search_team_of_five: {e}")
        return []