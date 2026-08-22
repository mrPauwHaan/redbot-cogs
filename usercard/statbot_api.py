import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional, List, Tuple
import aiohttp


class StatbotClient:
    BASE_URL = "https://api.statbot.net/v1"
    _top_cache: Dict[int, Tuple[float, List[Dict[str, Any]]]] = {}
    WHITELIST_ROLES = ["724556731564163082", "563348666312687618"]

    def __init__(self, api_key: str, session: Optional[aiohttp.ClientSession] = None):
        self.api_key = api_key
        self._session = session
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def get_top_voice_members(
        self, guild_id: int, start_ms: int, end_ms: int
    ) -> List[Dict[str, Any]]:
        """Haalt alle actieve voice leden op gefilterd op Lid/SZG+ rollen (15 min cache)."""
        now = time.time()
        if guild_id in self._top_cache:
            cache_time, cache_data = self._top_cache[guild_id]
            if now - cache_time < 900:  # 15 minuten cache
                return cache_data

        session = await self._get_session()
        url = f"{self.BASE_URL}/guilds/{guild_id}/voice/tops/members"
        params = [
            ("start", str(start_ms)),
            ("end", str(end_ms)),
            ("voice_states[]", "normal"),
            ("whitelist_roles[]", self.WHITELIST_ROLES[0]),
            ("whitelist_roles[]", self.WHITELIST_ROLES[1]),
            ("limit", "100"),
        ]

        try:
            async with session.get(url, headers=self._headers, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    members = data if isinstance(data, list) else data.get("data", [])
                    self._top_cache[guild_id] = (now, members)
                    return members
                else:
                    print(f"[UserCard Statbot] Top Voice API fout {resp.status}: {await resp.text()}")
        except Exception as e:
            print(f"[UserCard Statbot] Fout bij ophalen top voice members: {e}")

        return []

    async def get_user_voice_stats(
        self, guild_id: int, user_id: int, days: int = 30
    ) -> Dict[str, Any]:
        session = await self._get_session()
        now_ms = int(time.time() * 1000)
        start_ms = now_ms - (days * 24 * 60 * 60 * 1000)

        # 1. Totale voice tijd voor lid
        sums_url = f"{self.BASE_URL}/guilds/{guild_id}/voice/sums"
        sums_params = {
            "start": start_ms,
            "end": now_ms,
            "whitelist_members[]": str(user_id),
            "voice_states[]": "normal",
        }

        # 2. Uurlijkse series voor piekuur en weekgrafiek
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

        # 3. Positie bepalen binnen de Lid/SZG+ pool
        top_members = await self.get_top_voice_members(guild_id, start_ms, now_ms)
        rank = None
        total_active_members = len(top_members)
        user_id_str = str(user_id)

        for idx, entry in enumerate(top_members, start=1):
            m_id = str(entry.get("id") or entry.get("memberId") or entry.get("member_id") or "")
            if m_id == user_id_str:
                rank = entry.get("rank") or idx
                if not total_minutes and entry.get("count"):
                    total_minutes = entry.get("count", 0)
                    total_hours = round(total_minutes / 60, 1)
                break

        if rank is not None and total_active_members > 0:
            rank_str = f"#{rank} van {total_active_members}"
        elif total_active_members > 0 and total_hours > 0:
            rank_str = f">{total_active_members}"
        elif total_hours > 0:
            rank_str = "Actief"
        else:
            rank_str = "-"

        # 4. Uur- en weekdagverdeling parsen
        data_points = series_data if isinstance(series_data, list) else series_data.get("data", [])
        hour_bins = [0] * 24
        weekday_bins = [0] * 7  # 0=Maandag ... 6=Zondag

        for entry in data_points:
            raw_time = entry.get("unixTimestamp") or entry.get("timestamp") or entry.get("time")
            cnt = entry.get("count", 0)

            if raw_time is not None and cnt:
                try:
                    ts = raw_time / 1000 if raw_time > 1e11 else raw_time
                    dt = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone()
                    hour_bins[dt.hour] += cnt
                    weekday_bins[dt.weekday()] += cnt
                except Exception:
                    continue

        # 5. Piekuur
        if sum(hour_bins) > 0:
            peak_hour = max(range(24), key=lambda h: hour_bins[h])
            peak_str = f"{peak_hour:02d}:00 - {(peak_hour + 1) % 24:02d}:00"
        else:
            peak_str = "-"

        # 6. Weekend percentage
        weekend_mins = weekday_bins[4] + weekday_bins[5] + weekday_bins[6]
        tracked_mins = sum(weekday_bins) or total_minutes or 1
        weekend_pct = round((weekend_mins / tracked_mins) * 100)

        # 7. Persona
        night_mins = sum(hour_bins[0:6]) + hour_bins[23]
        evening_mins = sum(hour_bins[18:23])
        day_mins = sum(hour_bins[6:18])

        if total_hours < 0.5:
            persona = "Stille Luisteraar"
            activity_label = "Weinig activiteit"
        elif total_hours >= 40:
            persona = "VC Stamgast"
            activity_label = "Dagelijks aanwezig"
        elif night_mins > (tracked_mins * 0.4):
            persona = "De Nachtbraker"
            activity_label = "Vooral 's nachts"
        elif weekend_pct >= 60:
            persona = "Weekend Strijder"
            activity_label = "Vooral weekends"
        elif evening_mins > day_mins:
            persona = "Prime-Time Prater"
            activity_label = "Avondspits"
        else:
            persona = "Dagvogel"
            activity_label = "Overdag actief"

        daily_avg_mins = round(total_minutes / 30)
        daily_avg_str = (
            f"{daily_avg_mins} min / dag"
            if daily_avg_mins < 60
            else f"{round(total_hours / 30, 1)} uur / dag"
        )

        # 8. Gemiddelde per specifieke weekdag berekenen
        end_dt = datetime.fromtimestamp(now_ms / 1000, tz=timezone.utc).astimezone()
        weekday_occurrences = [0] * 7
        for d in range(days):
            day_dt = end_dt - timedelta(days=d)
            weekday_occurrences[day_dt.weekday()] += 1

        avg_weekday_mins = [
            (weekday_bins[i] / max(weekday_occurrences[i], 1))
            for i in range(7)
        ]

        weekday_hours = [round(m / 60, 1) for m in avg_weekday_mins]
        max_avg_val = max(avg_weekday_mins) if max(avg_weekday_mins) > 0 else 1
        weekday_norm = [round(m / max_avg_val, 2) for m in avg_weekday_mins]

        return {
            "total_minutes": total_minutes,
            "total_hours": total_hours,
            "rank_str": rank_str,
            "persona": persona,
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