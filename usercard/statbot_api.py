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
        session = await self._get_session()
        now_ms = int(time.time() * 1000)
        start_30d_ms = now_ms - (days * 24 * 60 * 60 * 1000)
        start_7d_ms = now_ms - (7 * 24 * 60 * 60 * 1000)

        # 1. Totale voice tijd (30 dagen gefilterd)
        sums_url = f"{self.BASE_URL}/guilds/{guild_id}/voice/sums"
        sums_params = {
            "start": start_30d_ms,
            "end": now_ms,
            "whitelist_members[]": str(user_id),
            "voice_states[]": "normal",
        }

        # 2. Dagelijkse series (30 dagen) voor de Ma-Zo weekgrafiek
        day_series_url = f"{self.BASE_URL}/guilds/{guild_id}/voice/series"
        day_series_params = {
            "start": start_30d_ms,
            "end": now_ms,
            "whitelist_members[]": str(user_id),
            "voice_states[]": "normal",
            "interval": "day",
        }

        # 3. Uurlijkse series (7 dagen) voor piekuur zonder 400-fout
        hour_series_url = f"{self.BASE_URL}/guilds/{guild_id}/voice/series"
        hour_series_params = {
            "start": start_7d_ms,
            "end": now_ms,
            "whitelist_members[]": str(user_id),
            "voice_states[]": "normal",
            "interval": "hour",
        }

        # Request 1: Sums
        try:
            async with session.get(sums_url, headers=self._headers, params=sums_params) as resp:
                sums_data = await resp.json() if resp.status == 200 else {}
        except Exception:
            sums_data = {}

        # Request 2: Dagen (30d)
        try:
            async with session.get(day_series_url, headers=self._headers, params=day_series_params) as resp:
                day_data = await resp.json() if resp.status == 200 else []
        except Exception:
            day_data = []

        # Request 3: Uren (7d)
        try:
            async with session.get(hour_series_url, headers=self._headers, params=hour_series_params) as resp:
                hour_data = await resp.json() if resp.status == 200 else []
        except Exception:
            hour_data = []

        total_minutes = sums_data.get("count", 0) if isinstance(sums_data, dict) else 0
        total_hours = round(total_minutes / 60, 1)

        def extract_points(raw):
            if isinstance(raw, list):
                return raw
            if isinstance(raw, dict):
                return raw.get("data") or raw.get("series") or []
            return []

        # Verwerk 30-dagen weekdagverdeling (Ma=0 ... Zo=6)
        weekday_bins = [0] * 7
        for entry in extract_points(day_data):
            t_val = entry.get("timestamp") or entry.get("time") or entry.get("t") or entry.get("start")
            cnt = entry.get("count") or entry.get("c") or entry.get("value") or entry.get("v") or 0
            if t_val is not None and cnt:
                try:
                    if isinstance(t_val, (int, float)):
                        ts = t_val / 1000 if t_val > 1e11 else t_val
                        dt = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone()
                    else:
                        dt = datetime.fromisoformat(str(t_val).replace("Z", "+00:00")).astimezone()
                    weekday_bins[dt.weekday()] += cnt
                except Exception:
                    continue

        # Verwerk 7-dagen uurverdeling
        hour_bins = [0] * 24
        for entry in extract_points(hour_data):
            t_val = entry.get("timestamp") or entry.get("time") or entry.get("t") or entry.get("start")
            cnt = entry.get("count") or entry.get("c") or entry.get("value") or entry.get("v") or 0
            if t_val is not None and cnt:
                try:
                    if isinstance(t_val, (int, float)):
                        ts = t_val / 1000 if t_val > 1e11 else t_val
                        dt = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone()
                    else:
                        dt = datetime.fromisoformat(str(t_val).replace("Z", "+00:00")).astimezone()
                    hour_bins[dt.hour] += cnt
                except Exception:
                    continue

        # 1. Piekuur bepalen
        if sum(hour_bins) > 0:
            peak_hour = max(range(24), key=lambda h: hour_bins[h])
            peak_str = f"{peak_hour:02d}:00 - {(peak_hour + 1) % 24:02d}:00"
        else:
            peak_str = "Onbekend"

        # 2. Gewoontes berekenen
        weekend_mins = weekday_bins[4] + weekday_bins[5] + weekday_bins[6]
        total_weekday_mins = sum(weekday_bins) or total_minutes or 1
        weekend_pct = round((weekend_mins / total_weekday_mins) * 100)

        night_mins = sum(hour_bins[0:6]) + hour_bins[23]
        evening_mins = sum(hour_bins[18:23])
        day_mins = sum(hour_bins[6:18])

        # 3. Persona bepalen
        if total_hours < 0.5:
            persona = "Stille Luisteraar"
            activity_label = "Weinig activiteit"
        elif total_hours >= 40:
            persona = "VC Stamgast"
            activity_label = "Dagelijkse aanwezigheid"
        elif night_mins > 0 and night_mins > (sum(hour_bins) * 0.35):
            persona = "De Nachtbraker"
            activity_label = "Nachtbraker uren"
        elif weekend_pct >= 60:
            persona = "Weekend Strijder"
            activity_label = "Hoofdzakelijk weekends"
        elif evening_mins > day_mins:
            persona = "Prime-Time Prater"
            activity_label = "Avondspits"
        else:
            persona = "Dagvogel"
            activity_label = "Overdag actief"

        # 4. Voice Tier
        if total_hours >= 35:
            tier = "Diamant"
        elif total_hours >= 20:
            tier = "Goud"
        elif total_hours >= 8:
            tier = "Zilver"
        elif total_hours >= 0.5:
            tier = "Brons"
        else:
            tier = "Geen Tier"

        daily_avg_mins = round(total_minutes / 30)
        daily_avg_str = f"{daily_avg_mins} min / dag" if daily_avg_mins < 60 else f"{round(total_hours / 30, 1)} uur / dag"

        max_weekday = max(weekday_bins) if max(weekday_bins) > 0 else 1
        weekday_norm = [round(w / max_weekday, 2) for w in weekday_bins]
        weekday_hours = [round(w / 60, 1) for w in weekday_bins]

        return {
            "total_minutes": total_minutes,
            "total_hours": total_hours,
            "persona": persona,
            "tier": tier,
            "peak_time": peak_str,
            "activity_label": activity_label,
            "weekend_pct": weekend_pct,
            "daily_avg_str": daily_avg_str,
            "weekday_norm": weekday_norm,
            "weekday_hours": weekday_hours,
        }

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()