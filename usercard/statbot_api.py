import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple
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

    async def get_member_voice_rank(
        self, guild_id: int, user_id: int
    ) -> Tuple[Optional[int], Optional[int]]:
        """Haalt de 30-dagen rang en totaal aantal actieve leden op via het officiële ranks endpoint."""
        session = await self._get_session()
        url = f"{self.BASE_URL}/guilds/{guild_id}/members/{user_id}/ranks"

        try:
            async with session.get(url, headers=self._headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    voice_ranks = data.get("voice", {})

                    # Zoek naar de 30d / maandelijkse rang
                    period_data = (
                        voice_ranks.get("30d")
                        or voice_ranks.get("month")
                        or voice_ranks.get("1m")
                        or voice_ranks
                    )

                    if isinstance(period_data, dict):
                        rank = period_data.get("rank") or period_data.get("position")
                        total = (
                            period_data.get("total")
                            or period_data.get("outOf")
                            or period_data.get("count_members")
                            or data.get("total_members")
                        )
                        if rank is not None:
                            return int(rank), int(total) if total is not None else None
                    elif isinstance(period_data, (int, float)):
                        return int(period_data), None
                else:
                    print(f"[UserCard Statbot] Ranks API status {resp.status}: {await resp.text()}")
        except Exception as e:
            print(f"[UserCard Statbot] Fout bij ophalen member ranks: {e}")

        return None, None

    async def get_user_voice_stats(
        self, guild_id: int, user_id: int, days: int = 30
    ) -> Dict[str, Any]:
        session = await self._get_session()
        now_ms = int(time.time() * 1000)
        start_ms = now_ms - (days * 24 * 60 * 60 * 1000)

        # 1. Totale voice tijd
        sums_url = f"{self.BASE_URL}/guilds/{guild_id}/voice/sums"
        sums_params = {
            "start": start_ms,
            "end": now_ms,
            "whitelist_members[]": str(user_id),
            "voice_states[]": "normal",
        }

        # 2. Uurlijkse series voor piekuur en weekdagverdeling
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

        # 3. Officiële Statbot Rang ophalen
        rank_num, total_members = await self.get_member_voice_rank(guild_id, user_id)
        if rank_num is not None:
            if total_members is not None and total_members > 0:
                top_pct = max(1, round((rank_num / total_members) * 100))
                rank_str = f"#{rank_num} van {total_members}"
                top_pct_str = f"Top {top_pct}%"
            else:
                rank_str = f"#{rank_num}"
                top_pct_str = "-"
        elif total_hours > 0:
            rank_str = "N.v.t."
            top_pct_str = "-"
        else:
            rank_str = "-"
            top_pct_str = "-"

        # 4. Verwerk unixTimestamp (ms) en count (minuten)
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

        has_series_data = sum(hour_bins) > 0

        # 5. Piekuur bepalen
        if has_series_data:
            peak_hour = max(range(24), key=lambda h: hour_bins[h])
            peak_str = f"{peak_hour:02d}:00 - {(peak_hour + 1) % 24:02d}:00"
        else:
            peak_str = "-"

        # 6. Gewoontes & Weekend aandeel (Vrijdag t/m Zondag)
        weekend_mins = weekday_bins[4] + weekday_bins[5] + weekday_bins[6]
        total_tracked_mins = sum(weekday_bins) or total_minutes or 1
        weekend_pct = round((weekend_mins / total_tracked_mins) * 100)

        night_mins = sum(hour_bins[0:6]) + hour_bins[23]
        evening_mins = sum(hour_bins[18:23])
        day_mins = sum(hour_bins[6:18])

        # 7. Persona bepaling
        if total_hours < 0.5:
            persona = "Stille Luisteraar"
            activity_label = "Weinig activiteit"
        elif total_hours >= 40:
            persona = "VC Stamgast"
            activity_label = "Dagelijkse aanwezigheid"
        elif night_mins > (total_tracked_mins * 0.4):
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

        daily_avg_mins = round(total_minutes / 30)
        daily_avg_str = f"{daily_avg_mins} min / dag" if daily_avg_mins < 60 else f"{round(total_hours / 30, 1)} uur / dag"

        max_weekday = max(weekday_bins) if max(weekday_bins) > 0 else 1
        weekday_norm = [round(w / max_weekday, 2) for w in weekday_bins]
        weekday_hours = [round(w / 60, 1) for w in weekday_bins]

        return {
            "total_minutes": total_minutes,
            "total_hours": total_hours,
            "rank_str": rank_str,
            "top_pct_str": top_pct_str,
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