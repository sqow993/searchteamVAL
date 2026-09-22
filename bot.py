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
    init_db, save_user, get_user, delete_user, update_rank, update_profile,
    search_teammates, search_team_of_five, count_users, _rank_range
)
from keyboards import (
    main_menu, back_to_menu, teammate_actions, ranks_keyboard,
    profile_menu, profile_skip_keyboard
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


class ProfileStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_age = State()
    waiting_for_location = State()
    waiting_for_experience = State()


# ===== Bot =====
bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()


# ===== Форматирование карточки игрока =====
def format_profile_card(user: dict, title: str = "👤 Найден тиммейт!") -> str:
    """Формирует карточку игрока с анкетой"""
    rank = user.get("rank", "Unranked")
    rank_range = _rank_range(rank, tolerance=2)
    range_text = f"{rank_range[0]} — {rank_range[-1]}" if rank_range else rank

    lines = [f"<b>{title}</b>\n"]
    lines.append(f"🎯 Riot ID: <code>{user['riot_id']}</code>")
    lines.append(f"🏆 Ранг: <b>{rank}</b> (диапазон поиска: {range_text})")

    # Анкета (только заполненные поля)
    name = user.get("name", "").strip()
    age = user.get("age", 0)
    location = user.get("location", "").strip()
    experience = user.get("experience", "").strip()

    has_profile = name or age or location or experience

    if has_profile:
        lines.append("\n📋 <b>О игроке:</b>")
        if name:
            lines.append(f"• Имя: <b>{name}</b>")
        if age and age > 0:
            lines.append(f"• Возраст: <b>{age}</b>")
        if location:
            lines.append(f"• Откуда: <b>{location}</b>")
        if experience:
            lines.append(f"• Опыт в Valorant: <b>{experience}</b>")
    else:
        lines.append("\n📋 <i>Анкета не заполнена</i>")

    return "\n".join(lines)


# ===== Команды =====

@dp.message(CommandStart())
async def cmd_start(message: Message):
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
        "🔗 <b>Как привязать аккаунт:</b>\n"
        "1. Отправь Riot ID в формате <code>Ник#ТЕГ</code>\n"
        "2. Выбери свой ранг из списка\n"
        "3. Заполни анкету (по желанию)\n\n"
        "🎮 <b>Поиск:</b>\n"
        "Бот ищет игроков в пределах ±2 дивизиона от твоего ранга."
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

    # Предлагаем заполнить анкету
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(text="📝 Заполнить анкету", callback_data="edit_profile")
    builder.button(text="⏭ Пропустить", callback_data="main_menu")
    builder.adjust(1, 1)

    text = (
        f"✅ <b>Аккаунт привязан!</b>\n\n"
        f"🎯 Riot ID: <code>{riot_id}</code>\n"
        f"🏆 Ранг: <b>{rank}</b>\n"
        f"🔍 Диапазон поиска: <b>{range_text}</b>\n\n"
        f"Хочешь заполнить анкету о себе?\n"
        f"Это поможет другим игрокам узнать тебя лучше."
    )

    await state.clear()
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
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

    encoded = urllib.parse.quote(user["riot_id"], safe="")
    tracker_url = f"https://tracker.gg/valorant/profile/riot/{encoded}/overview"

    rank = user.get("rank", "Unranked")
    rank_range = _rank_range(rank, tolerance=2)
    range_text = f"{rank_range[0]} — {rank_range[-1]}" if rank_range else rank

    text = f"👤 <b>Твой профиль</b>\n\n"
    text += f"🎯 Riot ID: <code>{user['riot_id']}</code>\n"
    text += f"🏆 Ранг: <b>{rank}</b>\n"
    text += f"🔍 Диапазон поиска: <b>{range_text}</b>\n"

    # Анкета
    name = user.get("name", "").strip()
    age = user.get("age", 0)
    location = user.get("location", "").strip()
    experience = user.get("experience", "").strip()

    text += "\n📋 <b>Анкета:</b>\n"
    if name:
        text += f"• Имя: <b>{name}</b>\n"
    if age and age > 0:
        text += f"• Возраст: <b>{age}</b>\n"
    if location:
        text += f"• Откуда: <b>{location}</b>\n"
    if experience:
        text += f"• Опыт: <b>{experience}</b>\n"

    if not any([name, age, location, experience]):
        text += "<i>не заполнена</i>\n"

    text += f"\n🔗 <a href='{tracker_url}'>Открыть на Tracker.gg</a>"

    await callback.message.edit_text(
        text,
        reply_markup=profile_menu(),
        disable_web_page_preview=True
    )
    await callback.answer()


# ===== Редактирование анкеты: шаг 1 — Имя =====

@dp.callback_query(F.data == "edit_profile")
async def cb_edit_profile(callback: CallbackQuery, state: FSMContext):
    user = await get_user(callback.from_user.id)
    if not user:
        await callback.answer("Сначала привяжи аккаунт", show_alert=True)
        return

    await state.set_state(ProfileStates.waiting_for_name)

    text = (
        "📝 <b>Заполнение анкеты</b>\n\n"
        "Шаг 1/4: <b>Как тебя зовут?</b>\n\n"
        "Напиши своё имя или ник (например, <i>Александр</i> или <i>Sasha</i>).\n\n"
        "Или нажми «Пропустить»."
    )

    await callback.message.edit_text(text, reply_markup=profile_skip_keyboard())
    await callback.answer()


@dp.message(ProfileStates.waiting_for_name)
async def profile_name(message: Message, state: FSMContext):
    name = message.text.strip()[:50]
    await state.update_data(name=name)
    await state.set_state(ProfileStates.waiting_for_age)

    await message.answer(
        f"✅ Имя: <b>{name}</b>\n\n"
        "Шаг 2/4: <b>Сколько тебе лет?</b>\n\n"
        "Напиши число (например, <i>18</i>).",
        reply_markup=profile_skip_keyboard()
    )


# ===== Шаг 2 — Возраст =====

@dp.message(ProfileStates.waiting_for_age)
async def profile_age(message: Message, state: FSMContext):
    text = message.text.strip()

    if not text.isdigit():
        await message.answer(
            "❌ Возраст должен быть числом. Попробуй ещё раз:",
            reply_markup=profile_skip_keyboard()
        )
        return

    age = int(text)
    if age < 5 or age > 100:
        await message.answer(
            "❌ Возраст должен быть от 5 до 100. Попробуй ещё раз:",
            reply_markup=profile_skip_keyboard()
        )
        return

    await state.update_data(age=age)
    await state.set_state(ProfileStates.waiting_for_location)

    await message.answer(
        f"✅ Возраст: <b>{age}</b>\n\n"
        "Шаг 3/4: <b>Откуда ты?</b>\n\n"
        "Напиши город или страну (например, <i>Москва</i> или <i>Казахстан</i>).",
        reply_markup=profile_skip_keyboard()
    )


# ===== Шаг 3 — Локация =====

@dp.message(ProfileStates.waiting_for_location)
async def profile_location(message: Message, state: FSMContext):
    location = message.text.strip()[:50]
    await state.update_data(location=location)
    await state.set_state(ProfileStates.waiting_for_experience)

    await message.answer(
        f"✅ Откуда: <b>{location}</b>\n\n"
        "Шаг 4/4: <b>Сколько играешь в Valorant?</b>\n\n"
        "Напиши свой опыт (например, <i>2 года</i>, <i>с беты</i>, <i>3 месяца</i>).",
        reply_markup=profile_skip_keyboard()
    )


# ===== Шаг 4 — Опыт =====

@dp.message(ProfileStates.waiting_for_experience)
async def profile_experience(message: Message, state: FSMContext):
    experience = message.text.strip()[:50]
    await state.update_data(experience=experience)

    # Сохраняем всё
    data = await state.get_data()
    await update_profile(
        message.from_user.id,
        data.get("name", ""),
        data.get("age", 0),
        data.get("location", ""),
        experience
    )

    await state.clear()

    text = (
        "✅ <b>Анкета сохранена!</b>\n\n"
        f"📋 <b>Твои данные:</b>\n"
        f"• Имя: <b>{data.get('name', '—')}</b>\n"
        f"• Возраст: <b>{data.get('age', '—')}</b>\n"
        f"• Откуда: <b>{data.get('location', '—')}</b>\n"
        f"• Опыт: <b>{experience}</b>\n\n"
        f"Теперь другие игроки увидят это при поиске."
    )

    await message.answer(text, reply_markup=main_menu())


# ===== Пропуск поля =====

@dp.callback_query(F.data == "skip_field")
async def cb_skip_field(callback: CallbackQuery, state: FSMContext):
    current = await state.get_state()

    if current == ProfileStates.waiting_for_name:
        await state.set_state(ProfileStates.waiting_for_age)
        await callback.message.edit_text(
            "⏭ Имя пропущено.\n\n"
            "Шаг 2/4: <b>Сколько тебе лет?</b>\n"
            "Напиши число или пропусти.",
            reply_markup=profile_skip_keyboard()
        )
    elif current == ProfileStates.waiting_for_age:
        await state.set_state(ProfileStates.waiting_for_location)
        await callback.message.edit_text(
            "⏭ Возраст пропущен.\n\n"
            "Шаг 3/4: <b>Откуда ты?</b>\n"
            "Напиши город/страну или пропусти.",
            reply_markup=profile_skip_keyboard()
        )
    elif current == ProfileStates.waiting_for_location:
        await state.set_state(ProfileStates.waiting_for_experience)
        await callback.message.edit_text(
            "⏭ Локация пропущена.\n\n"
            "Шаг 4/4: <b>Сколько играешь в Valorant?</b>\n"
            "Напиши опыт или пропусти.",
            reply_markup=profile_skip_keyboard()
        )
    elif current == ProfileStates.waiting_for_experience:
        # Финальный шаг — сохраняем что есть
        data = await state.get_data()
        await update_profile(
            callback.from_user.id,
            data.get("name", ""),
            data.get("age", 0),
            data.get("location", ""),
            ""
        )
        await state.clear()
        await callback.message.edit_text(
            "✅ Анкета сохранена!",
            reply_markup=main_menu()
        )

    await callback.answer()


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

    # Формируем карточки для каждого
    lines = ["🎮 <b>Команда собрана!</b>\n"]

    # Ты
    lines.append("━━━━━━━━━━━━━━━")
    lines.append("👑 <b>Ты</b>")
    lines.append(f"🎯 <code>{me['riot_id']}</code>")
    lines.append(f"🏆 {me.get('rank', '?')}")
    if me.get("name"):
        lines.append(f"• {me['name']}, {me.get('age', '?')} лет, {me.get('location', '?')}")

    # Остальные
    for i, c in enumerate(candidates, start=1):
        lines.append("━━━━━━━━━━━━━━━")
        lines.append(f"👤 <b>Игрок {i}</b>")
        lines.append(f"🎯 <code>{c['riot_id']}</code>")
        lines.append(f"🏆 {c.get('rank', '?')}")
        if c.get("name"):
            lines.append(f"• {c['name']}, {c.get('age', '?')} лет, {c.get('location', '?')}")
        if c.get("experience"):
            lines.append(f"• Опыт: {c['experience']}")

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