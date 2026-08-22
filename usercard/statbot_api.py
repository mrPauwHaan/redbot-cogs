import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional
import aiohttp


class StatbotClient:
    BASE_URL = "https://api.statbot.net/v1"

    def __init__(self, api_key: str, session: Optional[aiohttp.ClientSession] = None):
        self.api_key = api_key
        self._session = session
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def get_user_voice_stats(
        self, guild_id: int, user_id: int, days: int = 30
    ) -> Dict[str, Any]:
        """Haalt gefilterde voice data op en berekent persona, tier en activiteitspatroon."""
        session = await self._get_session()
        now_ms = int(time.time() * 1000)
        start_ms = now_ms - (days * 24 * 60 * 60 * 1000)

        # 1. Totale voice tijd (gefilterd op normale voice states)
        sums_url = f"{self.BASE_URL}/guilds/{guild_id}/voice/sums"
        sums_params = {
            "start": start_ms,
            "end": now_ms,
            "whitelist_members[]": str(user_id),
            "voice_states[]": "normal",
        }

        # 2. Uurlijkse verdeling over 30 dagen
        series_url = f"{self.BASE_URL}/guilds/{guild_id}/voice/series"
        series_params = {
            "start": start_ms,
            "end": now_ms,
            "whitelist_members[]": str(user_id),
            "voice_states[]": "normal",
            "interval": "hour",
        }

        try:
            async with session.get(sums_url, headers=self._headers, params=sums_params) as resp:
                sums_data = await resp.json() if resp.status == 200 else {}
        except Exception:
            sums_data = {}

        try:
            async with session.get(series_url, headers=self._headers, params=series_params) as resp:
                series_data = await resp.json() if resp.status == 200 else []
        except Exception:
            series_data = []

        total_minutes = sums_data.get("count", 0) if isinstance(sums_data, dict) else 0
        total_hours = round(total_minutes / 60, 1)

        # Analyseer dag- en uurverdeling
        hour_bins = [0] * 24
        weekday_bins = [0] * 7  # 0=Maandag, 6=Zondag

        if isinstance(series_data, list):
            for entry in series_data:
                t_ms = entry.get("time") or entry.get("t")
                cnt = entry.get("count") or entry.get("c", 0)
                if t_ms and cnt:
                    dt = datetime.fromtimestamp(t_ms / 1000, tz=timezone.utc)
                    hour_bins[dt.hour] += cnt
                    weekday_bins[dt.weekday()] += cnt

        # 3. Piekuur bepalen
        peak_hour = max(range(24), key=lambda h: hour_bins[h]) if total_minutes > 0 else None
        peak_str = f"{peak_hour:02d}:00 - {(peak_hour + 1) % 24:02d}:00" if peak_hour is not None else "-"

        # 4. Persona bepaling
        night_mins = sum(hour_bins[0:6]) + hour_bins[23]
        evening_mins = sum(hour_bins[18:23])
        day_mins = sum(hour_bins[6:18])
        weekend_mins = weekday_bins[4] + weekday_bins[5] + weekday_bins[6]

        if total_hours < 0.5:
            persona = "Stille Luisteraar"
        elif total_hours >= 40:
            persona = "VC Stamgast"
        elif total_minutes > 0 and night_mins > (total_minutes * 0.4):
            persona = "De Nachtbraker"
        elif total_minutes > 0 and weekend_mins > (total_minutes * 0.6):
            persona = "Weekend Strijder"
        elif evening_mins > day_mins:
            persona = "Prime-Time Prater"
        else:
            persona = "Dagvogel"

        # 5. Tier bepaling
        if total_hours >= 35:
            tier = "Diamant"
        elif total_hours >= 20:
            tier = "Goud"
        elif total_hours >= 8:
            tier = "Zilver"
        elif total_hours > 0:
            tier = "Brons"
        else:
            tier = "Geen Tier"

        # 6. Relatieve normalisatie voor de 7-daagse weekgrafiek (0.0 - 1.0)
        max_weekday = max(weekday_bins) if max(weekday_bins) > 0 else 1
        weekday_norm = [round(w / max_weekday, 2) for w in weekday_bins]

        return {
            "total_minutes": total_minutes,
            "total_hours": total_hours,
            "persona": persona,
            "tier": tier,
            "peak_time": peak_str,
            "weekday_bins": weekday_bins,
            "weekday_norm": weekday_norm,
        }

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()