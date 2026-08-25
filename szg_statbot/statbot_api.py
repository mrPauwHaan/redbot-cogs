from datetime import datetime, timezone, timedelta
from typing import Optional
import aiohttp
import logging

log = logging.getLogger("red.szg_statbot.api")


class StatbotClient:
    BASE_URL = "https://api.statbot.net/v2"

    def __init__(self, api_key: str, guild_id: int):
        self.api_key = api_key
        self.guild_id = guild_id
        self.headers = {
            "Authorization": self.api_key,
            "Content-Type": "application/json"
        }

    async def _fetch(self, endpoint: str, params: dict) -> Optional[dict]:
        url = f"{self.BASE_URL}/guilds/{self.guild_id}/{endpoint}"
        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                async with session.get(url, params=params, timeout=15) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    log.error(f"Statbot API error ({resp.status}): {await resp.text()}")
                    return None
        except Exception as e:
            log.exception(f"Exception connecting to Statbot API: {e}")
            return None

    async def get_30_day_daily_average_hours(self) -> float:
        """Berekent het gemiddelde aantal voice-uren per dag over de afgelopen 30 dagen."""
        now = datetime.now(timezone.utc)
        start_date = (now - timedelta(days=30)).replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = now.replace(hour=0, minute=0, second=0, microsecond=0)

        params = {
            "stat": "voice",
            "interval": "day",
            "after": start_date.isoformat(),
            "before": end_date.isoformat()
        }

        data = await self._fetch("stats", params)
        if not data or "data" not in data:
            return 0.0

        daily_points = data.get("data", [])
        if not daily_points:
            return 0.0

        total_seconds = sum(point.get("value", 0) for point in daily_points)
        days_count = max(len(daily_points), 1)
        return round((total_seconds / 3600) / days_count, 1)

    async def get_today_voice_hours(self) -> float:
        """Haalt het cumulatieve aantal voice-uren op sinds 00:00 UTC vandaag."""
        now = datetime.now(timezone.utc)
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)

        params = {
            "stat": "voice",
            "interval": "hour",
            "after": start_of_day.isoformat()
        }

        data = await self._fetch("stats", params)
        if not data or "data" not in data:
            return 0.0

        hourly_points = data.get("data", [])
        total_seconds = sum(point.get("value", 0) for point in hourly_points)
        return round(total_seconds / 3600, 1)


def format_category_name(current_hours: float, target_hours: float) -> str:
    """
    Formatteert de categorienaam met progressieblokken (Optie A, max ~20 tekens).
    Voorbeeld: ██░░ [ 4/12u ] ░░░░
    """
    total_blocks = 8

    if target_hours <= 0:
        return "░░░░ [ SPRAAK ] ░░░░"

    ratio = min(max(current_hours / target_hours, 0.0), 1.0)
    filled_blocks = round(ratio * total_blocks)
    empty_blocks = total_blocks - filled_blocks

    full_bar = ("█" * filled_blocks) + ("░" * empty_blocks)
    left_part = full_bar[:4]
    right_part = full_bar[4:]

    cur_str = f"{current_hours:.1f}" if current_hours < 10 else f"{int(round(current_hours))}"
    tar_str = f"{target_hours:.1f}" if target_hours < 10 else f"{int(round(target_hours))}"

    if current_hours >= target_hours and target_hours > 0:
        return f"🔥🔥 [ {cur_str}/{tar_str}u ] 🔥🔥"

    return f"{left_part} [ {cur_str}/{tar_str}u ] {right_part}"