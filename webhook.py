from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

from config import WEBHOOK_PATH, WEBHOOK_SECRET


async def healthcheck(request: web.Request) -> web.Response:
    return web.json_response({"status": "ok", "service": "valorant-bot"})


async def root(request: web.Request) -> web.Response:
    return web.json_response({"status": "ok"})


def create_app(bot: Bot, dp: Dispatcher) -> web.Application:
    app = web.Application()

    app.router.add_get("/", root)
    app.router.get("/healthcheck", healthcheck) if False else app.router.add_get("/healthcheck", healthcheck)

    webhook_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
        secret_token=WEBHOOK_SECRET,
    )
    webhook_handler.register(app, path=WEBHOOK_PATH)

    setup_application(app, dp, bot=bot)
    return app