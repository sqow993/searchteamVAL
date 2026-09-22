from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

from config import WEBHOOK_PATH, WEBHOOK_SECRET


async def healthcheck(request: web.Request) -> web.Response:
    """Проверка, что сервис жив (использует UptimeRobot)"""
    return web.json_response({"status": "ok", "service": "valorant-bot"})


async def root(request: web.Request) -> web.Response:
    """Корневой endpoint"""
    return web.json_response({"status": "ok"})


def create_app(bot: Bot, dp: Dispatcher) -> web.Application:
    """Создаёт aiohttp-приложение с webhook и healthcheck"""
    app = web.Application()

    # Healthcheck endpoints
    app.router.add_get("/", root)
    app.router.add_get("/healthcheck", healthcheck)

    # Webhook от Telegram
    # handle_in_background=True — бот сразу отвечает Telegram "200 OK",
    # а обработку сообщения делает в фоне. Это решает проблему Read timeout.
    webhook_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
        secret_token=WEBHOOK_SECRET,
        handle_in_background=True,
    )
    webhook_handler.register(app, path=WEBHOOK_PATH)

    # Регистрируем startup/shutdown
    setup_application(app, dp, bot=bot)

    return app