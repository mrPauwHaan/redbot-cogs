from redbot.core import commands
from redbot.core.bot import Red
import discord
import typing

import asyncio
import functools
import io
import time
from pathlib import Path
from datetime import datetime

from fontTools.ttLib import TTFont
from PIL import Image, ImageChops, ImageDraw, ImageFont
from redbot.core.data_manager import bundled_data_path
from frappeclient import FrappeClient

from .view import usercardView
from .statbot_api import StatbotClient


class usercard(commands.Cog):
    """A cog to generate user cards, monthly stats, and yearly wrapped images."""

    WHITELIST_ROLES = [724556731564163082, 563348666312687618]

    def __init__(self, bot: Red) -> None:
        super().__init__()
        self.bot: Red = bot
        self.Frappeclient = None
        self.api_key = None
        self.api_secret = None
        self._latest_event_cache: typing.Optional[typing.Tuple[float, int]] = None

        self.font_path: Path = bundled_data_path(self) / "arial.ttf"
        self.bold_font_path: Path = bundled_data_path(self) / "arial_bold.ttf"
        self.font: typing.Dict[int, ImageFont.ImageFont] = {
            size: ImageFont.truetype(str(self.font_path), size=size)
            for size in {24, 28, 30, 32, 36, 40, 54}
        }
        self.bold_font: typing.Dict[int, ImageFont.ImageFont] = {
            size: ImageFont.truetype(str(self.bold_font_path), size=size)
            for size in {24, 26, 30, 32, 36, 40, 50, 60}
        }
        self.font_to_remove_unprintable_characters: TTFont = TTFont(self.font_path)
        self.icons: typing.Dict[str, Path] = {
            name: (bundled_data_path(self) / f"{name}.png")
            for name in (
                "logo",
                "person",
                "game",
                "background",
            )
        }

    async def cog_load(self):
        frappe_keys = await self.bot.get_shared_api_tokens("frappelogin")
        self.api_key = frappe_keys.get("username")
        self.api_secret = frappe_keys.get("password")

        if self.api_key and self.api_secret:
            self.Frappeclient = FrappeClient("https://shadowzone.nl")
            self.Frappeclient.login(self.api_key, self.api_secret)
        else:
            print("API keys for Frappe are missing.")

    async def cog_unload(self) -> None:
        self.font_to_remove_unprintable_characters.close()

    def is_member(self, member: discord.Member) -> bool:
        """Controleert strikt op basis van actieve Discord-rollen of iemand Lid/SZG+ is."""
        if not isinstance(member, discord.Member):
            return False
        return any(role.id in self.WHITELIST_ROLES for role in getattr(member, 'roles', []))

    def get_latest_event_number(self, fallback_max: int = 0) -> int:
        """Haalt het hoogste afgelopen eventnummer op uit Frappe 'Beheer events' (1 uur cache)."""
        now = time.time()
        if self._latest_event_cache:
            cache_time, cached_val = self._latest_event_cache
            if now - cache_time < 3600:
                return max(cached_val, fallback_max)

        if not self.Frappeclient:
            return fallback_max

        try:
            docs = self.Frappeclient.get_list(
                'Beheer events',
                fields=['event_name', 'name'],
                filters={'afgelopen': 1},
                limit_page_length=200
            )
            max_num = fallback_max
            if docs:
                for doc in docs:
                    event_name = doc.get('event_name') or doc.get('name') or ''
                    if event_name and event_name not in ('Qmusic Foute Party: 24 - 26 juni 2022', 'Vakantie: 11-18 augustus 2023'):
                        try:
                            num = int(event_name.split()[1].strip(":"))
                            if num > max_num:
                                max_num = num
                        except (IndexError, ValueError):
                            continue

                if max_num > fallback_max:
                    self._latest_event_cache = (now, max_num)
                    return max_num
        except Exception as e:
            print(f"[UserCard] Fout bij ophalen Beheer events: {e}")

        return fallback_max

    def get_frappe_year_events(self, member: typing.Optional[dict], year: int) -> typing.Tuple[int, int]:
        """Haalt (bezocht_in_jaar, totaal_in_jaar) op uit Frappe 'Beheer events'."""
        year_str = str(year)
        total_year_events = 0
        attended_year_events = 0
        attended_names = set()

        if member and member.get("custom_events"):
            for item in member.get("custom_events"):
                event_name = item.get("event_bezocht") or ""
                if event_name:
                    attended_names.add(event_name.strip())
                    if year_str in event_name:
                        attended_year_events += 1

        if self.Frappeclient:
            try:
                docs = self.Frappeclient.get_list(
                    'Beheer events',
                    fields=['event_name', 'name'],
                    filters={'afgelopen': 1},
                    limit_page_length=200
                )
                if docs:
                    for doc in docs:
                        ev_name = (doc.get('event_name') or doc.get('name') or '').strip()
                        if ev_name and year_str in ev_name:
                            total_year_events += 1
                            if ev_name in attended_names and attended_year_events == 0:
                                attended_year_events += 1
            except Exception:
                pass

        return attended_year_events, max(total_year_events, attended_year_events)

    def get_frappe_member_data(self, member_obj: discord.Member):
        """Haalt member data op, maar alleen als de gebruiker daadwerkelijk de actieve Lid/SZG+ rol heeft."""
        if not self.is_member(member_obj) or not self.Frappeclient:
            return None

        try:
            docs = self.Frappeclient.get_list('Member', fields=['name'], filters={'discord_id': str(member_obj.id)})
            if docs:
                return self.Frappeclient.get_doc("Member", docs[0]['name'])
        except Exception as e:
            print(f"[UserCard] Fout bij ophalen data: {e}. Probeer opnieuw in te loggen...")
            try:
                if self.api_key and self.api_secret:
                    self.Frappeclient.login(self.api_key, self.api_secret)
                    docs = self.Frappeclient.get_list('Member', fields=['name'], filters={'discord_id': str(member_obj.id)})
                    if docs:
                        return self.Frappeclient.get_doc("Member", docs[0]['name'])
            except Exception as e2:
                print(f"[UserCard] Herstel mislukt: {e2}")

        return None

    def align_text_center(
        self,
        draw: ImageDraw.Draw,
        xy: typing.Tuple[int, int, int, int],
        text: str,
        fill: typing.Optional[typing.Tuple[int, int, int, typing.Optional[int]]],
        font: ImageFont.ImageFont,
    ) -> typing.Tuple[int, int]:
        x1, y1, x2, y2 = xy
        text_size = font.getbbox(text)
        x = int((x2 - x1 - text_size[2]) / 2)
        x = max(x, 0)
        y = int((y2 - y1 - text_size[3]) / 2)
        y = max(y, 0)
        if font in self.bold_font.values():
            y -= 5
        draw.text((x1 + x, y1 + y), text=text, fill=fill, font=font)
        return text_size

    def draw_locked_placeholder(
        self,
        draw: ImageDraw.Draw,
        xy: typing.Tuple[int, int, int, int],
        text: str = "Lidmaatschap vereist",
        font: typing.Optional[ImageFont.ImageFont] = None,
        fill: typing.Tuple[int, int, int] = (140, 145, 155),
    ) -> None:
        """Tekent een scherp vector slot-icoon inclusief tekst voor niet-leden."""
        use_font = font or self.font[30]
        x1, y1, x2, y2 = xy

        bbox = use_font.getbbox(text)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]

        lock_w = 18
        lock_h = 22
        gap = 10

        total_w = lock_w + gap + text_w
        start_x = x1 + int((x2 - x1 - total_w) / 2)
        center_y = y1 + int((y2 - y1) / 2)

        lock_x = start_x
        lock_y = center_y - int(lock_h / 2)

        # Slotbeugel
        draw.arc(
            (lock_x + 3, lock_y, lock_x + lock_w - 3, lock_y + 14),
            start=180,
            end=0,
            fill=fill,
            width=3,
        )
        # Slotkast
        draw.rounded_rectangle(
            (lock_x, lock_y + 8, lock_x + lock_w, lock_y + lock_h),
            radius=3,
            fill=fill,
        )
        # Sleutelgat
        draw.rectangle(
            (lock_x + 8, lock_y + 12, lock_x + 10, lock_y + 16),
            fill=(24, 26, 27),
        )

        # Tekst
        text_x = start_x + lock_w + gap
        text_y = center_y - int(text_h / 2)
        if use_font in self.bold_font.values():
            text_y -= 5
        draw.text((text_x, text_y), text=text, fill=fill, font=use_font)

    def remove_unprintable_characters(self, text: str) -> str:
        return (
            "".join(
                [
                    char
                    for char in text
                    if ord(char) in self.font_to_remove_unprintable_characters.getBestCmap()
                    and char.isascii()
                ]
            )
            .strip()
            .strip("-|_")
            .strip()
        )

    def _generate_prefix_image(
        self,
        _object: discord.Member,
        size: typing.Tuple[int, int],
        to_file: bool,
        _object_display: typing.Optional[bytes],
    ) -> typing.Union[Image.Image, discord.File]:
        img: Image.Image = Image.new("RGBA", size, (0, 0, 0, 0))
        try:
            image = Image.open(self.icons["background"]).convert("RGBA").resize(size)
            mask = Image.new("L", size, 0)
            d = ImageDraw.Draw(mask)
            d.rounded_rectangle((0, 0, size[0], size[1]), radius=50, fill=255)
            img.paste(image, (0, 0), mask=mask)
        except Exception as e:
            print(f"Failed to load background: {e}")
            draw_bg = ImageDraw.Draw(img)
            draw_bg.rounded_rectangle((0, 0, img.width, img.height), radius=50, fill=(32, 34, 37))

        draw: ImageDraw.ImageDraw = ImageDraw.Draw(img)
        align_text_center = functools.partial(self.align_text_center, draw)

        member = self.get_frappe_member_data(_object)

        if _object_display:
            try:
                image = Image.open(io.BytesIO(_object_display)).resize((140, 140))
                mask = Image.new("L", image.size, 0)
                d = ImageDraw.Draw(mask)
                d.rounded_rectangle((0, 0, image.width, image.height), radius=20, fill=255)
                try:
                    img.paste(image, (30, 478, 170, 618), mask=ImageChops.multiply(mask, image.split()[3]))
                except IndexError:
                    img.paste(image, (30, 478, 170, 618), mask=mask)
            except Exception:
                pass

        name_clean = self.remove_unprintable_characters(_object.display_name) or _object.name
        draw.text((190, 478), text=name_clean, fill=(255, 255, 255), font=self.bold_font[50])

        if member and member.get('custom_status') == 'Actief':
            role_text = member.get('membership_type') or 'Lid'
        else:
            role_text = 'Gast'

        draw.text((190, 553), text=role_text, fill=(163, 163, 163), font=self.font[54])

        try:
            image = Image.open(self.icons["logo"]).resize((55, 55))
            img.paste(image, (30, 30, 85, 85), mask=image.split()[3])
        except Exception:
            pass

        draw.text((105, 30), text='Shadowzone Gaming', fill=(163, 163, 163), font=self.font[54])

        # `created_on`
        draw.rounded_rectangle((1200, 75, 1545, 175), radius=15, fill=(47, 49, 54))
        align_text_center(
            (1200, 75, 1545, 175),
            text=_object.created_at.strftime("%d %B %Y"),
            fill=(255, 255, 255),
            font=self.font[36],
        )
        draw.rounded_rectangle((1220, 30, 1476, 90), radius=15, fill=(79, 84, 92))
        align_text_center((1220, 30, 1476, 90), text="Op Discord", fill=(255, 255, 255), font=self.bold_font[30])

        # `joined_on`
        draw.rounded_rectangle((1200 + 365, 75, 1545 + 365, 175), radius=15, fill=(47, 49, 54))
        align_text_center(
            (1200 + 365, 75, 1545 + 365, 175),
            text=_object.joined_at.strftime("%d %B %Y"),
            fill=(255, 255, 255),
            font=self.font[36],
        )
        draw.rounded_rectangle((1220 + 365, 30, 1476 + 365, 90), radius=15, fill=(79, 84, 92))
        align_text_center((1220 + 365, 30, 1476 + 365, 90), text="In server", fill=(255, 255, 255), font=self.bold_font[30])

        if not to_file:
            return img
        buffer = io.BytesIO()
        img.save(buffer, format="png", optimize=True)
        buffer.seek(0)
        return discord.File(buffer, filename="image.png")

    async def generate_prefix_image(
        self,
        _object: discord.Member,
        size: typing.Tuple[int, int] = (1942, 1026),
        to_file: bool = True,
    ) -> typing.Union[Image.Image, discord.File]:
        return await asyncio.to_thread(
            self._generate_prefix_image,
            _object=_object,
            size=size,
            to_file=to_file,
            _object_display=((await _object.display_avatar.read()) if isinstance(_object, discord.Member) else None),
        )

    def _generate_image(
        self,
        _object: discord.Member,
        to_file: bool,
        img: Image.Image,
    ) -> typing.Optional[typing.Union[Image.Image, discord.File]]:
        draw: ImageDraw.ImageDraw = ImageDraw.Draw(img)
        align_text_center = functools.partial(self.align_text_center, draw)

        if isinstance(_object, discord.Member):
            member = self.get_frappe_member_data(_object)
            is_active_member = (member is not None)

            # 1. Bovenste Kaart: Lidmaatschap
            draw.rounded_rectangle((1306 - 125, 204, 1912, 585), radius=15, fill=(47, 49, 54))
            align_text_center((1325 - 125, 214, 1325 - 125, 284), text="Lidmaatschap", fill=(255, 255, 255), font=self.bold_font[40])
            try:
                image = Image.open(self.icons["person"]).resize((70, 70))
                img.paste(image, (1822, 214, 1892, 284), mask=image.split()[3])
            except Exception:
                pass

            # Rij 1: Lid
            draw.rounded_rectangle((1325 - 125, 301, 1892, 418), radius=15, fill=(32, 34, 37))
            draw.rounded_rectangle((1325 - 125, 301, 1588 - 125, 418), radius=15, fill=(24, 26, 27))
            align_text_center((1326 - 125, 301, 1601 - 125, 418), text="Lid", fill=(255, 255, 255), font=self.bold_font[36])

            if is_active_member:
                if member.get('custom_start_lidmaatschap') and member.get('custom_status') == 'Actief' and member.get('membership_type') == 'Lid':
                    lid_datum = datetime.strptime(member.get('custom_start_lidmaatschap'), '%Y-%m-%d').strftime('%d %B %Y')
                else:
                    lid_datum = "-"
                align_text_center((1601 - 125, 301, 1892, 418), text=lid_datum, fill=(255, 255, 255), font=self.font[36])
            else:
                self.draw_locked_placeholder(draw, (1601 - 125, 301, 1892, 418))

            # Rij 2: Betrokken
            draw.rounded_rectangle((1325 - 125, 448, 1892, 565), radius=15, fill=(32, 34, 37))
            draw.rounded_rectangle((1325 - 125, 448, 1601 - 125, 565), radius=15, fill=(24, 26, 27))
            align_text_center((1325 - 125, 448, 1601 - 125, 565), text="Betrokken", fill=(255, 255, 255), font=self.bold_font[30])

            if is_active_member:
                betrokken_datum = datetime.strptime(member.get('custom_begin_datum'), '%Y-%m-%d').strftime('%d %B %Y') if member.get('custom_begin_datum') else "-"
                align_text_center((1601 - 125, 448, 1892, 565), text=betrokken_datum, fill=(255, 255, 255), font=self.font[36])
            else:
                self.draw_locked_placeholder(draw, (1601 - 125, 448, 1892, 565))

            # 2. Onderste Kaart: Events
            events = 0
            highest_event_value = 0
            attended_events_set = set()

            if is_active_member and member.get("custom_events"):
                for item in member.get("custom_events"):
                    event_name = item.get('event_bezocht') or ''
                    if event_name and event_name not in ('Qmusic Foute Party: 24 - 26 juni 2022', 'Vakantie: 11-18 augustus 2023'):
                        events += 1
                        try:
                            event_value = int(event_name.split()[1].strip(":"))
                            attended_events_set.add(event_value)
                            if event_value > highest_event_value:
                                highest_event_value = event_value
                        except (IndexError, ValueError):
                            continue

            draw.rounded_rectangle((1306 - 125, 615, 1912, 996), radius=15, fill=(47, 49, 54))
            align_text_center((1326 - 125, 625, 1326 - 125, 695), text="Events", fill=(255, 255, 255), font=self.bold_font[40])
            try:
                image = Image.open(self.icons["game"]).resize((70, 70))
                img.paste(image, (1822, 625, 1892, 695), mask=image.split()[3])
            except Exception:
                pass

            # Row 1: Totaal
            draw.rounded_rectangle((1326 - 125, 712, 1892, 829), radius=15, fill=(32, 34, 37))
            draw.rounded_rectangle((1326 - 125, 712, 1601 - 125, 829), radius=15, fill=(24, 26, 27))
            align_text_center((1326 - 125, 712, 1601 - 125, 829), text="Totaal", fill=(255, 255, 255), font=self.bold_font[36])

            if is_active_member:
                align_text_center((1601 - 125, 712, 1892, 829), text=str(events), fill=(255, 255, 255), font=self.font[36])
            else:
                self.draw_locked_placeholder(draw, (1601 - 125, 712, 1892, 829))

            # Row 2: Laatste Event + 10 Bolletjes
            draw.rounded_rectangle((1326 - 125, 859, 1892, 976), radius=15, fill=(32, 34, 37))
            draw.rounded_rectangle((1326 - 125, 859, 1601 - 125, 976), radius=15, fill=(24, 26, 27))
            align_text_center((1326 - 125, 859, 1601 - 125, 976), text="Laatste", fill=(255, 255, 255), font=self.bold_font[36])

            if is_active_member:
                last_event_str = f"Event {highest_event_value}" if highest_event_value > 0 else "-"
                align_text_center((1601 - 125, 863, 1892, 915), text=last_event_str, fill=(255, 255, 255), font=self.bold_font[30])
            else:
                self.draw_locked_placeholder(draw, (1601 - 125, 863, 1892, 915), font=self.font[28])

            latest_global_event = max(self.get_latest_event_number(highest_event_value), highest_event_value, 10)
            last_10_events = list(range(latest_global_event - 9, latest_global_event + 1))

            dot_diameter = 14
            dot_spacing = 26
            total_dots_w = (9 * dot_spacing) + dot_diameter
            start_dot_x = 1684 - int(total_dots_w / 2)
            dot_y = 932

            for k, ev_num in enumerate(last_10_events):
                dx1 = start_dot_x + (k * dot_spacing)
                dy1 = dot_y
                dx2 = dx1 + dot_diameter
                dy2 = dy1 + dot_diameter
                if is_active_member and ev_num in attended_events_set:
                    draw.ellipse((dx1, dy1, dx2, dy2), fill=(255, 5, 2))
                else:
                    draw.ellipse((dx1, dy1, dx2, dy2), fill=(47, 49, 54), outline=(79, 84, 92), width=2)

            if not to_file:
                return img
            buffer = io.BytesIO()
            img.save(buffer, format="png", optimize=True)
            buffer.seek(0)
            return discord.File(buffer, filename="image.png")

        return None

    async def generate_image(
        self,
        _object: discord.Member,
        to_file: bool = True,
    ) -> typing.Optional[typing.Union[Image.Image, discord.File]]:
        img: Image.Image = await self.generate_prefix_image(_object, size=(1942, 1096), to_file=False)
        return await asyncio.to_thread(self._generate_image, _object, to_file=to_file, img=img)

    # --- 30-DAGEN DASHBOARD ---
    def _generate_stats_image(
        self,
        _object: discord.Member,
        to_file: bool,
        stats: dict,
        _object_display: typing.Optional[bytes],
    ) -> typing.Union[Image.Image, discord.File]:
        size = (1942, 1096)
        img = Image.new("RGBA", size, (0, 0, 0, 0))

        try:
            bg_image = Image.open(self.icons["background"]).convert("RGBA").resize(size)
            mask = Image.new("L", size, 0)
            d = ImageDraw.Draw(mask)
            d.rounded_rectangle((0, 0, size[0], size[1]), radius=50, fill=255)
            img.paste(bg_image, (0, 0), mask=mask)
        except Exception:
            draw_bg = ImageDraw.Draw(img)
            draw_bg.rounded_rectangle((0, 0, size[0], size[1]), radius=50, fill=(32, 34, 37))

        draw = ImageDraw.Draw(img)
        align_text_center = functools.partial(self.align_text_center, draw)

        if _object_display:
            try:
                avatar = Image.open(io.BytesIO(_object_display)).resize((140, 140))
                mask_av = Image.new("L", avatar.size, 0)
                d_av = ImageDraw.Draw(mask_av)
                d_av.rounded_rectangle((0, 0, avatar.width, avatar.height), radius=20, fill=255)
                try:
                    img.paste(avatar, (60, 45, 200, 185), mask=ImageChops.multiply(mask_av, avatar.split()[3]))
                except IndexError:
                    img.paste(avatar, (60, 45, 200, 185), mask=mask_av)
            except Exception:
                pass

        name_str = self.remove_unprintable_characters(_object.display_name) or _object.name
        draw.text((225, 45), text=name_str, fill=(255, 255, 255), font=self.bold_font[50])

        persona_str = f"Voice Persona: {stats.get('persona', 'Stille Luisteraar')}"
        persona_w = self.bold_font[30].getbbox(persona_str)[2]
        draw.rounded_rectangle((225, 120, 245 + persona_w + 20, 180), radius=12, fill=(255, 5, 2))
        draw.text((235, 130), text=persona_str, fill=(255, 255, 255), font=self.bold_font[30])

        try:
            logo = Image.open(self.icons["logo"]).resize((55, 55))
            img.paste(logo, (1320, 50, 1375, 105), mask=logo.split()[3])
        except Exception:
            pass
        draw.text((1390, 50), text="Shadowzone Gaming", fill=(163, 163, 163), font=self.font[54])

        # BOX 1 (TOP LINKS): VOICE STATUS & SERVER RANG
        draw.rounded_rectangle((60, 204, 940, 585), radius=15, fill=(47, 49, 54))
        align_text_center((80, 214, 920, 284), text="Voice Status & Rang", fill=(255, 255, 255), font=self.bold_font[40])
        try:
            icon_p = Image.open(self.icons["person"]).resize((65, 65))
            img.paste(icon_p, (855, 214), mask=icon_p.split()[3])
        except Exception:
            pass

        draw.rounded_rectangle((80, 301, 920, 418), radius=15, fill=(32, 34, 37))
        draw.rounded_rectangle((80, 301, 380, 418), radius=15, fill=(24, 26, 27))
        align_text_center((80, 301, 380, 418), text="Rang", fill=(255, 255, 255), font=self.bold_font[36])
        align_text_center((380, 301, 920, 418), text=stats.get("rank_str", "-"), fill=(255, 255, 255), font=self.bold_font[36])

        draw.rounded_rectangle((80, 448, 920, 565), radius=15, fill=(32, 34, 37))
        draw.rounded_rectangle((80, 448, 380, 565), radius=15, fill=(24, 26, 27))
        align_text_center((80, 448, 380, 565), text="Totaal", fill=(255, 255, 255), font=self.bold_font[30])
        align_text_center((380, 448, 920, 565), text=f"{stats.get('total_hours', 0)} Uur", fill=(255, 255, 255), font=self.font[36])

        # BOX 2 (BOTTOM LINKS): TIJDSBESTEDING
        draw.rounded_rectangle((60, 615, 940, 996), radius=15, fill=(47, 49, 54))
        align_text_center((80, 625, 920, 695), text="Tijdsbesteding", fill=(255, 255, 255), font=self.bold_font[40])
        try:
            icon_g = Image.open(self.icons["game"]).resize((65, 65))
            img.paste(icon_g, (855, 625), mask=icon_g.split()[3])
        except Exception:
            pass

        draw.rounded_rectangle((80, 712, 920, 829), radius=15, fill=(32, 34, 37))
        draw.rounded_rectangle((80, 712, 430, 829), radius=15, fill=(24, 26, 27))
        align_text_center((80, 712, 430, 829), text="Gemiddelde", fill=(255, 255, 255), font=self.bold_font[36])
        align_text_center((430, 712, 920, 829), text=stats.get("daily_avg_str", "-"), fill=(255, 255, 255), font=self.font[36])

        draw.rounded_rectangle((80, 859, 920, 976), radius=15, fill=(32, 34, 37))
        draw.rounded_rectangle((80, 859, 430, 976), radius=15, fill=(24, 26, 27))
        align_text_center((80, 859, 430, 976), text="Weekend Aandeel", fill=(255, 255, 255), font=self.bold_font[30])
        align_text_center((430, 859, 920, 976), text=f"{stats.get('weekend_pct', 0)}% van voice tijd", fill=(255, 255, 255), font=self.font[36])

        # BOX 3 (TOP RECHTS): GEWOONTES & PIEKTIJD
        draw.rounded_rectangle((1000, 204, 1880, 585), radius=15, fill=(47, 49, 54))
        align_text_center((1020, 214, 1860, 284), text="Gewoontes & Piektijd", fill=(255, 255, 255), font=self.bold_font[40])

        draw.rounded_rectangle((1020, 301, 1860, 418), radius=15, fill=(32, 34, 37))
        draw.rounded_rectangle((1020, 301, 1370, 418), radius=15, fill=(24, 26, 27))
        align_text_center((1020, 301, 1370, 418), text="Piekuur", fill=(255, 255, 255), font=self.bold_font[36])
        align_text_center((1370, 301, 1860, 418), text=stats.get("peak_time", "-"), fill=(255, 255, 255), font=self.font[36])

        draw.rounded_rectangle((1020, 448, 1860, 565), radius=15, fill=(32, 34, 37))
        draw.rounded_rectangle((1020, 448, 1370, 565), radius=15, fill=(24, 26, 27))
        align_text_center((1020, 448, 1370, 565), text="Patroon", fill=(255, 255, 255), font=self.bold_font[30])
        align_text_center((1370, 448, 1860, 565), text=stats.get("activity_label", "-"), fill=(255, 255, 255), font=self.font[36])

        # BOX 4 (BOTTOM RECHTS): WEKELIJKSE ACTIVITEIT
        draw.rounded_rectangle((1000, 615, 1880, 996), radius=15, fill=(47, 49, 54))
        align_text_center((1020, 625, 1860, 695), text="Wekelijke Activiteit", fill=(255, 255, 255), font=self.bold_font[40])
        draw.rounded_rectangle((1020, 712, 1860, 976), radius=15, fill=(32, 34, 37))

        day_labels = ["Ma", "Di", "Wo", "Do", "Vr", "Za", "Zo"]
        norms = stats.get("weekday_norm", [0] * 7)
        hours = stats.get("weekday_hours", [0] * 7)
        base_x = 1060
        max_bar_height = 135

        for i in range(7):
            bx = base_x + (i * 110)
            val = norms[i] if i < len(norms) else 0
            bar_h = max(int(val * max_bar_height), 8) if stats.get("total_minutes", 0) > 0 else 8
            is_peak = (val == 1.0 and stats.get("total_minutes", 0) > 0)

            bar_color = (255, 5, 2) if is_peak else (79, 84, 92)
            draw.rounded_rectangle((bx, 905 - bar_h, bx + 65, 905), radius=6, fill=bar_color)

            lbl = day_labels[i]
            lbl_box = self.bold_font[30].getbbox(lbl)
            lbl_x = bx + int((65 - (lbl_box[2] - lbl_box[0])) / 2)
            draw.text((lbl_x, 920), text=lbl, fill=(255, 255, 255) if is_peak else (160, 160, 160), font=self.bold_font[30])

            if hours[i] > 0:
                h_str = f"{hours[i]}u"
                h_box = self.font[28].getbbox(h_str)
                h_x = bx + int((65 - (h_box[2] - h_box[0])) / 2)
                draw.text((h_x, 905 - bar_h - 32), text=h_str, fill=(200, 200, 200), font=self.font[28])

        draw.text((200, 1025), text="* Op basis van de afgelopen 30 dagen", fill=(150, 155, 165), font=self.font[30])

        if not to_file:
            return img
        buffer = io.BytesIO()
        img.save(buffer, format="png", optimize=True)
        buffer.seek(0)
        return discord.File(buffer, filename="stats_image.png")

    async def generate_stats_image(
        self,
        _object: discord.Member,
        to_file: bool = True,
    ) -> typing.Union[discord.File, str]:
        api_tokens = await self.bot.get_shared_api_tokens("statbot")
        api_key = api_tokens.get("api_key", "")

        client = StatbotClient(api_key=api_key)
        stats = await client.get_user_voice_stats(_object.guild.id, _object.id, days=30)
        await client.close()

        total_minutes = stats.get("total_minutes", 0)
        if total_minutes < 60:
            needed = 60 - total_minutes
            return f"⏳ **Nog {needed} {'minuut' if needed == 1 else 'minuten'}** in voice om dit te ontgrendelen! *(Minimaal 1 uur activiteit vereist in de afgelopen 30 dagen)*"

        avatar_bytes = await _object.display_avatar.read()
        return await asyncio.to_thread(
            self._generate_stats_image,
            _object,
            to_file=to_file,
            stats=stats,
            _object_display=avatar_bytes,
        )

    # --- WRAPPED JAAROVERZICHT DASHBOARD ---
    def _generate_wrapped_image(
        self,
        _object: discord.Member,
        to_file: bool,
        stats: dict,
        _object_display: typing.Optional[bytes],
        attended_events: int,
        total_events: int,
        is_frappe_member: bool,
    ) -> typing.Union[Image.Image, discord.File]:
        size = (1942, 1096)
        img = Image.new("RGBA", size, (0, 0, 0, 0))

        try:
            bg_image = Image.open(self.icons["background"]).convert("RGBA").resize(size)
            mask = Image.new("L", size, 0)
            d = ImageDraw.Draw(mask)
            d.rounded_rectangle((0, 0, size[0], size[1]), radius=50, fill=255)
            img.paste(bg_image, (0, 0), mask=mask)
        except Exception:
            draw_bg = ImageDraw.Draw(img)
            draw_bg.rounded_rectangle((0, 0, size[0], size[1]), radius=50, fill=(32, 34, 37))

        draw = ImageDraw.Draw(img)
        align_text_center = functools.partial(self.align_text_center, draw)

        year = stats.get("year", datetime.now().year - 1)

        # 1. Header: Avatar
        if _object_display:
            try:
                avatar = Image.open(io.BytesIO(_object_display)).resize((140, 140))
                mask_av = Image.new("L", avatar.size, 0)
                d_av = ImageDraw.Draw(mask_av)
                d_av.rounded_rectangle((0, 0, avatar.width, avatar.height), radius=20, fill=255)
                try:
                    img.paste(avatar, (60, 45, 200, 185), mask=ImageChops.multiply(mask_av, avatar.split()[3]))
                except IndexError:
                    img.paste(avatar, (60, 45, 200, 185), mask=mask_av)
            except Exception:
                pass

        # 2. Header: Username & Wrapped Title Badge
        name_str = self.remove_unprintable_characters(_object.display_name) or _object.name
        draw.text((225, 45), text=name_str, fill=(255, 255, 255), font=self.bold_font[50])

        badge_str = f"Wrapped {year}: {stats.get('persona', 'Gezelligheidsdier')}"
        badge_w = self.bold_font[30].getbbox(badge_str)[2]
        draw.rounded_rectangle((225, 120, 245 + badge_w + 20, 180), radius=12, fill=(255, 5, 2))
        draw.text((235, 130), text=badge_str, fill=(255, 255, 255), font=self.bold_font[30])

        # 3. Header: Server Logo & Wrapped Jaar
        try:
            logo = Image.open(self.icons["logo"]).resize((55, 55))
            img.paste(logo, (1320, 50, 1375, 105), mask=logo.split()[3])
        except Exception:
            pass
        draw.text((1390, 50), text=f"WRAPPED {year}", fill=(255, 5, 2), font=self.bold_font[50])

        # --- BOX 1 (TOP LINKS): JAARPRESTATIES ---
        draw.rounded_rectangle((60, 204, 940, 585), radius=15, fill=(47, 49, 54))
        align_text_center((80, 214, 920, 284), text=f"Jaarprestaties {year}", fill=(255, 255, 255), font=self.bold_font[40])
        try:
            icon_p = Image.open(self.icons["person"]).resize((65, 65))
            img.paste(icon_p, (855, 214), mask=icon_p.split()[3])
        except Exception:
            pass

        draw.rounded_rectangle((80, 301, 920, 418), radius=15, fill=(32, 34, 37))
        draw.rounded_rectangle((80, 301, 380, 418), radius=15, fill=(24, 26, 27))
        align_text_center((80, 301, 380, 418), text="Jaarrang", fill=(255, 255, 255), font=self.bold_font[36])
        align_text_center((380, 301, 920, 418), text=stats.get("rank_str", "-"), fill=(255, 255, 255), font=self.bold_font[36])

        # Row 2: Totaal VC in Dagen
        draw.rounded_rectangle((80, 448, 920, 565), radius=15, fill=(32, 34, 37))
        draw.rounded_rectangle((80, 448, 380, 565), radius=15, fill=(24, 26, 27))
        align_text_center((80, 448, 380, 565), text="Totaal VC", fill=(255, 255, 255), font=self.bold_font[30])

        total_days = stats.get('total_days_vc', 0)
        total_hrs = stats.get('total_hours', 0)
        prev_diff = stats.get('prev_diff_str')

        if prev_diff:
            total_vc_str = f"{total_days} Dagen ({total_hrs}u | {prev_diff})"
        else:
            total_vc_str = f"{total_days} Dagen ({total_hrs} Uur)"

        align_text_center((380, 448, 920, 565), text=total_vc_str, fill=(255, 255, 255), font=self.font[32])

        # --- BOX 2 (BOTTOM LINKS): HOOGTEPUNTEN & EVENTS ---
        draw.rounded_rectangle((60, 615, 940, 996), radius=15, fill=(47, 49, 54))
        align_text_center((80, 625, 920, 695), text="Hoogtepunten & Events", fill=(255, 255, 255), font=self.bold_font[40])
        try:
            icon_g = Image.open(self.icons["game"]).resize((65, 65))
            img.paste(icon_g, (855, 625), mask=icon_g.split()[3])
        except Exception:
            pass

        draw.rounded_rectangle((80, 712, 920, 829), radius=15, fill=(32, 34, 37))
        draw.rounded_rectangle((80, 712, 430, 829), radius=15, fill=(24, 26, 27))
        align_text_center((80, 712, 430, 829), text="Marathondag", fill=(255, 255, 255), font=self.bold_font[32])
        marathon_str = f"{stats.get('marathon_hours', 0)}u op {stats.get('marathon_date', '-')}" if stats.get('marathon_hours', 0) > 0 else "-"
        align_text_center((430, 712, 920, 829), text=marathon_str, fill=(255, 255, 255), font=self.font[36])

        draw.rounded_rectangle((80, 859, 920, 976), radius=15, fill=(32, 34, 37))
        draw.rounded_rectangle((80, 859, 430, 976), radius=15, fill=(24, 26, 27))
        align_text_center((80, 859, 430, 976), text="SZG Events", fill=(255, 255, 255), font=self.bold_font[32])

        if is_frappe_member:
            event_str = f"{attended_events} van de {total_events} bezocht" if total_events > 0 else (f"{attended_events} bezocht" if attended_events > 0 else "-")
            align_text_center((430, 859, 920, 976), text=event_str, fill=(255, 255, 255), font=self.font[36])
        else:
            self.draw_locked_placeholder(draw, (430, 859, 920, 976), font=self.font[30])

        # --- BOX 3 (TOP RECHTS): RITME & SEIZOENEN ---
        draw.rounded_rectangle((1000, 204, 1880, 585), radius=15, fill=(47, 49, 54))
        align_text_center((1020, 214, 1860, 284), text="Ritme & Seizoenen", fill=(255, 255, 255), font=self.bold_font[40])

        draw.rounded_rectangle((1020, 301, 1860, 418), radius=15, fill=(32, 34, 37))
        draw.rounded_rectangle((1020, 301, 1370, 418), radius=15, fill=(24, 26, 27))
        align_text_center((1020, 301, 1370, 418), text="Actieve Dagen", fill=(255, 255, 255), font=self.bold_font[30])
        active_str = f"{stats.get('active_days_count', 0)} van {stats.get('total_days_in_year', 365)} ({stats.get('active_pct', 0)}%)"
        align_text_center((1370, 301, 1860, 418), text=active_str, fill=(255, 255, 255), font=self.font[36])

        draw.rounded_rectangle((1020, 448, 1860, 565), radius=15, fill=(32, 34, 37))
        draw.rounded_rectangle((1020, 448, 1370, 565), radius=15, fill=(24, 26, 27))
        align_text_center((1020, 448, 1370, 565), text="Piekdag & Seizoen", fill=(255, 255, 255), font=self.bold_font[30])
        combo_str = f"{stats.get('peak_weekday', '-')} | {stats.get('top_season', '-')}"
        align_text_center((1370, 448, 1860, 565), text=combo_str, fill=(255, 255, 255), font=self.font[36])

        # --- BOX 4 (BOTTOM RECHTS): 12-MAANDEN GRAFIEK ---
        draw.rounded_rectangle((1000, 615, 1880, 996), radius=15, fill=(47, 49, 54))
        align_text_center((1020, 625, 1860, 695), text=f"Maandelijkse Activiteit ({year})", fill=(255, 255, 255), font=self.bold_font[40])
        draw.rounded_rectangle((1020, 712, 1860, 976), radius=15, fill=(32, 34, 37))

        months = ["Jan", "Feb", "Mrt", "Apr", "Mei", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dec"]
        m_norms = stats.get("month_norm", [0] * 12)
        m_hours = stats.get("month_hours", [0] * 12)

        start_x = 1050
        bar_w = 44
        gap = 22
        max_bar_h = 135

        for i in range(12):
            bx = start_x + (i * (bar_w + gap))
            val = m_norms[i] if i < len(m_norms) else 0
            bar_h = max(int(val * max_bar_h), 6) if stats.get("total_minutes", 0) > 0 else 6
            is_peak = (val == 1.0 and stats.get("total_minutes", 0) > 0)

            bar_color = (255, 5, 2) if is_peak else (79, 84, 92)
            draw.rounded_rectangle((bx, 905 - bar_h, bx + bar_w, 905), radius=5, fill=bar_color)

            lbl = months[i]
            lbl_box = self.bold_font[26].getbbox(lbl)
            lbl_x = bx + int((bar_w - (lbl_box[2] - lbl_box[0])) / 2)
            draw.text((lbl_x, 920), text=lbl, fill=(255, 255, 255) if is_peak else (160, 160, 160), font=self.bold_font[26])

            if m_hours[i] > 0:
                h_str = f"{int(round(m_hours[i]))}u"
                h_box = self.font[24].getbbox(h_str)
                h_x = bx + int((bar_w - (h_box[2] - h_box[0])) / 2)
                draw.text((h_x, 905 - bar_h - 28), text=h_str, fill=(200, 200, 200), font=self.font[24])

        if not to_file:
            return img
        buffer = io.BytesIO()
        img.save(buffer, format="png", optimize=True)
        buffer.seek(0)
        return discord.File(buffer, filename="wrapped_image.png")

    async def generate_wrapped_image(
        self,
        _object: discord.Member,
        year: typing.Optional[int] = None,
        to_file: bool = True,
    ) -> typing.Union[discord.File, str]:
        target_year = year or (datetime.now().year - 1)
        api_tokens = await self.bot.get_shared_api_tokens("statbot")
        api_key = api_tokens.get("api_key", "")

        client = StatbotClient(api_key=api_key)
        stats = await client.get_user_wrapped_stats(_object.guild.id, _object.id, year=target_year)
        await client.close()

        total_minutes = stats.get("total_minutes", 0)
        if total_minutes < 60:
            return f"🔒 **Niet genoeg voice activiteit** in {target_year} om een Wrapped te ontgrendelen *(minimaal 1 uur activiteit vereist in dat jaar)*."

        member = self.get_frappe_member_data(_object)
        attended_events, total_events = self.get_frappe_year_events(member, target_year)
        avatar_bytes = await _object.display_avatar.read()

        return await asyncio.to_thread(
            self._generate_wrapped_image,
            _object,
            to_file=to_file,
            stats=stats,
            _object_display=avatar_bytes,
            attended_events=attended_events,
            total_events=total_events,
            is_frappe_member=(member is not None),
        )

    # --- COMMANDS ---
    @commands.guild_only()
    @commands.bot_has_permissions(attach_files=True)
    @commands.hybrid_command(
        name="profiel",
        aliases=["lid", "profile", "card"],
        description="Bekijk je Shadowzone profiel, statistieken en badges",
    )
    async def profiel(
        self,
        ctx: commands.Context,
        *,
        member: discord.Member = commands.Author,
    ) -> None:
        """Bekijk je serverprofiel"""
        if not member.bot:
            await usercardView(cog=self, _object=member).start(ctx, command='card')
        else:
            await ctx.send('Niet mogelijk voor bot')

    @commands.guild_only()
    @commands.bot_has_permissions(attach_files=True)
    @commands.hybrid_command(
        name="wrapped",
        description="Krijg het jaaroverzicht (Wrapped) van een gebruiker",
    )
    @discord.app_commands.describe(
        member="Het lid waarvan je de Wrapped wilt bekijken (standaard jezelf)",
        year="Het kalenderjaar (bijv. 2024, standaard het meest recente jaar)"
    )
    async def wrapped(
        self,
        ctx: commands.Context,
        member: typing.Optional[discord.Member] = None,
        year: typing.Optional[int] = None,
    ) -> None:
        """Krijg het jaaroverzicht (Wrapped) van een gebruiker"""
        target_member = member or ctx.author
        if target_member.bot:
            await ctx.send('Niet mogelijk voor bot')
            return

        current_year = datetime.now().year
        recent_wrapped_year = current_year - 1
        target_year = year or recent_wrapped_year

        # 1. Huidig / toekomstig jaar blokkeren
        if target_year >= current_year:
            await ctx.send(
                f"⚠️ Het jaar **{target_year}** is nog bezig! Je kunt een Wrapped over {target_year} pas vanaf **1 januari {target_year + 1}** bekijken.\n"
                f"*(Standaard wordt **{recent_wrapped_year}** getoond met `/wrapped`)*"
            )
            return

        # 2. Eerdere jaargangen (Archief) exclusief voor Leden / SZG+
        if target_year < recent_wrapped_year:
            if not self.is_member(target_member) or not self.is_member(ctx.author):
                await ctx.send(
                    f"🔒 Het opvragen van eerdere jaargangen (zoals **{target_year}**) is een exclusief archiefvoordeel voor **Leden** en **SZG+**!\n"
                    f"*(Gasten kunnen uitsluitend de meest recente Wrapped van **{recent_wrapped_year}** bekijken)*"
                )
                return

        await usercardView(cog=self, _object=target_member, year=target_year).start(ctx, command='wrapped', year=target_year)

    @commands.guild_only()
    @commands.bot_has_permissions(attach_files=True)
    @commands.hybrid_command(name="id", description="Krijg Discord ID van gebruiker")
    async def id(
        self,
        ctx: commands.Context,
        *,
        member: discord.Member = commands.Author,
    ) -> None:
        """Krijg Discord ID van gebruiker"""
        if not member.bot:
            await usercardView(cog=self, _object=member).start(ctx, command='id')
        else:
            await ctx.send('Niet mogelijk voor bot')