"""
Скриншот профиля Tracker.gg через Playwright.
"""

import io
from PIL import Image
from playwright.async_api import async_playwright


async def take_stats_screenshot(tracker_url: str) -> io.BytesIO | None:
    """
    Открывает Tracker.gg и возвращает скриншот верхней части страницы
    с блоком статистики.
    """

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-gpu",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
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
        )

        page = await context.new_page()

        try:
            await page.goto(
                tracker_url,
                wait_until="domcontentloaded",
                timeout=60000
            )

            # Ждём, пока данные подгрузятся
            await page.wait_for_timeout(7000)

            # Полный скриншот страницы
            screenshot_bytes = await page.screenshot(full_page=True)

        except Exception as e:
            print(f"[SCREENSHOT] Ошибка рендеринга: {e}")
            await browser.close()
            return None

        await browser.close()

    # Обрезаем верхнюю часть с блоком статистики
    try:
        img = Image.open(io.BytesIO(screenshot_bytes))

        # Первые 780 пикселей — Rating, Level, Damage/Round, K/D, HS%, Win%
        crop_height = min(img.height, 780)
        cropped = img.crop((0, 0, img.width, crop_height))

        output = io.BytesIO()
        cropped.save(output, format="PNG")
        output.seek(0)
        return output

    except Exception as e:
        print(f"[SCREENSHOT] Ошибка обработки: {e}")
        return None