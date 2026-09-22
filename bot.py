import asyncio
import logging
import sys
import os

from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery

from config import (
    BOT_TOKEN,
    WEBHOOK_URL,
    WEBHOOK_PATH,
    WEBHOOK_SECRET,
    WEBAPP_HOST,
    WEBAPP_PORT,
    DB_PATH,
)
from database import init_db, save_user, get_user, delete_user, search_teammates
from keyboards import main_menu, back_to_menu, teammate_actions
from tracker_api import get_player_stats
from webhook import create_app


# ===== Логирование =====
logging.basicConfig(
    level=logging.INFO,
    stream=sys.stdout,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


# ===== Состояния FSM =====
class LinkStates(StatesGroup):
    waiting_for_riot_id = State()


# ===== Bot и Dispatcher =====
bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()


# ===== Форматирование статистики =====
def format_stats_text(stats: dict) -> str:
    """Формирует красивое сообщение со статистикой игрока"""
    matches = stats.get("last_matches", [])

    if not matches:
        matches_text = "нет данных"
        winrate = 0
        kda_text = "нет данных"
    else:
        lines = []
        for m in matches:
            result = "✅" if m.get("result") == "W" else "❌"
            k = m.get("kills", 0)
            d = m.get("deaths", 0)
            a = m.get("assists", 0)
            agent = m.get("agent", "?")
            lines.append(f"{result} <code>{k}/{d}/{a}</code> — {agent}")
        matches_text = "\n".join(lines)

        wins = sum(1 for m in matches if m.get("result") == "W")
        total = len(matches)
        winrate = round(wins / total * 100, 1) if total > 0 else 0

        avg_kills = round(sum(m.get("kills", 0) for m in matches) / total, 1)
        avg_deaths = round(sum(m.get("deaths", 0) for m in matches) / total, 1)
        avg_assists = round(sum(m.get("assists", 0) for m in matches) / total, 1)
        kda_text = f"{avg_kills} / {avg_deaths} / {avg_assists}"

    text = (
        f"👤 <b>{stats.get('name', 'Unknown')}</b>\n\n"
        f"📊 <b>Средний KDA:</b> {kda_text}\n"
        f"🏆 <b>Winrate (5 игр):</b> {winrate}%\n\n"
        f"🎮 <b>Последние 5 игр:</b>\n{matches_text}"
    )

    return text


# ===== Команды =====

@dp.message(CommandStart())
async def cmd_start(message: Message):
    user = await get_user(message.from_user.id)

    if user:
        text = (
            f"👋 С возвращением, {message.from_user.full_name}!\n\n"
            f"Твой аккаунт привязан: <code>{user['riot_id']}</code>\n"
            f"Выбери действие:"
        )
    else:
        text = (
            f"👋 Привет, {message.from_user.full_name}!\n\n"
            "🎮 Это бот для поиска тиммейтов в <b>Valorant</b>.\n\n"
            "⚠️ <b>Для использования нужно привязать Riot ID.</b>\n"
            "Так мы гарантируем, что все игроки — реальные.\n\n"
            "Нажми <b>«Привязать аккаунт»</b>, чтобы начать."
        )

    await message.answer(text, reply_markup=main_menu())


@dp.message(Command("help"))
async def cmd_help(message: Message):
    text = (
        "📖 <b>Команды:</b>\n\n"
        "/start — главное меню\n"
        "/help — эта справка\n\n"
        "🔗 <b>Как привязать аккаунт:</b>\n"
        "Отправь боту свой Riot ID в формате:\n"
        "<code>Ник#ТЕГ</code>\n\n"
        "Пример:\n"
        "<code>Player#EUW</code>\n\n"
        "⚠️ Ник должен быть точным, включая регистр."
    )
    await message.answer(text)


# ===== Callback: главное меню =====

@dp.callback_query(F.data == "main_menu")
async def cb_main_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    user = await get_user(callback.from_user.id)

    if user:
        text = (
            f"👋 С возвращением, {callback.from_user.full_name}!\n\n"
            f"Твой аккаунт привязан: <code>{user['riot_id']}</code>\n"
            f"Выбери действие:"
        )
    else:
        text = (
            f"👋 Привет, {callback.from_user.full_name}!\n\n"
            "🎮 Это бот для поиска тиммейтов в <b>Valorant</b>.\n\n"
            "⚠️ <b>Для использования нужно привязать Riot ID.</b>\n\n"
            "Нажми <b>«Привязать аккаунт»</b>, чтобы начать."
        )

    await callback.message.edit_text(text, reply_markup=main_menu())
    await callback.answer()


# ===== Привязка аккаунта =====

@dp.callback_query(F.data == "link_tracker")
async def cb_link_tracker(callback: CallbackQuery, state: FSMContext):
    await state.set_state(LinkStates.waiting_for_riot_id)

    text = (
        "🔗 <b>Привязка Riot ID</b>\n\n"
        "Отправь мне свой Riot ID в формате:\n"
        "<code>Ник#ТЕГ</code>\n\n"
        "<b>Примеры:</b>\n"
        "<code>Player#EUW</code>\n"
        "<code>из грязи в князи#GAVNO</code>\n\n"
        "⚠️ Ник должен быть точным, включая регистр и пробелы.\n"
        "Если не знаешь свой тег — посмотри в клиенте Valorant."
    )

    await callback.message.edit_text(text, reply_markup=back_to_menu())
    await callback.answer()


@dp.message(LinkStates.waiting_for_riot_id)
async def process_riot_id(message: Message, state: FSMContext):
    riot_id = message.text.strip()

    if "#" not in riot_id:
        await message.answer(
            "❌ <b>Неверный формат.</b>\n\n"
            "Riot ID должен содержать <code>#</code>:\n"
            "<code>Ник#ТЕГ</code>\n\n"
            "Пример: <code>Player#EUW</code>",
            reply_markup=back_to_menu()
        )
        return

    processing_msg = await message.answer(
        "⏳ Загружаю статистику с Riot API...\n"
        "Это может занять 10-20 секунд."
    )

    stats = await get_player_stats(riot_id)

    if stats:
        await save_user(message.from_user.id, riot_id, f"riot:{riot_id}")

        text = f"✅ <b>Аккаунт привязан!</b>\n\n{format_stats_text(stats)}"

        await processing_msg.delete()
        await message.answer(text, reply_markup=main_menu())
    else:
        await processing_msg.edit_text(
            "❌ <b>Не удалось получить статистику.</b>\n\n"
            "Возможные причины:\n"
            "• Неверный Riot ID (проверь регистр)\n"
            "• Аккаунт не существует в этом регионе\n"
            "• API ключ истёк (обновляется каждые 24ч)\n"
            "• Riot API временно недоступен\n\n"
            "Попробуй позже или проверь данные.",
            reply_markup=back_to_menu()
        )

    await state.clear()


# ===== Мой профиль =====

@dp.callback_query(F.data == "my_profile")
async def cb_my_profile(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)

    if not user:
        await callback.message.edit_text(
            "❌ Ты ещё не привязал аккаунт.\n\n"
            "Нажми <b>«Привязать аккаунт»</b>.",
            reply_markup=back_to_menu()
        )
        await callback.answer()
        return

    await callback.message.edit_text("⏳ Загружаю статистику...")
    await callback.answer()

    stats = await get_player_stats(user["riot_id"])

    if stats:
        text = f"👤 <b>Твой профиль</b>\n\n{format_stats_text(stats)}"
        await callback.message.delete()
        await callback.message.answer(text, reply_markup=back_to_menu())
    else:
        await callback.message.edit_text(
            "⚠️ Не удалось загрузить статистику.\n"
            "Попробуй позже (возможно, API ключ истёк).",
            reply_markup=back_to_menu()
        )


# ===== Поиск тиммейта =====

@dp.callback_query(F.data == "find_teammate")
async def cb_find_teammate(callback: CallbackQuery):
    me = await get_user(callback.from_user.id)

    if not me:
        await callback.message.edit_text(
            "⚠️ <b>Сначала привяжи свой аккаунт!</b>",
            reply_markup=back_to_menu()
        )
        await callback.answer()
        return

    candidates = await search_teammates(callback.from_user.id, limit=1)

    if not candidates:
        await callback.message.edit_text(
            "😔 Пока нет других игроков в базе.\n\n"
            "Пригласи друзей или заходи позже!",
            reply_markup=back_to_menu()
        )
        await callback.answer()
        return

    candidate = candidates[0]

    await callback.message.edit_text("⏳ Загружаю профиль тиммейта...")
    await callback.answer()

    stats = await get_player_stats(candidate["riot_id"])

    if stats:
        text = f"👤 <b>Найден тиммейт!</b>\n\n{format_stats_text(stats)}"
        await callback.message.delete()
        await callback.message.answer(
            text,
            reply_markup=teammate_actions(candidate["telegram_id"])
        )
    else:
        await callback.message.edit_text(
            f"👤 <b>Найден игрок</b>\n\n"
            f"🎯 <code>{candidate['riot_id']}</code>\n\n"
            "⚠️ Не удалось загрузить статистику.",
            reply_markup=teammate_actions(candidate["telegram_id"])
        )


# ===== Отвязка =====

@dp.callback_query(F.data == "unlink")
async def cb_unlink(callback: CallbackQuery):
    await delete_user(callback.from_user.id)

    await callback.message.edit_text(
        "✅ Аккаунт отвязан.\n\n"
        "Привяжи снова, чтобы искать тиммейтов.",
        reply_markup=back_to_menu()
    )
    await callback.answer()


# ===== Запуск =====

async def on_startup():
    """Инициализация БД и установка webhook"""
    await init_db()

    # Проверка БД
    logger.info(f"[STARTUP] DB_PATH = {os.path.abspath(DB_PATH)}")
    logger.info(f"[STARTUP] Файл существует: {os.path.exists(DB_PATH)}")

    webhook_full_url = f"{WEBHOOK_URL}{WEBHOOK_PATH}"
    await bot.set_webhook(
        url=webhook_full_url,
        secret_token=WEBHOOK_SECRET,
        drop_pending_updates=True
    )
    logger.info(f"Webhook установлен: {webhook_full_url}")


async def on_shutdown():
    await bot.delete_webhook()
    await bot.session.close()
    logger.info("Бот остановлен")


async def main():
    await on_startup()

    app = create_app(bot, dp)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, WEBAPP_HOST, WEBAPP_PORT)
    await site.start()

    logger.info(f"🚀 Сервер запущен на {WEBAPP_HOST}:{WEBAPP_PORT}")

    try:
        await asyncio.Event().wait()
    finally:
        await on_shutdown()
        await runner.cleanup()


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    asyncio.run(main())