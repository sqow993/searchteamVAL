import aiohttp
import asyncio
from config import RIOT_API_KEY

# Riot API endpoints
ACCOUNT_URL = "https://europe.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{gameName}/{tagLine}"
MATCH_LIST_URL = "https://europe.api.riotgames.com/val/match/v1/matchlists/by-puuid/{puuid}"
MATCH_DETAILS_URL = "https://europe.api.riotgames.com/val/match/v1/matches/{matchId}"
MMR_URL = "https://europe.api.riotgames.com/val/ranked/v1/leaderboards/by-act/{actId}"


async def get_puuid(game_name: str, tag_line: str) -> str | None:
    """Получает PUUID по Riot ID"""
    url = ACCOUNT_URL.format(gameName=game_name, tagLine=tag_line)
    headers = {"X-Riot-Token": RIOT_API_KEY}
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data.get("puuid")
            else:
                print(f"[RIOT] Ошибка получения PUUID: {resp.status}")
                return None


async def get_match_history(puuid: str, count: int = 5) -> list | None:
    """Получает последние матчи"""
    url = MATCH_LIST_URL.format(puuid=puuid)
    headers = {"X-Riot-Token": RIOT_API_KEY}
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data.get("history", [])[:count]
            else:
                print(f"[RIOT] Ошибка получения истории: {resp.status}")
                return None


async def get_match_details(match_id: str) -> dict | None:
    """Получает детали матча"""
    url = MATCH_DETAILS_URL.format(matchId=match_id)
    headers = {"X-Riot-Token": RIOT_API_KEY}
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            if resp.status == 200:
                return await resp.json()
            else:
                print(f"[RIOT] Ошибка получения матча: {resp.status}")
                return None


async def get_player_stats(riot_id: str) -> dict | None:
    """
    Получает статистику игрока по Riot ID.
    
    Возвращает:
    {
        "name": "Player#TAG",
        "puuid": "...",
        "rank": "Silver 1",
        "last_matches": [
            {"result": "W", "kills": 15, "deaths": 10, "assists": 5, "agent": "Jett"},
            ...
        ]
    }
    """
    # Парсим Riot ID
    if "#" not in riot_id:
        return None
    
    game_name, tag_line = riot_id.split("#", 1)
    
    # Получаем PUUID
    puuid = await get_puuid(game_name, tag_line)
    if not puuid:
        return None
    
    # Получаем историю
    history = await get_match_history(puuid, count=5)
    if not history:
        return None
    
    # Собираем детали каждого матча
    matches = []
    for match_info in history:
        match_id = match_info.get("matchId")
        if match_id:
            details = await get_match_details(match_id)
            if details:
                # Извлекаем статистику игрока из деталей
                # Структура ответа Riot API сложная, упрощаем
                players = details.get("players", [])
                for p in players:
                    if p.get("puuid") == puuid:
                        stats = p.get("stats", {})
                        matches.append({
                            "result": "W" if p.get("teamId") == details.get("teams", [{}])[0].get("teamId") else "L",
                            "kills": stats.get("kills", 0),
                            "deaths": stats.get("deaths", 0),
                            "assists": stats.get("assists", 0),
                            "agent": p.get("characterId", "Unknown")
                        })
                        break
    
    return {
        "name": riot_id,
        "puuid": puuid,
        "last_matches": matches
    }