"""
Утилиты для работы со ссылками Tracker.gg.
Парсинг данных не делаем — только скриншот.
"""

import urllib.parse


async def parse_tracker_url(url: str) -> str | None:
    """
    Достаёт Riot ID из ссылки Tracker.gg.

    Пример:
    https://tracker.gg/valorant/profile/riot/Player%23TAG/overview
    -> Player#TAG
    """
    if "/profile/riot/" not in url:
        return None

    try:
        part = url.split("/profile/riot/")[1].split("/")[0]
        riot_id = urllib.parse.unquote(part)
        return riot_id
    except (IndexError, ValueError):
        return None


def format_last_matches(matches: list[str]) -> str:
    """Оставляем на будущее, если решишь парсить данные"""
    mapping = {"W": "✅", "L": "❌", "D": "➖"}
    return " ".join(mapping.get(m, "➖") for m in matches)