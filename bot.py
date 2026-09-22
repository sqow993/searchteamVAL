import asyncio
import logging
import sys
import os
import urllib.parse

from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery

from config import (
    BOT_TOKEN, WEBHOOK_URL, WEBHOOK_PATH, WEBHOOK_SECRET,
    WEBAPP_HOST, WEBAPP_PORT, DB_PATH, RANKS,
)
from database import (
    init_db, save_user, get_user, delete_user, update_rank, update_bio,
    search_teammates, search_team_of_five, count_users, _rank_range
)
from keyboards import (
    main_menu, back_to_menu, teammate_actions, ranks_keyboard,
    after_link_keyboard, profile_menu
)
from webhook import create_app


logging.basicConfig(
    level=logging.INFO,
    stream=sys.stdout,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


# ===== Состояния FSM =====
class LinkStates(StatesGroup):
    waiting_for_riot_id = State()
    waiting_for_rank = State()


class BioStates(StatesGroup):
    waiting_for_bio = State()


# ===== Bot =====
bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()


# ===== Форматирование карточки игрока =====
def format_profile_card(user: dict, title: str = "👤 Найден тиммейт!") -> str:
    """Карточка игрока: Riot ID, ранг, «Обо мне»"""
    rank = user.get("rank", "Unranked")
    rank_range = _rank_range(rank, tolerance=2)
    range_text = f"{rank_range[0]} — {rank_range[-1]}" if rank_range else rank

    bio = (user.get("bio") or "").strip()

    lines = [f"<b>{title}</b>\n"]
    lines.append(f"🎯 Riot ID: <code>{user['riot_id']}</code>")
    lines.append(f"🏆 Ранг: <b>{rank}</b>")
    lines.append(f"🔍 Ищет в диапазоне: {range_text}")

    if bio:
        lines.append(f"\n📝 <b>Обо мне:</b>\n<i>{bio}</i>")
    else:
        lines.append("\n📝 <i>«Обо мне» не заполнено</i>")

    return "\n".join(lines)


# ===== Команды =====

@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user = await get_user(message.from_user.id)

    if user:
        text = (
            f"👋 С возвращением, {message.from_user.full_name}!\n\n"
            f"🎯 Riot ID: <code>{user['riot_id']}</code>\n"
            f"🏆 Ранг: <b>{user.get('rank', 'Unranked')}</b>\n\n"
            f"Выбери действие:"
        )
    else:
        text = (
            f"👋 Привет, {message.from_user.full_name}!\n\n"
            "🎮 Это бот для поиска тиммейтов в <b>Valorant</b>.\n\n"
            "⚠️ <b>Для использования нужно указать Riot ID и ранг.</b>\n\n"
            "Нажми <b>«Привязать аккаунт»</b>, чтобы начать."
        )

    await message.answer(text, reply_markup=main_menu())


@dp.message(Command("help"))
async def cmd_help(message: Message):
    text = (
        "📖 <b>Команды:</b>\n\n"
        "/start — главное меню\n"
        "/help — эта справка\n"
        "/stats — сколько игроков в базе\n\n"
        "🔗 <b>Привязка:</b>\n"
        "1. Отправь Riot ID в формате <code>Ник#ТЕГ</code>\n"
        "2. Выбери ранг\n"
        "3. Заполни «Обо мне» (по желанию)\n\n"
        "🎮 <b>Поиск:</b> бот ищет игроков в пределах ±2 дивизиона от твоего ранга."
    )
    await message.answer(text)


@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    total = await count_users()
    await message.answer(f"👥 Игроков в базе: <b>{total}</b>")


# ===== Главное меню =====

@dp.callback_query(F.data == "main_menu")
async def cb_main_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    user = await get_user(callback.from_user.id)

    if user:
        text = (
            f"👋 С возвращением, {callback.from_user.full_name}!\n\n"
            f"🎯 Riot ID: <code>{user['riot_id']}</code>\n"
            f"🏆 Ранг: <b>{user.get('rank', 'Unranked')}</b>\n\n"
            f"Выбери действие:"
        )
    else:
        text = (
            f"👋 Привет, {callback.from_user.full_name}!\n\n"
            "🎮 Это бот для поиска тиммейтов в <b>Valorant</b>.\n\n"
            "⚠️ <b>Для использования нужно указать Riot ID и ранг.</b>\n\n"
            "Нажми <b>«Привязать аккаунт»</b>, чтобы начать."
        )

    await callback.message.edit_text(text, reply_markup=main_menu())
    await callback.answer()


# ===== Привязка: шаг 1 — Riot ID =====

@dp.callback_query(F.data == "link_tracker")
async def cb_link_tracker(callback: CallbackQuery, state: FSMContext):
    await state.set_state(LinkStates.waiting_for_riot_id)

    text = (
        "🔗 <b>Шаг 1/2: Riot ID</b>\n\n"
        "Отправь мне свой Riot ID в формате:\n"
        "<code>Ник#ТЕГ</code>\n\n"
        "<b>Примеры:</b>\n"
        "<code>Player#EUW</code>\n"
        "<code>из грязи в князи#GAVNO</code>"
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
            "<code>Ник#ТЕГ</code>",
            reply_markup=back_to_menu()
        )
        return

    if len(riot_id) < 3 or len(riot_id) > 50:
        await message.answer("❌ Слишком короткий или длинный Riot ID.")
        return

    await state.update_data(riot_id=riot_id)
    await state.set_state(LinkStates.waiting_for_rank)

    text = (
        f"✅ Riot ID: <code>{riot_id}</code>\n\n"
        "🔗 <b>Шаг 2/2: Ранг</b>\n\n"
        "Выбери свой текущий ранг в Valorant."
    )

    await message.answer(text, reply_markup=ranks_keyboard())


# ===== Привязка: шаг 2 — Ранг =====

@dp.callback_query(F.data.startswith("set_rank:"), LinkStates.waiting_for_rank)
async def cb_set_rank(callback: CallbackQuery, state: FSMContext):
    rank = callback.data.split(":", 1)[1]

    if rank not in RANKS:
        await callback.answer("❌ Неизвестный ранг", show_alert=True)
        return

    data = await state.get_data()
    riot_id = data.get("riot_id")

    if not riot_id:
        await callback.message.edit_text(
            "❌ Что-то пошло не так. Начни заново.",
            reply_markup=back_to_menu()
        )
        await state.clear()
        await callback.answer()
        return

    encoded = urllib.parse.quote(riot_id, safe="")
    tracker_url = f"https://tracker.gg/valorant/profile/riot/{encoded}/overview"

    await save_user(callback.from_user.id, riot_id, tracker_url, rank)

    rank_range = _rank_range(rank, tolerance=2)
    range_text = f"{rank_range[0]} — {rank_range[-1]}" if rank_range else rank

    text = (
        f"✅ <b>Аккаунт привязан!</b>\n\n"
        f"🎯 Riot ID: <code>{riot_id}</code>\n"
        f"🏆 Ранг: <b>{rank}</b>\n"
        f"🔍 Диапазон поиска: <b>{range_text}</b>\n\n"
        f"Хочешь рассказать о себе?\n"
        f"Например: <i>«Меня зовут Егор, играю с 2024 года, "
        f"активно начал в этом году, хочу найти тиммейта чтобы закеррил катку»</i>"
    )

    await state.clear()
    await callback.message.edit_text(text, reply_markup=after_link_keyboard())
    await callback.answer("Ранг сохранён!")


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

    text = format_profile_card(user, title="👤 Твой профиль")
    text += "\n\n💡 Чтобы изменить данные — используй кнопки ниже."

    await callback.message.edit_text(
        text,
        reply_markup=profile_menu(),
        disable_web_page_preview=True
    )
    await callback.answer()


# ===== Заполнение «Обо мне» =====

@dp.callback_query(F.data == "edit_bio")
async def cb_edit_bio(callback: CallbackQuery, state: FSMContext):
    user = await get_user(callback.from_user.id)
    if not user:
        await callback.answer("Сначала привяжи аккаунт", show_alert=True)
        return

    current_bio = (user.get("bio") or "").strip()
    current_text = f"\n\nСейчас: <i>{current_bio}</i>" if current_bio else ""

    await state.set_state(BioStates.waiting_for_bio)

    text = (
        "📝 <b>Обо мне</b>\n\n"
        "Напиши пару слов о себе. Что угодно:\n"
        "• Как зовут\n"
        "• Сколько играешь\n"
        "• Кого ищешь в тиммейты\n"
        "• Свои цели в игре\n\n"
        f"<b>Пример:</b>\n"
        f"<i>«Меня зовут Егор, играю с 2024 года, активно начал в этом году, "
        f"хочу найти тиммейта чтобы закеррил катку :)»</i>\n\n"
        f"Максимум 300 символов.{current_text}"
    )

    await callback.message.edit_text(text, reply_markup=back_to_menu())
    await callback.answer()


@dp.message(BioStates.waiting_for_bio)
async def process_bio(message: Message, state: FSMContext):
    bio = message.text.strip()

    if len(bio) > 300:
        await message.answer(
            f"❌ Слишком длинно ({len(bio)} символов). Максимум 300.\n"
            "Сократи и отправь ещё раз."
        )
        return

    if len(bio) < 3:
        await message.answer(
            "❌ Слишком коротко. Напиши хотя бы пару слов."
        )
        return

    await update_bio(message.from_user.id, bio)
    await state.clear()

    user = await get_user(message.from_user.id)
    text = "✅ <b>«Обо мне» сохранено!</b>\n\n" + format_profile_card(user, "👤 Твой профиль")

    await message.answer(
        text,
        reply_markup=profile_menu(),
        disable_web_page_preview=True
    )


# ===== Изменение ранга =====

@dp.callback_query(F.data == "change_rank")
async def cb_change_rank(callback: CallbackQuery, state: FSMContext):
    user = await get_user(callback.from_user.id)
    if not user:
        await callback.answer("Сначала привяжи аккаунт", show_alert=True)
        return

    await state.set_state(LinkStates.waiting_for_rank)
    await state.update_data(riot_id=user["riot_id"])

    await callback.message.edit_text(
        "🏆 <b>Выбери новый ранг:</b>",
        reply_markup=ranks_keyboard()
    )
    await callback.answer()


# ===== Поиск 1 тиммейта =====

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

    my_rank = me.get("rank", "Unranked")

    if my_rank not in RANKS:
        await callback.message.edit_text(
            "⚠️ У тебя не выбран ранг. Укажи его в профиле.",
            reply_markup=back_to_menu()
        )
        await callback.answer()
        return

    candidates = await search_teammates(
        callback.from_user.id, rank=my_rank, limit=1
    )

    if not candidates:
        await callback.message.edit_text(
            f"😔 Пока нет игроков рядом с рангом <b>{my_rank}</b>.\n\n"
            f"👥 Всего в базе: <b>{await count_users()}</b>",
            reply_markup=back_to_menu()
        )
        await callback.answer()
        return

    candidate = candidates[0]
    text = format_profile_card(candidate)

    await callback.message.edit_text(
        text,
        reply_markup=teammate_actions(candidate["telegram_id"]),
        disable_web_page_preview=True
    )
    await callback.answer()


# ===== Поиск команды из 5 =====

@dp.callback_query(F.data == "find_team")
async def cb_find_team(callback: CallbackQuery):
    me = await get_user(callback.from_user.id)

    if not me:
        await callback.message.edit_text(
            "⚠️ <b>Сначала привяжи свой аккаунт!</b>",
            reply_markup=back_to_menu()
        )
        await callback.answer()
        return

    my_rank = me.get("rank", "Unranked")

    if my_rank not in RANKS:
        await callback.message.edit_text(
            "⚠️ Сначала укажи ранг в профиле.",
            reply_markup=back_to_menu()
        )
        await callback.answer()
        return

    candidates = await search_team_of_five(callback.from_user.id, rank=my_rank)

    if not candidates:
        await callback.message.edit_text(
            f"😔 Недостаточно игроков рядом с рангом <b>{my_rank}</b>.\n\n"
            f"👥 Всего в базе: <b>{await count_users()}</b>",
            reply_markup=back_to_menu()
        )
        await callback.answer()
        return

    lines = ["🎮 <b>Команда собрана!</b>\n"]

    lines.append("━━━━━━━━━━━━━━━")
    lines.append("👑 <b>Ты</b>")
    lines.append(f"🎯 <code>{me['riot_id']}</code>")
    lines.append(f"🏆 {me.get('rank', '?')}")
    if me.get("bio"):
        lines.append(f"📝 <i>{me['bio']}</i>")

    for i, c in enumerate(candidates, start=1):
        lines.append("━━━━━━━━━━━━━━━")
        lines.append(f"👤 <b>Игрок {i}</b>")
        lines.append(f"🎯 <code>{c['riot_id']}</code>")
        lines.append(f"🏆 {c.get('rank', '?')}")
        if c.get("bio"):
            lines.append(f"📝 <i>{c['bio']}</i>")

    text = "\n".join(lines)
    text += "\n\n💬 Добавляйтесь в друзья и играйте!"

    await callback.message.edit_text(
        text,
        reply_markup=back_to_menu(),
        disable_web_page_preview=True
    )
    await callback.answer()


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
    await init_db()
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