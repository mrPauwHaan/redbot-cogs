import time
import aiohttp
from typing import Optional, Dict, Any

class StatbotClient:
    BASE_URL = "https://api.statbot.net/v1"

    def __init__(self, api_key: str, session: Optional[aiohttp.ClientSession] = None):
        self.api_key = api_key
        self._session = session
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def get_user_voice_stats(self, guild_id: int, user_id: int, days: int = 30) -> Dict[str, Any]:
        session = await self._get_session()
        now_ms = int(time.time() * 1000)
        start_ms = now_ms - (days * 24 * 60 * 60 * 1000)

        # 1. Total voice duration
        sums_url = f"{self.BASE_URL}/guilds/{guild_id}/voice/sums"
        sums_params = {
            "start": start_ms,
            "end": now_ms,
            "whitelist_members[]": str(user_id),
            "voice_states[]": "normal"
        }

        # 2. Channel breakdown
        series_url = f"{self.BASE_URL}/guilds/{guild_id}/voice/series"
        series_params = {
            "start": start_ms,
            "end": now_ms,
            "whitelist_members[]": str(user_id),
            "by_channel": "true",
            "interval": "month"
        }

        async with session.get(sums_url, headers=self._headers, params=sums_params) as resp:
            sums_data = await resp.json() if resp.status == 200 else {}

        async with session.get(series_url, headers=self._headers, params=series_params) as resp:
            series_data = await resp.json() if resp.status == 200 else []

        total_seconds = sums_data.get("count", 0) if isinstance(sums_data, dict) else 0

        # Sort top channels
        channel_totals: Dict[str, int] = {}
        for entry in series_data:
            ch_id = entry.get("channelId", "Unknown")
            channel_totals[ch_id] = channel_totals.get(ch_id, 0) + entry.get("count", 0)

        sorted_channels = sorted(channel_totals.items(), key=lambda x: x[1], reverse=True)

        return {
            "timeframe_days": days,
            "total_seconds": total_seconds,
            "total_hours": round(total_seconds / 3600, 1),
            "top_channels": sorted_channels[:3]
        }

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

def calculate_voice_persona(stats: Dict[str, Any]) -> str:
    total_hours = stats.get("total_hours", 0)
    top_channels = stats.get("top_channels", [])

    if total_hours == 0:
        return "Ghost Listener"
    if total_hours > 40:
        return "VC Resident"
    if len(top_channels) == 1:
        return "Channel Loyalist"
    return "Social Butterfly"