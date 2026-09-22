"""
Настройка aiohttp-приложения для работы через webhook.
"""

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

from config import WEBHOOK_PATH, WEBHOOK_SECRET


async def healthcheck(request: web.Request) -> web.Response:
    """Endpoint для проверки, что бот жив (использует UptimeRobot)"""
    return web.json_response({"status": "ok", "service": "valorant-bot"})


async def root(request: web.Request) -> web.Response:
    """Корневой endpoint — тоже возвращает ok"""
    return web.json_response({"status": "ok"})


def create_app(bot: Bot, dp: Dispatcher) -> web.Application:
    """Создаёт aiohttp-приложение с webhook и healthcheck"""

    app = web.Application()

    # Healthcheck endpoints (для UptimeRobot)
    app.router.add_get("/", root)
    app.router.add_get("/healthcheck", healthcheck)

    # Webhook для Telegram
    webhook_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
        secret_token=WEBHOOK_SECRET,
    )
    webhook_handler.register(app, path=WEBHOOK_PATH)

    # Регистрируем startup/shutdown
    setup_application(app, dp, bot=bot)

    return app