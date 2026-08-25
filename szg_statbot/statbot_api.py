from datetime import datetime, timezone, timedelta
from typing import Optional
import aiohttp
import logging

log = logging.getLogger("red.szg_statbot.api")


class StatbotClient:
    BASE_URL = "https://api.statbot.net/v1"

    def __init__(self, api_key: str, guild_id: int):
        self.api_key = api_key
        self.guild_id = guild_id
        auth_header = api_key if api_key.startswith("Bearer ") else f"Bearer {api_key}"
        self.headers = {
            "Authorization": auth_header,
            "Accept": "application/json"
        }

    async def _fetch_voice_sums(self, params: dict) -> Optional[dict]:
        url = f"{self.BASE_URL}/guilds/{self.guild_id}/voice/sums"
        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                async with session.get(url, params=params, timeout=15) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    log.error(f"Statbot API fout ({resp.status}): {await resp.text()}")
                    return None
        except Exception as e:
            log.exception(f"Fout bij verbinden met Statbot API: {e}")
            return None

    async def get_30_day_daily_average_hours(self) -> float:
        """
        Haalt het totale aantal voice-minuten over de afgelopen 30 dagen op
        en berekent het gemiddelde aantal uren per dag.
        """
        now = datetime.now(timezone.utc)
        start_dt = (now - timedelta(days=30)).replace(hour=0, minute=0, second=0, microsecond=0)
        end_dt = now.replace(hour=0, minute=0, second=0, microsecond=0)

        params = {
            "start": int(start_dt.timestamp() * 1000),
            "end": int(end_dt.timestamp() * 1000),
            "bot": "false"
        }

        data = await self._fetch_voice_sums(params)
        if not data or "count" not in data:
            return 0.0

        total_minutes = data.get("count", 0)
        daily_average_hours = (total_minutes / 60) / 30
        return round(daily_average_hours, 1)

    async def get_today_voice_hours(self) -> float:
        """Haalt het totale aantal voice-minuten op sinds 00:00 UTC vandaag."""
        now = datetime.now(timezone.utc)
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)

        params = {
            "start": int(start_of_day.timestamp() * 1000),
            "bot": "false"
        }

        data = await self._fetch_voice_sums(params)
        if not data or "count" not in data:
            return 0.0

        today_minutes = data.get("count", 0)
        return round(today_minutes / 60, 1)


def format_category_name(current_hours: float, target_hours: float) -> str:
    """Formatteert de categorienaam met progressieblokken (max ~20 tekens)."""
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