from AAA3A_utils import Cog  # isort:skip
from redbot.core import commands  # isort:skip
from redbot.core.bot import Red  # isort:skip
from redbot.core.i18n import Translator, cog_i18n  # isort:skip
import discord  # isort:skip
import typing  # isort:skip

import asyncio
import functools
import io
from collections import Counter
from pathlib import Path
from datetime import datetime

import plotly.graph_objects as go
from fontTools.ttLib import TTFont
from PIL import Image, ImageChops, ImageDraw, ImageFont
from redbot.core.data_manager import bundled_data_path
from frappeclient import FrappeClient

from .view import GuildStatsView


_: Translator = Translator("GuildStats", __file__)


@cog_i18n(_)
class GuildStats(Cog):
    """A cog to generate images"""

    def __init__(self, bot: Red) -> None:
        super().__init__(bot=bot)
        self.Frappeclient = None

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
            )
        }

    async def cog_load(self):
        await super().cog_load()
        frappe_keys = await self.bot.get_shared_api_tokens("frappelogin")
        api_key =  frappe_keys.get("username")
        api_secret = frappe_keys.get("password")
        if api_key and api_secret:
            self.Frappeclient = FrappeClient("https://shadowzone.nl")
            self.Frappeclient.login(api_key, api_secret)
        else:
            print("API keys for Frappe are missing.")

    async def cog_unload(self) -> None:
        self.font_to_remove_unprintable_characters.close()
        for icon in self.icons.values():
            icon.close()
        await super().cog_unload() 

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
        draw: ImageDraw.ImageDraw = ImageDraw.Draw(img)
        draw.rounded_rectangle(
            (0, 0, img.width, img.height),
            radius=50,
            fill=(32, 34, 37),
        )
        align_text_center = functools.partial(self.align_text_center, draw)

        doc = self.Frappeclient.get_list('Member', fields = ['name'], filters = {'discord_id': _object.id})
        if doc:
            member = self.Frappeclient.get_doc("Member", doc[0]['name'])
        
            # Member name & Member avatar.
            image = Image.open(io.BytesIO(_object_display))
            image = image.resize((140, 140))
            mask = Image.new("L", image.size, 0)
            d = ImageDraw.Draw(mask)
            d.rounded_rectangle(
                (0, 0, image.width, image.height),
                radius=20,
                fill=255,
            )
            # d.ellipse((0, 0, image.width, image.height), fill=255)
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
            guild_icon=(
                (
                    await (
                        _object if isinstance(_object, discord.Guild) else _object.guild
                    ).icon.read()
                )
                if (_object if isinstance(_object, discord.Guild) else _object.guild).icon
                is not None
                else None
            ),
        )

    def _generate_image(
        self,
        _object: discord.Member,
        to_file: bool,
        img: Image.Image,
    ) -> typing.Union[Image.Image, discord.File]:
        draw: ImageDraw.ImageDraw = ImageDraw.Draw(img)
        align_text_center = functools.partial(self.align_text_center, draw)

        # Data.
        if isinstance(_object, (discord.Member)):
            # lidmaatschap
            doc = self.Frappeclient.get_list('Member', fields = ['name'], filters = {'discord_id': _object.id})
            if doc:
                member = self.Frappeclient.get_doc("Member", doc[0]['name'])

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
                    text=f"{datetime.strptime(member.get('custom_start_lidmaatschap'), '%Y-%m-%d').strftime('%d %B %Y') if member.get('custom_start_lidmaatschap') and  member.get('custom_status') == 'Actief' and  member.get('membership_type') == 'Lid' else '-'}",
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
                for item in member.get("custom_events"):
                    if item['event_bezocht'] not in ('Qmusic Foute Party: 24 - 26 juni 2022', 'Vakantie: 11-18 augustus 2023'):
                        events += 1
                        try:
                            event_value = int(item["event_bezocht"].split()[1].strip(":"))
                            if event_value > highest_event_value:
                                highest_event = item['event_bezocht']
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
                    text=(
                        str(events)
                    ),
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

    async def generate_image(
        self,
        _object: discord.Member,
        to_file: bool = True,
    ) -> typing.Union[Image.Image, discord.File]:
        img: Image.Image = await self.generate_prefix_image(
            _object,
            size=(1942, 1096),
            to_file=False,
        )  # (1940, 1481) / 1942 + 636
        return await asyncio.to_thread(
            self._generate_image,
            _object,
            to_file=to_file,
            img=img,
        )

    @commands.guild_only()
    @commands.bot_has_permissions(attach_files=True)
    @commands.hybrid_group(invoke_without_command=True)
    async def guildstats(
        self,
        ctx: commands.Context,
        *,
        member: discord.Member = commands.Author,
    ) -> None:
        """Display stats for a specified member."""
        if not member.bot:
            await GuildStatsView(
                cog=self,
                _object=member,
            ).start(ctx)
        else: 
            await ctx.send('Niet mogelijk voor bot')