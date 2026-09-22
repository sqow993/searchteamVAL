import asyncio
import logging
import sys

from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, BufferedInputFile

from config import (
    BOT_TOKEN,
    WEBHOOK_URL,
    WEBHOOK_PATH,
    WEBHOOK_SECRET,
    WEBAPP_HOST,
    WEBAPP_PORT,
)
from database import init_db, save_user, get_user, delete_user, search_teammates
from keyboards import main_menu, back_to_menu, teammate_actions
from tracker_api import parse_tracker_url
from screenshot import take_stats_screenshot
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
    waiting_for_url = State()


# ===== Bot и Dispatcher =====
bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()


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
            "⚠️ <b>Для использования нужно привязать профиль Tracker.gg.</b>\n"
            "Так мы гарантируем, что все игроки — реальные.\n\n"
            "Нажми <b>«Привязать Tracker»</b>, чтобы начать."
        )

    await message.answer(text, reply_markup=main_menu())


@dp.message(Command("help"))
async def cmd_help(message: Message):
    text = (
        "📖 <b>Команды:</b>\n\n"
        "/start — главное меню\n"
        "/help — эта справка\n\n"
        "🔗 <b>Как привязать Tracker.gg:</b>\n"
        "1. Открой tracker.gg/valorant\n"
        "2. Найди свой профиль\n"
        "3. Скопируй ссылку из адресной строки\n"
        "4. Отправь её боту\n\n"
        "⚠️ Профиль должен быть <b>публичным</b>."
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
            "⚠️ <b>Для использования нужно привязать профиль Tracker.gg.</b>\n\n"
            "Нажми <b>«Привязать Tracker»</b>, чтобы начать."
        )

    await callback.message.edit_text(text, reply_markup=main_menu())
    await callback.answer()


# ===== Привязка аккаунта =====

@dp.callback_query(F.data == "link_tracker")
async def cb_link_tracker(callback: CallbackQuery, state: FSMContext):
    await state.set_state(LinkStates.waiting_for_url)

    text = (
        "🔗 <b>Привязка Tracker.gg</b>\n\n"
        "Отправь мне ссылку на свой профиль.\n\n"
        "<b>Как получить:</b>\n"
        "1. Открой tracker.gg/valorant\n"
        "2. Найди свой профиль\n"
        "3. Скопируй URL из адресной строки\n\n"
        "Пример:\n"
        "<code>https://tracker.gg/valorant/profile/riot/Player%23TAG/overview</code>\n\n"
        "⚠️ Профиль должен быть <b>публичным</b>."
    )

    await callback.message.edit_text(text, reply_markup=back_to_menu())
    await callback.answer()


@dp.message(LinkStates.waiting_for_url)
async def process_tracker_url(message: Message, state: FSMContext):
    url = message.text.strip()

    riot_id = await parse_tracker_url(url)

    if not riot_id:
        await message.answer(
            "❌ <b>Не удалось распознать ссылку.</b>\n\n"
            "Убедись, что она ведёт на профиль Tracker.gg:\n"
            "<code>https://tracker.gg/valorant/profile/riot/Ник%23ТЕГ/overview</code>",
            reply_markup=back_to_menu()
        )
        return

    # Сохраняем сразу (чтобы не потерять, если скриншот упадёт)
    await save_user(message.from_user.id, riot_id, url)

    processing_msg = await message.answer(
        "⏳ Загружаю статистику с Tracker.gg...\n"
        "Это может занять 15-30 секунд."
    )

    screenshot_io = await take_stats_screenshot(url)

    if screenshot_io:
        photo = BufferedInputFile(
            screenshot_io.read(),
            filename="valorant_stats.png"
        )

        await processing_msg.delete()
        await message.answer_photo(
            photo,
            caption=(
                f"✅ <b>Аккаунт привязан!</b>\n"
                f"👤 Ник: <code>{riot_id}</code>"
            ),
            reply_markup=main_menu()
        )
    else:
        await processing_msg.edit_text(
            "⚠️ <b>Аккаунт сохранён, но скриншот не удалось загрузить.</b>\n\n"
            "Возможные причины:\n"
            "• Профиль не публичный\n"
            "• Cloudflare блокирует запрос\n"
            "• Tracker.gg временно недоступен\n\n"
            "Попробуй позже через «Мой профиль».",
            reply_markup=main_menu()
        )

    await state.clear()


# ===== Мой профиль =====

@dp.callback_query(F.data == "my_profile")
async def cb_my_profile(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)

    if not user:
        await callback.message.edit_text(
            "❌ Ты ещё не привязал аккаунт.\n\n"
            "Нажми <b>«Привязать Tracker»</b>.",
            reply_markup=back_to_menu()
        )
        await callback.answer()
        return

    await callback.message.edit_text("⏳ Загружаю статистику...")
    await callback.answer()

    screenshot_io = await take_stats_screenshot(user["tracker_url"])

    if screenshot_io:
        photo = BufferedInputFile(
            screenshot_io.read(),
            filename="my_stats.png"
        )

        await callback.message.delete()
        await callback.message.answer_photo(
            photo,
            caption=(
                f"👤 <b>Твой профиль</b>\n"
                f"🎯 <code>{user['riot_id']}</code>\n\n"
                f"🔗 <a href='{user['tracker_url']}'>Tracker.gg</a>"
            ),
            reply_markup=back_to_menu()
        )
    else:
        await callback.message.edit_text(
            "⚠️ Не удалось загрузить статистику.\n"
            "Попробуй позже.",
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

    screenshot_io = await take_stats_screenshot(candidate["tracker_url"])

    if screenshot_io:
        photo = BufferedInputFile(
            screenshot_io.read(),
            filename="teammate_stats.png"
        )

        await callback.message.delete()
        await callback.message.answer_photo(
            photo,
            caption=(
                f"👤 <b>Найден тиммейт!</b>\n"
                f"🎯 <code>{candidate['riot_id']}</code>\n\n"
                f"🔗 <a href='{candidate['tracker_url']}'>Tracker.gg</a>"
            ),
            reply_markup=teammate_actions(candidate["telegram_id"])
        )
    else:
        await callback.message.edit_text(
            f"👤 <b>Найден игрок</b>\n\n"
            f"🎯 <code>{candidate['riot_id']}</code>\n"
            f"🔗 <a href='{candidate['tracker_url']}'>Tracker.gg</a>\n\n"
            "⚠️ Не удалось загрузить скриншот.",
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
    """Устанавливает webhook при старте"""
    await init_db()

    webhook_full_url = f"{WEBHOOK_URL}{WEBHOOK_PATH}"
    await bot.set_webhook(
        url=webhook_full_url,
        secret_token=WEBHOOK_SECRET,
        drop_pending_updates=True
    )
    logger.info(f"Webhook установлен: {webhook_full_url}")


async def on_shutdown():
    """Удаляет webhook при остановке"""
    await bot.delete_webhook()
    await bot.session.close()
    logger.info("Бот остановлен")


async def main():
    # Webhook ставим до старта сервера
    await on_startup()

    # Создаём aiohttp-приложение
    app = create_app(bot, dp)

    # Запускаем сервер
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, WEBAPP_HOST, WEBAPP_PORT)
    await site.start()

    logger.info(f"🚀 Сервер запущен на {WEBAPP_HOST}:{WEBAPP_PORT}")

    # Бесконечное ожидание
    try:
        await asyncio.Event().wait()
    finally:
        await on_shutdown()
        await runner.cleanup()


if __name__ == "__main__":
    # На Windows для Playwright нужен SelectorEventLoop
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    asyncio.run(main())