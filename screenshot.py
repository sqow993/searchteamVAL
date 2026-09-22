"""
Скриншот профиля Tracker.gg через Playwright.
Ждём обхода Cloudflare перед скриншотом.
"""

import io
import asyncio
from PIL import Image
from playwright.async_api import async_playwright


# Признаки Cloudflare-заглушки
CLOUDFLARE_MARKERS = [
    "Performing security verification",
    "Just a moment",
    "Checking your browser",
    "Verify you are human",
    "cloudflare",
]

# Признаки того, что реальный профиль загрузился
PROFILE_MARKERS = [
    "Rating",
    "Damage/Round",
    "K/D Ratio",
    "Tracker Score",
    "Win %",
]


async def _is_cloudflare_page(page) -> bool:
    """Проверяет, показывает ли страница Cloudflare-заглушку"""
    try:
        content = await page.content()
        content_lower = content.lower()
        return any(marker.lower() in content_lower for marker in CLOUDFLARE_MARKERS)
    except Exception:
        return False


async def _is_profile_loaded(page) -> bool:
    """Проверяет, загрузился ли реальный профиль"""
    try:
        content = await page.content()
        # Проверяем, что нет Cloudflare
        if await _is_cloudflare_page(page):
            return False
        # Ищем маркеры профиля
        return any(marker in content for marker in PROFILE_MARKERS)
    except Exception:
        return False


async def take_stats_screenshot(tracker_url: str) -> io.BytesIO | None:
    """
    Открывает Tracker.gg и возвращает скриншот верхней части страницы.
    Ждёт обхода Cloudflare и загрузки реального контента.
    """

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-gpu",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
            ]
        )

        context = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            locale="en-US",
            timezone_id="Europe/Moscow",
        )

        # Скрываем признаки автоматизации
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en', 'ru']
            });
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
            window.chrome = { runtime: {} };
        """)

        page = await context.new_page()

        try:
            print(f"[SCREENSHOT] Открываю: {tracker_url}")
            await page.goto(
                tracker_url,
                wait_until="domcontentloaded",
                timeout=60000
            )

            # Ждём обхода Cloudflare (до 60 секунд)
            max_wait = 60
            waited = 0
            step = 3

            while waited < max_wait:
                if await _is_profile_loaded(page):
                    print(f"[SCREENSHOT] Профиль загрузился за {waited} сек")
                    break

                if await _is_cloudflare_page(page):
                    print(f"[SCREENSHOT] Cloudflare проверяет... ({waited}с)")
                else:
                    print(f"[SCREENSHOT] Страница грузится... ({waited}с)")

                await page.wait_for_timeout(step * 1000)
                waited += step
            else:
                print("[SCREENSHOT] Таймаут: Cloudflare не пропустил")
                # Всё равно пробуем сделать скриншот
                # (иногда Cloudflare пропускает чуть позже)

            # Даём время на финальную отрисовку графиков
            await page.wait_for_timeout(4000)

            # Проверяем, не Cloudflare ли сейчас
            if await _is_cloudflare_page(page):
                print("[SCREENSHOT] Всё ещё Cloudflare — прерываю")
                await browser.close()
                return None

            # Прокручиваем страницу вниз и обратно (иногда помогает прогрузить)
            await page.evaluate("window.scrollTo(0, 500)")
            await page.wait_for_timeout(1000)
            await page.evaluate("window.scrollTo(0, 0)")
            await page.wait_for_timeout(1000)

            screenshot_bytes = await page.screenshot(full_page=True)
            print("[SCREENSHOT] Скриншот сделан")

        except Exception as e:
            print(f"[SCREENSHOT] Ошибка рендеринга: {e}")
            await browser.close()
            return None

        await browser.close()

    # Обрезаем
    try:
        img = Image.open(io.BytesIO(screenshot_bytes))
        crop_height = min(img.height, 780)
        cropped = img.crop((0, 0, img.width, crop_height))

        output = io.BytesIO()
        cropped.save(output, format="PNG")
        output.seek(0)
        return output

    except Exception as e:
        print(f"[SCREENSHOT] Ошибка обработки: {e}")
        return None