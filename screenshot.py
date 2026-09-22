"""
Скриншот профиля Tracker.gg через FlareSolverr + Playwright.
"""

import io
import aiohttp
from PIL import Image
from playwright.async_api import async_playwright


# Сюда вставь URL твоего FlareSolverr на Render
# Например: "https://flaresolverr-xxxx.onrender.com"
FLARESOLVERR_URL = "https://flaresolverr-9rkr.onrender.com"


async def fetch_html_via_flaresolverr(tracker_url: str) -> str | None:
    """
    Отправляет запрос в FlareSolverr.
    FlareSolverr решает Cloudflare и возвращает готовый HTML.
    """
    payload = {
        "cmd": "request.get",
        "url": tracker_url,
        "maxTimeout": 90000  # 90 секунд на решение challenge
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{FLARESOLVERR_URL}/v1",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=120)
            ) as resp:
                if resp.status != 200:
                    print(f"[FLARESOLVERR] HTTP {resp.status}")
                    return None

                data = await resp.json()
                solution = data.get("solution", {})
                html = solution.get("response")

                if html:
                    print(f"[FLARESOLVERR] HTML получен, размер: {len(html)}")
                    return html
                else:
                    print(f"[FLARESOLVERR] Пустой ответ: {data}")
                    return None

    except Exception as e:
        print(f"[FLARESOLVERR] Ошибка: {e}")
        return None


async def take_stats_screenshot(tracker_url: str) -> io.BytesIO | None:
    """
    Получает HTML через FlareSolverr и рендерит его в Playwright.
    """

    # Шаг 1: Получаем HTML через FlareSolverr
    print(f"[SCREENSHOT] Запрос в FlareSolverr для {tracker_url}")
    html = await fetch_html_via_flaresolverr(tracker_url)

    if not html:
        print("[SCREENSHOT] FlareSolverr не смог получить HTML")
        return None

    # Шаг 2: Рендерим HTML в Playwright и делаем скриншот
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-gpu",
                "--disable-dev-shm-usage",
            ]
        )

        page = await browser.new_page(viewport={"width": 1440, "height": 900})

        try:
            # Загружаем готовый HTML от FlareSolverr
            await page.set_content(html, wait_until="networkidle")

            # Даём время на отрисовку графиков
            await page.wait_for_timeout(5000)

            # Скриншот
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