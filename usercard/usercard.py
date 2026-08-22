from AAA3A_utils import Cog  # isort:skip
from redbot.core import commands  # isort:skip
from redbot.core.bot import Red  # isort:skip
import discord  # isort:skip
import typing  # isort:skip

import asyncio
import functools
import io
from pathlib import Path
from datetime import datetime

from fontTools.ttLib import TTFont
from PIL import Image, ImageChops, ImageDraw, ImageFont
from redbot.core.data_manager import bundled_data_path
from frappeclient import FrappeClient

from .view import usercardView
from .statbot_api import StatbotClient


class usercard(Cog):
    """A cog to generate images"""

    def __init__(self, bot: Red) -> None:
        super().__init__(bot=bot)
        self.Frappeclient = None
        self.api_key = None
        self.api_secret = None

        self.font_path: Path = bundled_data_path(self) / "arial.ttf"
        self.bold_font_path: Path = bundled_data_path(self) / "arial_bold.ttf"
        self.font: typing.Dict[int, ImageFont.ImageFont] = {
            size: ImageFont.truetype(str(self.font_path), size=size)
            for size in {28, 30, 36, 40, 54}
        }
        self.bold_font: typing.Dict[int, ImageFont.ImageFont] = {
            size: ImageFont.truetype(str(self.bold_font_path), size=size)
            for size in {30, 36, 40, 50, 60}
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
        await super().cog_load()
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
        await super().cog_unload()

    def get_frappe_member_data(self, discord_id):
        """Haalt member data op en logt automatisch opnieuw in als de sessie verlopen is."""
        if not self.Frappeclient:
            return None

        try:
            docs = self.Frappeclient.get_list('Member', fields=['name'], filters={'discord_id': str(discord_id)})
            if docs:
                return self.Frappeclient.get_doc("Member", docs[0]['name'])
        except Exception as e:
            print(f"[UserCard] Fout bij ophalen data: {e}. Probeer opnieuw in te loggen...")
            try:
                if self.api_key and self.api_secret:
                    self.Frappeclient.login(self.api_key, self.api_secret)
                    docs = self.Frappeclient.get_list('Member', fields=['name'], filters={'discord_id': str(discord_id)})
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

    def get_member_display(self, member: discord.Member) -> str:
        return (
            self.remove_unprintable_characters(member.display_name)
            if (
                sum(
                    (
                        1
                        if ord(char) in self.font_to_remove_unprintable_characters.getBestCmap()
                        else 0
                    )
                    for char in member.display_name
                )
                / len(member.display_name)
                > 0.8
            )
            and len(self.remove_unprintable_characters(member.display_name)) >= 5
            else (
                self.remove_unprintable_characters(member.global_name)
                if member.global_name is not None
                and (
                    sum(
                        (
                            1
                            if ord(char)
                            in self.font_to_remove_unprintable_characters.getBestCmap()
                            else 0
                        )
                        for char in member.global_name
                    )
                    / len(member.global_name)
                    > 0.8
                )
                and len(self.remove_unprintable_characters(member.global_name)) >= 5
                else member.name
            )
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
            image = Image.open(self.icons["background"])
            image = image.convert("RGBA").resize(size)

            mask = Image.new("L", size, 0)
            d = ImageDraw.Draw(mask)
            d.rounded_rectangle((0, 0, size[0], size[1]), radius=50, fill=255)

            img.paste(image, (0, 0), mask=mask)
        except Exception as e:
            print(f"Failed to load background: {e}")
            draw_bg = ImageDraw.Draw(img)
            draw_bg.rounded_rectangle(
                (0, 0, img.width, img.height),
                radius=50,
                fill=(32, 34, 37),
            )

        draw: ImageDraw.ImageDraw = ImageDraw.Draw(img)
        align_text_center = functools.partial(self.align_text_center, draw)

        member = self.get_frappe_member_data(_object.id)

        if member:
            image = Image.open(io.BytesIO(_object_display))
            image = image.resize((140, 140))
            mask = Image.new("L", image.size, 0)
            d = ImageDraw.Draw(mask)
            d.rounded_rectangle(
                (0, 0, image.width, image.height),
                radius=20,
                fill=255,
            )
            try:
                img.paste(
                    image, (30, 478, 170, 618), mask=ImageChops.multiply(mask, image.split()[3])
                )
            except IndexError:
                img.paste(image, (30, 478, 170, 618), mask=mask)
            if (
                sum(
                    (
                        1
                        if ord(char) in self.font_to_remove_unprintable_characters.getBestCmap()
                        else 0
                    )
                    for char in _object.display_name
                )
                / len(_object.display_name)
                > 0.8
            ) and len(self.remove_unprintable_characters(_object.display_name)) >= 5:
                draw.text(
                    (190, 478),
                    text=self.remove_unprintable_characters(_object.display_name),
                    fill=(255, 255, 255),
                    font=self.bold_font[50],
                )
                display_name_size = self.bold_font[50].getbbox(_object.display_name)
                if (
                    display_name_size[2]
                    + 25
                    + self.font[40].getbbox(_object.global_name or _object.name)[2]
                ) <= 1000:
                    draw.text(
                        (190 + display_name_size[2] + 25, 496),
                        text=(
                            self.remove_unprintable_characters(_object.global_name)
                            if _object.global_name is not None
                            else _object.name
                        ),
                        fill=(163, 163, 163),
                        font=self.font[40],
                    )
            elif (
                _object.global_name is not None
                and (
                    sum(
                        (
                            1
                            if ord(char)
                            in self.font_to_remove_unprintable_characters.getBestCmap()
                            else 0
                        )
                        for char in _object.global_name
                    )
                    / len(_object.global_name)
                    > 0.8
                )
                and len(self.remove_unprintable_characters(_object.global_name)) >= 5
            ):
                draw.text(
                    (190, 478),
                    text=self.remove_unprintable_characters(_object.global_name),
                    fill=(255, 255, 255),
                    font=self.bold_font[50],
                )
            else:
                draw.text(
                    (190, 478), text=_object.name, fill=(255, 255, 255), font=self.bold_font[50]
                )

            # Rol
            draw.text(
                (190, 553),
                text=f"{member.get('membership_type') if member.get('custom_status') == 'Actief' else ''}",
                fill=(163, 163, 163),
                font=self.font[54],
            )

            # Guild name & Guild icon.
            image = Image.open(self.icons["logo"])
            image = image.resize((55, 55))
            img.paste(image, (30, 30, 85, 85), mask=image.split()[3])
            draw.text(
                (105, 30),
                text='Shadowzone Gaming',
                fill=(163, 163, 163),
                font=self.font[54],
            )

            # `created_on`
            draw.rounded_rectangle((1200, 75, 1545, 175), radius=15, fill=(47, 49, 54))
            align_text_center(
                (1200, 75, 1545, 175),
                text=_object.created_at.strftime("%d %B %Y"),
                fill=(255, 255, 255),
                font=self.font[36],
            )
            draw.rounded_rectangle((1220, 30, 1476, 90), radius=15, fill=(79, 84, 92))
            align_text_center(
                (1220, 30, 1476, 90),
                text="Op Discord",
                fill=(255, 255, 255),
                font=self.bold_font[30],
            )
            # `joined_on`
            draw.rounded_rectangle((1200 + 365, 75, 1545 + 365, 175), radius=15, fill=(47, 49, 54))
            align_text_center(
                (1200 + 365, 75, 1545 + 365, 175),
                text=_object.joined_at.strftime("%d %B %Y"),
                fill=(255, 255, 255),
                font=self.font[36],
            )
            draw.rounded_rectangle((1220 + 365, 30, 1476 + 365, 90), radius=15, fill=(79, 84, 92))
            align_text_center(
                (1220 + 365, 30, 1476 + 365, 90),
                text="In server",
                fill=(255, 255, 255),
                font=self.bold_font[30],
            )

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
        if isinstance(_object, typing.Tuple):
            _object, _type = _object
        else:
            _type = None
        return await asyncio.to_thread(
            self._generate_prefix_image,
            _object=_object if _type is None else (_object, _type),
            size=size,
            to_file=to_file,
            _object_display=(
                (await _object.display_avatar.read())
                if isinstance(_object, discord.Member)
                else (
                    (await _object.display_icon.read())
                    if isinstance(_object, discord.Role) and _object.display_icon is not None
                    else None
                )
            ),
        )

    def _generate_image(
        self,
        _object: discord.Member,
        to_file: bool,
        img: Image.Image,
    ) -> typing.Optional[typing.Union[Image.Image, discord.File]]:
        draw: ImageDraw.ImageDraw = ImageDraw.Draw(img)
        align_text_center = functools.partial(self.align_text_center, draw)

        if isinstance(_object, (discord.Member)):
            member = self.get_frappe_member_data(_object.id)

            if member:
                draw.rounded_rectangle((1306 - 125, 204, 1912, 585), radius=15, fill=(47, 49, 54))
                align_text_center(
                    (1325 - 125, 214, 1325 - 125, 284),
                    text="Lidmaatschap",
                    fill=(255, 255, 255),
                    font=self.bold_font[40],
                )
                image = Image.open(self.icons["person"])
                image = image.resize((70, 70))
                img.paste(image, (1822, 214, 1892, 284), mask=image.split()[3])
                draw.rounded_rectangle((1325 - 125, 301, 1892, 418), radius=15, fill=(32, 34, 37))
                draw.rounded_rectangle((1325 - 125, 301, 1588 - 125, 418), radius=15, fill=(24, 26, 27))
                align_text_center(
                    (1326 - 125, 301, 1601 - 125, 418),
                    text="Lid",
                    fill=(255, 255, 255),
                    font=self.bold_font[36],
                )
                align_text_center(
                    (1601 - 125, 301, 1892, 418),
                    text=f"{datetime.strptime(member.get('custom_start_lidmaatschap'), '%Y-%m-%d').strftime('%d %B %Y') if member.get('custom_start_lidmaatschap') and member.get('custom_status') == 'Actief' and member.get('membership_type') == 'Lid' else '-'}",
                    fill=(255, 255, 255),
                    font=self.font[36],
                )
                draw.rounded_rectangle((1325 - 125, 448, 1892, 565), radius=15, fill=(32, 34, 37))
                draw.rounded_rectangle((1325 - 125, 448, 1601 - 125, 565), radius=15, fill=(24, 26, 27))
                align_text_center(
                    (1325 - 125, 448, 1601 - 125, 565),
                    text="Betrokken",
                    fill=(255, 255, 255),
                    font=self.bold_font[30],
                )
                align_text_center(
                    (1601 - 125, 448, 1892, 565),
                    text=f"{datetime.strptime(member.get('custom_begin_datum'), '%Y-%m-%d').strftime('%d %B %Y') if member.get('custom_begin_datum') else '-'}",
                    fill=(255, 255, 255),
                    font=self.font[36],
                )

                # Events
                events = 0
                highest_event_value = 0
                if member.get("custom_events"):
                    for item in member.get("custom_events"):
                        if item['event_bezocht'] not in ('Qmusic Foute Party: 24 - 26 juni 2022', 'Vakantie: 11-18 augustus 2023'):
                            events += 1
                            try:
                                event_value = int(item["event_bezocht"].split()[1].strip(":"))
                                if event_value > highest_event_value:
                                    highest_event_value = event_value
                            except (IndexError, ValueError):
                                continue

                draw.rounded_rectangle((1306 - 125, 615, 1912, 996), radius=15, fill=(47, 49, 54))
                align_text_center(
                    (1326 - 125, 625, 1326 - 125, 695),
                    text="Events",
                    fill=(255, 255, 255),
                    font=self.bold_font[40],
                )
                image = Image.open(self.icons["game"])
                image = image.resize((70, 70))
                img.paste(image, (1822, 625, 1892, 695), mask=image.split()[3])
                draw.rounded_rectangle((1326 - 125, 712, 1892, 829), radius=15, fill=(32, 34, 37))
                draw.rounded_rectangle((1326 - 125, 712, 1601 - 125, 829), radius=15, fill=(24, 26, 27))
                align_text_center(
                    (1326 - 125, 712, 1601 - 125, 829), text="Totaal", fill=(255, 255, 255), font=self.bold_font[36]
                )
                align_text_center(
                    (1601 - 125, 712, 1892, 829),
                    text=str(events),
                    fill=(255, 255, 255),
                    font=self.font[36],
                )
                draw.rounded_rectangle((1326 - 125, 859, 1892, 976), radius=15, fill=(32, 34, 37))
                draw.rounded_rectangle((1326 - 125, 859, 1601 - 125, 976), radius=15, fill=(24, 26, 27))
                align_text_center(
                    (1326 - 125, 859, 1601 - 125, 976),
                    text="Laatste",
                    fill=(255, 255, 255),
                    font=self.bold_font[36],
                )
                align_text_center(
                    (1601 - 125, 859, 1892, 976),
                    text=f"{'Event ' + str(highest_event_value) if highest_event_value > 0 else '-'}",
                    fill=(255, 255, 255),
                    font=self.font[36],
                )

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
        img: Image.Image = await self.generate_prefix_image(
            _object,
            size=(1942, 1096),
            to_file=False,
        )
        return await asyncio.to_thread(
            self._generate_image,
            _object,
            to_file=to_file,
            img=img,
        )

    # --- VOICE IDENTITY & HABITS DASHBOARD (4-QUADRANT FULL-PAGE DESIGN) ---
    def _generate_stats_image(
        self,
        _object: discord.Member,
        to_file: bool,
        stats: dict,
        _object_display: typing.Optional[bytes],
    ) -> typing.Union[Image.Image, discord.File]:
        size = (1942, 1096)
        img = Image.new("RGBA", size, (0, 0, 0, 0))

        # 1. Base Background
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

        # 2. Header: Avatar
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

        # 3. Header: Username & Persona Badge
        name_str = self.remove_unprintable_characters(_object.display_name) or _object.name
        draw.text((225, 45), text=name_str, fill=(255, 255, 255), font=self.bold_font[50])

        persona_str = f"Voice Persona: {stats.get('persona', 'Stille Luisteraar')}"
        persona_w = self.bold_font[30].getbbox(persona_str)[2]
        draw.rounded_rectangle((225, 120, 245 + persona_w + 20, 180), radius=12, fill=(88, 101, 242))
        draw.text((235, 130), text=persona_str, fill=(255, 255, 255), font=self.bold_font[30])

        # 4. Header: Server Logo & Name
        try:
            logo = Image.open(self.icons["logo"]).resize((55, 55))
            img.paste(logo, (1320, 50, 1375, 105), mask=logo.split()[3])
        except Exception:
            pass
        draw.text((1390, 50), text="Shadowzone Gaming", fill=(163, 163, 163), font=self.font[54])

        # ==================== 4-QUADRANT DASHBOARD ====================
        # Links: x=60 -> 940 (breedte 880)
        # Rechts: x=1000 -> 1880 (breedte 880)

        # --- BOX 1 (TOP LINKS): VOICE STATUS & SERVER RANG ---
        draw.rounded_rectangle((60, 204, 940, 585), radius=15, fill=(47, 49, 54))
        align_text_center((80, 214, 920, 284), text="Voice Status & Rang", fill=(255, 255, 255), font=self.bold_font[40])
        try:
            icon_p = Image.open(self.icons["person"]).resize((65, 65))
            img.paste(icon_p, (855, 214), mask=icon_p.split()[3])
        except Exception:
            pass

        # Row 1: Server Rang
        draw.rounded_rectangle((80, 301, 920, 418), radius=15, fill=(32, 34, 37))
        draw.rounded_rectangle((80, 301, 380, 418), radius=15, fill=(24, 26, 27))
        align_text_center((80, 301, 380, 418), text="30d Rang", fill=(255, 255, 255), font=self.bold_font[36])
        align_text_center((380, 301, 920, 418), text=stats.get("rank_str", "-"), fill=(255, 255, 255), font=self.bold_font[36])

        # Row 2: Totaal Uren + Percentiel
        draw.rounded_rectangle((80, 448, 920, 565), radius=15, fill=(32, 34, 37))
        draw.rounded_rectangle((80, 448, 380, 565), radius=15, fill=(24, 26, 27))
        align_text_center((80, 448, 380, 565), text="Totaal (30d)", fill=(255, 255, 255), font=self.bold_font[30])

        total_display = f"{stats.get('total_hours', 0)} Uur"
        if stats.get("top_pct_str") and stats.get("top_pct_str") != "-":
            total_display += f" ({stats.get('top_pct_str')})"
        align_text_center((380, 448, 920, 565), text=total_display, fill=(255, 255, 255), font=self.font[36])

        # --- BOX 2 (BOTTOM LINKS): TIJDSBESTEDING ---
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

        # --- BOX 3 (TOP RECHTS): GEWOONTES & PIEKTIJD ---
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

        # --- BOX 4 (BOTTOM RECHTS): WEKELIJKSE ACTIVITEIT (7-DAGEN GRAFIEK) ---
        draw.rounded_rectangle((1000, 615, 1880, 996), radius=15, fill=(47, 49, 54))
        align_text_center((1020, 625, 1860, 695), text="Wekelijkse Activiteit", fill=(255, 255, 255), font=self.bold_font[40])

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

            bar_color = (114, 137, 218) if is_peak else (79, 84, 92)
            draw.rounded_rectangle((bx, 905 - bar_h, bx + 65, 905), radius=6, fill=bar_color)

            # Daglabel
            lbl = day_labels[i]
            lbl_box = self.bold_font[30].getbbox(lbl)
            lbl_x = bx + int((65 - (lbl_box[2] - lbl_box[0])) / 2)
            draw.text((lbl_x, 920), text=lbl, fill=(255, 255, 255) if is_peak else (160, 160, 160), font=self.bold_font[30])

            # Uur-aantal boven de staaf
            if hours[i] > 0:
                h_str = f"{hours[i]}u"
                h_box = self.font[28].getbbox(h_str)
                h_x = bx + int((65 - (h_box[2] - h_box[0])) / 2)
                draw.text((h_x, 905 - bar_h - 32), text=h_str, fill=(200, 200, 200), font=self.font[28])

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
    ) -> typing.Union[Image.Image, discord.File]:
        api_tokens = await self.bot.get_shared_api_tokens("statbot")
        api_key = api_tokens.get("api_key", "")

        client = StatbotClient(api_key=api_key)
        stats = await client.get_user_voice_stats(_object.guild.id, _object.id, days=30)
        await client.close()

        avatar_bytes = await _object.display_avatar.read()

        return await asyncio.to_thread(
            self._generate_stats_image,
            _object,
            to_file=to_file,
            stats=stats,
            _object_display=avatar_bytes,
        )

    @commands.guild_only()
    @commands.bot_has_permissions(attach_files=True)
    @commands.hybrid_command(name="lid", description="Krijg profiel van gebruiker")
    async def lid(
        self,
        ctx: commands.Context,
        *,
        member: discord.Member = commands.Author,
    ) -> None:
        """Krijg profiel van gebruiker"""
        if not member.bot:
            await usercardView(
                cog=self,
                _object=member,
            ).start(ctx, command='card')
        else:
            await ctx.send('Niet mogelijk voor bot')

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
            await usercardView(
                cog=self,
                _object=member,
            ).start(ctx, command='id')
        else:
            await ctx.send('Niet mogelijk voor bot')