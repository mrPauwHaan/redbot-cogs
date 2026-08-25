from datetime import datetime, timedelta
from typing import Optional
import aiohttp
import logging
import pytz

log = logging.getLogger("red.szg_statbot.api")


class StatbotClient:
    BASE_URL = "https://api.statbot.net/v1"

    def __init__(self, api_key: str, guild_id: int, timezone_name: str = "Europe/Amsterdam"):
        self.api_key = api_key.strip()
        self.guild_id = guild_id
        self.tz = pytz.timezone(timezone_name)

        auth_token = self.api_key if self.api_key.startswith("Bearer ") else f"Bearer {self.api_key}"
        self.headers = {
            "Authorization": auth_token,
            "Accept": "application/json"
        }

    async def _fetch_voice_sums(self, params: dict) -> Optional[dict]:
        url = f"{self.BASE_URL}/guilds/{self.guild_id}/voice/sums"
        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                async with session.get(url, params=params, timeout=15) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    log.error(f"Statbot API fout (HTTP {resp.status}): {await resp.text()}")
                    return None
        except Exception as e:
            log.exception(f"Fout bij verbinden met Statbot API: {e}")
            return None

    async def get_30_day_daily_average_hours(self) -> float:
        """Haalt het totale aantal voice-minuten over de afgelopen 30 dagen op en berekent het daggemiddelde."""
        now_local = datetime.now(self.tz)
        start_dt = (now_local - timedelta(days=30)).replace(hour=0, minute=0, second=0, microsecond=0)
        end_dt = now_local.replace(hour=0, minute=0, second=0, microsecond=0)

        params = {
            "start": str(int(start_dt.timestamp() * 1000)),
            "end": str(int(end_dt.timestamp() * 1000)),
            "bot": "false"
        }

        data = await self._fetch_voice_sums(params)
        if not data or "count" not in data:
            return 0.0

        total_minutes = data.get("count", 0)
        daily_average_hours = (total_minutes / 60.0) / 30.0
        return round(daily_average_hours, 1)

    async def get_today_voice_hours(self) -> float:
        """Haalt het cumulatieve aantal voice-uren op sinds 00:00 lokale tijd vandaag."""
        now_local = datetime.now(self.tz)
        start_of_day = now_local.replace(hour=0, minute=0, second=0, microsecond=0)

        params = {
            "start": str(int(start_of_day.timestamp() * 1000)),
            "bot": "false"
        }

        data = await self._fetch_voice_sums(params)
        if not data or "count" not in data:
            return 0.0

        today_minutes = data.get("count", 0)
        return round(today_minutes / 60.0, 1)


def format_category_name(current_hours: float, target_hours: float) -> str:
    """
    Formatteert de categorienaam met afgeronde glyphs (Optie 4) en dubbele cijfers:
    - 0 uur:       ▱▱▱▱[ GEM: 12u ]▱▱▱▱ (Lege blokjes + daggemiddelde)
    - 1-11 uur:    ▰▰▱▱[ 03/12u ]▱▱▱▱
    - 12u+ (100%): 🔥🔥[ 14/12u ]🔥🔥 (Overdrive / doel behaald)
    """
    total_blocks = 8

    if target_hours <= 0:
        return "▱▱▱▱[ SPRAAK ]▱▱▱▱"

    tar_int = min(int(round(target_hours)), 99)
    tar_str = f"{tar_int:02d}"

    # 1. Bij 0 uur activiteit: toon lege blokjes rond het daggemiddelde
    if current_hours <= 0.0:
        return f"▱▱▱▱[ GEM: {tar_str}u ]▱▱▱▱"

    # 2. Vanaf activiteit: bereken en render gevulde en lege blokken
    ratio = min(max(current_hours / target_hours, 0.0), 1.0)
    filled_blocks = round(ratio * total_blocks)
    empty_blocks = total_blocks - filled_blocks

    full_bar = ("▰" * filled_blocks) + ("▱" * empty_blocks)
    left_part = full_bar[:4]
    right_part = full_bar[4:]

    cur_int = min(int(round(current_hours)), 99)
    cur_str = f"{cur_int:02d}"

    # 3. Overdrive weergave bij het behalen of overtreffen van het doel
    if current_hours >= target_hours:
        return f"🔥🔥[ {cur_str}/{tar_str}u ]🔥🔥"

    return f"{left_part}[ {cur_str}/{tar_str}u ]{right_part}"