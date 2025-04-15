from AAA3A_utils import Cog, Loop, CogsUtils, Menu  # isort:skip
from redbot.core import commands, Config  # isort:skip
from redbot.core.bot import Red  # isort:skip
from redbot.core.i18n import Translator, cog_i18n  # isort:skip
import discord  # isort:skip
import typing  # isort:skip

import asyncio
import datetime
import functools
import io
from collections import Counter
from copy import deepcopy
from pathlib import Path

import plotly.graph_objects as go
from fontTools.ttLib import TTFont
from PIL import Image, ImageChops, ImageDraw, ImageFont
from redbot.core.data_manager import bundled_data_path
from frappeclient import FrappeClient

from .view import GuildStatsView


_: Translator = Translator("GuildStats", __file__)


class ObjectConverter(commands.Converter):
    async def convert(
        self, ctx: commands.Context, argument: str
    ) -> typing.Union[
        discord.Member,
        discord.Role,
        typing.Literal["messages", "voice", "activities"],
        discord.CategoryChannel,
        discord.TextChannel,
        discord.VoiceChannel,
    ]:
        if ctx.command.name == "graphic" and argument.lower() in {
            "messages",
            "voice",
            "activities",
        }:
            return argument.lower()
        try:
            return await commands.MemberConverter().convert(ctx, argument=argument)
        except commands.BadArgument:
            try:
                return await commands.RoleConverter().convert(ctx, argument=argument)
            except commands.BadArgument:
                try:
                    return await commands.CategoryChannelConverter().convert(
                        ctx, argument=argument
                    )
                except commands.BadArgument:
                    try:
                        return await commands.TextChannelConverter().convert(
                            ctx, argument=argument
                        )
                    except commands.BadArgument:
                        try:
                            return await commands.VoiceChannelConverter().convert(
                                ctx, argument=argument
                            )
                        except commands.BadArgument:
                            raise commands.BadArgument(
                                "No member/category/text channel/voice channel found."
                            )


@cog_i18n(_)
class GuildStats(Cog):
    """A cog to generate images with messages and voice stats, for members, roles, guilds, categories, text channels, voice channels and activities!"""

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
                "trophy",
                "#",
                "sound",
                "history",
                "person",
                "graphic",
                "query_stats",
                "game",
                "home",
                "globe",
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

    def _get_data(
        self,
        _object: typing.Union[
            discord.Member,
            typing.Tuple[discord.Member, typing.Literal["activities"]],
            discord.Role,
            discord.Guild,
            typing.Tuple[
                discord.Guild,
                typing.Union[
                    typing.Literal["messages", "voice", "activities"],
                    typing.Tuple[
                        typing.Literal["top", "weekly", "monthly"],
                        typing.Literal["messages", "voice"],
                        typing.Literal["members", "channels"],
                    ],
                    typing.Tuple[typing.Literal["activity"], str],
                ],
            ],
            discord.CategoryChannel,
            discord.TextChannel,
            discord.VoiceChannel,
        ],
        members_type: typing.Literal["humans", "bots", "both"],
        utc_now: datetime.datetime,
    ) -> typing.Dict[str, typing.Any]:
        if isinstance(_object, typing.Tuple):
            _object, _type = _object
        else:
            _type = None
        if utc_now is None:
            utc_now = datetime.datetime.now(tz=datetime.timezone.utc)

    async def get_data(
        self,
        _object: typing.Union[
            discord.Member,
            typing.Tuple[discord.Member, typing.Literal["activities"]],
            discord.Role,
            discord.Guild,
            typing.Tuple[
                discord.Guild,
                typing.Union[
                    typing.Literal["messages", "voice", "activities"],
                    typing.Tuple[
                        typing.Literal["top", "weekly", "monthly"],
                        typing.Literal["messages", "voice"],
                        typing.Literal["members", "channels"],
                    ],
                    typing.Tuple[typing.Literal["activity"], str],
                ],
            ],
            discord.CategoryChannel,
            discord.TextChannel,
            discord.VoiceChannel,
        ],
        members_type: typing.Literal["humans", "bots", "both"] = "humans",
        utc_now: datetime.datetime = None,
    ) -> typing.Dict[str, typing.Any]:
        if isinstance(_object, typing.Tuple):
            _object, _type = _object
        else:
            _type = None
        return await asyncio.to_thread(
            self._get_data,
            _object=_object if _type is None else (_object, _type),
            members_type=members_type,
            utc_now=utc_now,
        )

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

    def number_to_text_with_suffix(self, number: float) -> str:
        suffixes = [
            "k",
            "m",
            "b",
            "t",
            "q",
            "Q",
            "s",
            "S",
            "o",
            "n",
            "d",
            "U",
            "D",
            "T",
            "Qa",
            "Qi",
            "Sx",
            "Sp",
            "Oc",
            "No",
            "Vi",
        ]
        index = None
        while abs(number) >= 1000 and (index or -1) < len(suffixes) - 1:
            number /= 1000.0
            if index is None:
                index = -1
            index += 1
        # return f"{number:.1f}{suffixes[index] if index is not None else ''}"
        if number == int(number):
            formatted_number = int(number)
        elif f"{number:.1f}" != "0.0":
            formatted_number = (
                int(float(f"{number:.1f}"))
                if float(f"{number:.1f}") == int(float(f"{number:.1f}"))
                else f"{number:.1f}"
            )
        else:
            formatted_number = (
                int(float(f"{number:.2f}"))
                if float(f"{number:.2f}") == int(float(f"{number:.2f}"))
                else f"{number:.2f}"
            )
        suffix = suffixes[index] if index is not None else ""
        return f"{formatted_number}{suffix}"

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
        _object: typing.Union[
            discord.Member,
            typing.Tuple[discord.Member, typing.Literal["activities"]],
            discord.Role,
            discord.Guild,
            typing.Tuple[
                discord.Guild,
                typing.Union[
                    typing.Literal["messages", "voice", "activities"],
                    typing.Tuple[
                        typing.Literal["top", "weekly", "monthly"],
                        typing.Literal["messages", "voice"],
                        typing.Literal["members", "channels"],
                    ],
                    typing.Tuple[typing.Literal["activity"], str],
                ],
            ],
            discord.CategoryChannel,
            discord.TextChannel,
            discord.VoiceChannel,
        ],
        size: typing.Tuple[int, int],
        to_file: bool,
        _object_display: typing.Optional[bytes],
        guild_icon: typing.Optional[bytes],
    ) -> typing.Union[Image.Image, discord.File]:
        if isinstance(_object, typing.Tuple):
            _object, _type = _object
        else:
            _type = None
        img: Image.Image = Image.new("RGBA", size, (0, 0, 0, 0))
        draw: ImageDraw.ImageDraw = ImageDraw.Draw(img)
        draw.rounded_rectangle(
            (0, 0, img.width, img.height),
            radius=50,
            fill=(32, 34, 37),
        )
        align_text_center = functools.partial(self.align_text_center, draw)

        # Member/Channel name & Member avatar.
        if isinstance(_object, discord.Member):
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
                    image, (30, 30, 170, 170), mask=ImageChops.multiply(mask, image.split()[3])
                )
            except IndexError:
                img.paste(image, (30, 30, 170, 170), mask=mask)
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
                    (190, 30),
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
                        (190 + display_name_size[2] + 25, 48),
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
                    (190, 30),
                    text=self.remove_unprintable_characters(_object.global_name),
                    fill=(255, 255, 255),
                    font=self.bold_font[50],
                )
            else:
                draw.text(
                    (190, 30), text=_object.name, fill=(255, 255, 255), font=self.bold_font[50]
                )
        elif isinstance(_object, discord.Role):
            if _object.display_icon is not None:
                image = Image.open(io.BytesIO(_object_display))
                image = image.resize((140, 140))
                mask = Image.new("L", image.size, 0)
                d = ImageDraw.Draw(mask)
                d.rounded_rectangle(
                    (0, 0, image.width, image.height),
                    radius=25,
                    fill=255,
                )
                try:
                    img.paste(
                        image, (30, 30, 170, 170), mask=ImageChops.multiply(mask, image.split()[3])
                    )
                except IndexError:
                    img.paste(image, (30, 30, 170, 170), mask=mask)
            else:
                image = Image.open(self.icons["person"])
                image = image.resize((140, 140))
                img.paste(image, (30, 30, 170, 170), mask=image.split()[3])
            draw.text(
                (190, 30),
                "Role {_object.name}").format(_object=_object,
                fill=(255, 255, 255),
                font=self.bold_font[50],
            )
        elif isinstance(_object, discord.Guild):
            if _type is None:
                draw.text(
                    (190, 30), text="Guild Stats", fill=(255, 255, 255), font=self.bold_font[50]
                )
                image = Image.open(
                    self.icons[
                        (
                            "home"
                            if "DISCOVERABLE"
                            not in (
                                _object if isinstance(_object, discord.Guild) else _object.guild
                            ).features
                            else "globe"
                        )
                    ]
                )
            elif _type == "messages":
                draw.text(
                    (190, 30),
                    text="Messages Stats",
                    fill=(255, 255, 255),
                    font=self.bold_font[50],
                )
                image = Image.open(self.icons["#"])
            elif _type == "voice":
                draw.text(
                    (190, 30), text="Voice Stats", fill=(255, 255, 255), font=self.bold_font[50]
                )
                image = Image.open(self.icons["sound"])
            elif _type == "activities":
                draw.text(
                    (190, 30),
                    text="Activities Stats",
                    fill=(255, 255, 255),
                    font=self.bold_font[50],
                )
                image = Image.open(self.icons["game"])
            image = image.resize((140, 140))
            img.paste(image, (30, 30, 170, 170), mask=image.split()[3])
        elif isinstance(_object, discord.CategoryChannel):
            draw.text(
                (190, 30),
                "Category - {_object.name}").format(_object=_object,
                fill=(255, 255, 255),
                font=self.bold_font[50],
            )
            image = Image.open(self.icons["#"])
            image = image.resize((140, 140))
            img.paste(image, (30, 30, 170, 170), mask=image.split()[3])
        elif isinstance(_object, discord.TextChannel):
            draw.text(
                (190, 30),
                self.remove_unprintable_characters(_object.name),
                fill=(255, 255, 255),
                font=self.bold_font[50],
            )
            image = Image.open(self.icons["#"])
            image = image.resize((140, 140))
            img.paste(image, (30, 30, 170, 170), mask=image.split()[3])
        elif isinstance(_object, discord.VoiceChannel):
            draw.text(
                (190, 30),
                self.remove_unprintable_characters(_object.name),
                fill=(255, 255, 255),
                font=self.bold_font[50],
            )
            image = Image.open(self.icons["sound"])
            image = image.resize((140, 140))
            img.paste(image, (30, 30, 170, 170), mask=image.split()[3])

        # Guild name & Guild icon.
        if guild_icon is not None:
            image = Image.open(io.BytesIO(guild_icon))
            image = image.resize((55, 55))
            mask = Image.new("L", image.size, 0)
            d = ImageDraw.Draw(mask)
            d.rounded_rectangle(
                (0, 0, image.width, image.height),
                radius=25,
                fill=255,
            )
            try:
                img.paste(
                    image, (190, 105, 245, 160), mask=ImageChops.multiply(mask, image.split()[3])
                )
            except IndexError:
                img.paste(image, (190, 105, 245, 160), mask=mask)
            draw.text(
                (265, 105),
                text=(_object if isinstance(_object, discord.Guild) else _object.guild).name,
                fill=(163, 163, 163),
                font=self.font[54],
            )
        else:
            image = Image.open(
                self.icons[
                    (
                        "home"
                        if "DISCOVERABLE"
                        not in (
                            _object if isinstance(_object, discord.Guild) else _object.guild
                        ).features
                        else "globe"
                    )
                ]
            )
            image = image.resize((55, 55))
            img.paste(image, (190, 105, 245, 160), mask=image.split()[3])
            draw.text(
                (255, 105),
                text=self.remove_unprintable_characters(
                    (_object if isinstance(_object, discord.Guild) else _object.guild).name
                ),
                fill=(163, 163, 163),
                font=self.font[54],
            )

        # Optional `joined_on` and `created_on`.
        if isinstance(_object, discord.Member):
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
        _object: typing.Union[
            discord.Member,
            discord.Role,
            discord.Guild,
            typing.Tuple[
                discord.Guild,
                typing.Union[
                    typing.Literal["messages", "voice", "activities"],
                    typing.Tuple[
                        typing.Literal["top", "weekly", "monthly"],
                        typing.Literal["messages", "voice"],
                        typing.Literal["members", "channels"],
                    ],
                    typing.Tuple[typing.Literal["activity"], str],
                ],
            ],
            discord.CategoryChannel,
            discord.TextChannel,
            discord.VoiceChannel,
        ],
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
        _object: typing.Union[
            discord.Member,
            discord.Role,
            discord.Guild,
            typing.Tuple[
                discord.Guild,
                typing.Union[
                    typing.Literal["messages", "voice", "activities"],
                    typing.Tuple[
                        typing.Literal["top", "weekly", "monthly"],
                        typing.Literal["messages", "voice"],
                        typing.Literal["members", "channels"],
                    ],
                    typing.Tuple[typing.Literal["activity"], str],
                ],
            ],
            discord.CategoryChannel,
            discord.TextChannel,
            discord.VoiceChannel,
        ],
        members_type: typing.Literal["humans", "bots", "both"],
        show_graphic: bool,
        graphic: typing.Optional[Image.Image],
        data: dict,
        to_file: bool,
        img: Image.Image,
    ) -> typing.Union[Image.Image, discord.File]:
        if isinstance(_object, typing.Tuple):
            _object, _type = _object
        else:
            _type = None
        draw: ImageDraw.ImageDraw = ImageDraw.Draw(img)
        align_text_center = functools.partial(self.align_text_center, draw)

        # Data.
        if isinstance(_object, (discord.Member, discord.Role)):
            if _type is None:
                # lidmaatschap. box = 606 / empty = 30 | 2 cases / box = 117 / empty = 30
                draw.rounded_rectangle((30, 204, 636, 585), radius=15, fill=(47, 49, 54))
                align_text_center(
                    (50, 214, 50, 284),
                    text="Lidmaatschap",
                    fill=(255, 255, 255),
                    font=self.bold_font[40],
                )
                image = Image.open(self.icons["history"])
                image = image.resize((70, 70))
                img.paste(image, (546, 214, 616, 284), mask=image.split()[3])
                draw.rounded_rectangle((50, 301, 616, 418), radius=15, fill=(32, 34, 37))
                draw.rounded_rectangle((50, 301, 325, 418), radius=15, fill=(24, 26, 27))
                align_text_center(
                    (50, 301, 325, 418),
                    text="Lid sinds",
                    fill=(255, 255, 255),
                    font=self.bold_font[36],
                )
                align_text_center(
                    (325, 301, 616, 418),
                    text=f"{self.number_to_text_with_suffix(0)} messages",
                    fill=(255, 255, 255),
                    font=self.font[36],
                )
                draw.rounded_rectangle((50, 448, 616, 565), radius=15, fill=(32, 34, 37))
                draw.rounded_rectangle((50, 448, 325, 565), radius=15, fill=(24, 26, 27))
                align_text_center(
                    (50, 448, 325, 565),
                    text="Betrokken sinds",
                    fill=(255, 255, 255),
                    font=self.bold_font[30],
                )
                align_text_center(
                    (325, 448, 616, 565),
                    text=f"{self.number_to_text_with_suffix(0)} hours",
                    fill=(255, 255, 255),
                    font=self.font[36],
                )

                # Messages. box = 606 / empty = 30 | 3 cases / box = 76 / empty = 16
                draw.rounded_rectangle((668, 204, 1274, 585), radius=15, fill=(47, 49, 54))
                align_text_center(
                    (688, 214, 688, 284),
                    text="Messages",
                    fill=(255, 255, 255),
                    font=self.bold_font[40],
                )
                image = Image.open(self.icons["#"])
                image = image.resize((70, 70))
                img.paste(image, (1184, 214, 1254, 284), mask=image.split()[3])
                draw.rounded_rectangle((688, 301, 1254, 377), radius=15, fill=(32, 34, 37))
                draw.rounded_rectangle((688, 301, 910, 377), radius=15, fill=(24, 26, 27))
                align_text_center(
                    (688, 301, 910, 377),
                    text="1d",
                    fill=(255, 255, 255),
                    font=self.bold_font[36],
                )
                align_text_center(
                    (910, 301, 1254, 377),
                    text=f"{self.number_to_text_with_suffix(0)} messages",
                    fill=(255, 255, 255),
                    font=self.font[36],
                )
                draw.rounded_rectangle((688, 395, 1254, 471), radius=15, fill=(32, 34, 37))
                draw.rounded_rectangle((688, 395, 910, 471), radius=15, fill=(24, 26, 27))
                align_text_center(
                    (688, 395, 910, 471),
                    text="7d",
                    fill=(255, 255, 255),
                    font=self.bold_font[36],
                )
                align_text_center(
                    (910, 395, 1254, 471),
                    text=f"{self.number_to_text_with_suffix(0)} messages",
                    fill=(255, 255, 255),
                    font=self.font[36],
                )
                draw.rounded_rectangle((688, 489, 1254, 565), radius=15, fill=(32, 34, 37))
                draw.rounded_rectangle((688, 489, 910, 565), radius=15, fill=(24, 26, 27))
                align_text_center(
                    (688, 489, 910, 565),
                    text="30d",
                    fill=(255, 255, 255),
                    font=self.bold_font[36],
                )
                align_text_center(
                    (910, 489, 1254, 565),
                    text=f"{self.number_to_text_with_suffix(0)} messages",
                    fill=(255, 255, 255),
                    font=self.font[36],
                )

                # Voice Activity. + 52 / box = 606 / empty = 30 | 3 cases / box = 76 / empty = 16
                draw.rounded_rectangle((1306, 204, 1912, 585), radius=15, fill=(47, 49, 54))
                align_text_center(
                    (1326, 214, 1326, 284),
                    text="Voice Activity",
                    fill=(255, 255, 255),
                    font=self.bold_font[40],
                )
                image = Image.open(self.icons["sound"])
                image = image.resize((70, 70))
                img.paste(image, (1822, 214, 1892, 284), mask=image.split()[3])
                draw.rounded_rectangle((1326, 301, 1892, 377), radius=15, fill=(32, 34, 37))
                draw.rounded_rectangle((1326, 301, 1548, 377), radius=15, fill=(24, 26, 27))
                align_text_center(
                    (1326, 301, 1548, 377),
                    text="1d",
                    fill=(255, 255, 255),
                    font=self.bold_font[36],
                )
                align_text_center(
                    (1548, 301, 1892, 377),
                    text=f"{self.number_to_text_with_suffix(0)} hours",
                    fill=(255, 255, 255),
                    font=self.font[36],
                )
                draw.rounded_rectangle((1326, 395, 1892, 471), radius=15, fill=(32, 34, 37))
                draw.rounded_rectangle((1326, 395, 1548, 471), radius=15, fill=(24, 26, 27))
                align_text_center(
                    (1326, 395, 1548, 471),
                    text="7d",
                    fill=(255, 255, 255),
                    font=self.bold_font[36],
                )
                align_text_center(
                    (1548, 395, 1892, 471),
                    text=f"{self.number_to_text_with_suffix(0)} hours",
                    fill=(255, 255, 255),
                    font=self.font[36],
                )
                draw.rounded_rectangle((1326, 489, 1892, 565), radius=15, fill=(32, 34, 37))
                draw.rounded_rectangle((1326, 489, 1548, 565), radius=15, fill=(24, 26, 27))
                align_text_center(
                    (1326, 489, 1548, 565),
                    text="30d",
                    fill=(255, 255, 255),
                    font=self.bold_font[36],
                )
                align_text_center(
                    (1548, 489, 1892, 565),
                    text=f"{self.number_to_text_with_suffix(0)} hours",
                    fill=(255, 255, 255),
                    font=self.font[36],
                )

                draw.rounded_rectangle((30, 615, 636, 996), radius=15, fill=(47, 49, 54))
                align_text_center(
                    (50, 625, 50, 695),
                    text="Server Ranks",
                    fill=(255, 255, 255),
                    font=self.bold_font[40],
                )
                image = Image.open(self.icons["trophy"])
                image = image.resize((70, 70))
                img.paste(image, (546, 625, 616, 695), mask=image.split()[3])
                draw.rounded_rectangle((50, 712, 616, 829), radius=15, fill=(32, 34, 37))
                draw.rounded_rectangle((50, 712, 325, 829), radius=15, fill=(24, 26, 27))
                align_text_center(
                    (50, 712, 325, 829), text="Text", fill=(255, 255, 255), font=self.bold_font[36]
                )
                align_text_center(
                    (325, 712, 616, 829),
                    text=(
                        f"No data."
                    ),
                    fill=(255, 255, 255),
                    font=self.font[36],
                )
                draw.rounded_rectangle((50, 859, 616, 976), radius=15, fill=(32, 34, 37))
                draw.rounded_rectangle((50, 859, 325, 976), radius=15, fill=(24, 26, 27))
                align_text_center(
                    (50, 859, 325, 976),
                    text="Voice",
                    fill=(255, 255, 255),
                    font=self.bold_font[36],
                )
                align_text_center(
                    (325, 859, 616, 976),
                    text=(
                        f"No data."
                    ),
                    fill=(255, 255, 255),
                    font=self.font[36],
                )

                # Top Channels & Activity. box = 925 / empty = 30 | 3 cases / box = 76 / empty = 16
                draw.rounded_rectangle((668, 615, 1593, 996), radius=15, fill=(47, 49, 54))
                align_text_center(
                    (688, 625, 688, 695),
                    text="Top Channels & Activity",
                    fill=(255, 255, 255),
                    font=self.bold_font[40],
                )
                image = Image.open(self.icons["query_stats"])
                image = image.resize((70, 70))
                img.paste(image, (1503, 625, 1573, 695), mask=image.split()[3])
                image = Image.open(self.icons["#"])
                image = image.resize((70, 70))
                img.paste(image, (688, 715, 758, 785), mask=image.split()[3])
                draw.rounded_rectangle((768, 712, 1573, 788), radius=15, fill=(32, 34, 37))
                draw.rounded_rectangle((768, 712, 1218, 788), radius=15, fill=(24, 26, 27))
                align_text_center(
                    (768, 712, 1218, 788),
                    text=self.remove_unprintable_characters(
                        "Test"
                    ),
                    fill=(255, 255, 255),
                    font=self.bold_font[36],
                )
                align_text_center(
                    (1218, 712, 1573, 788),
                    text=f"{self.number_to_text_with_suffix(0)} messages",
                    fill=(255, 255, 255),
                    font=self.font[36],
                )
                image = Image.open(self.icons["sound"])
                image = image.resize((70, 70))
                img.paste(image, (688, 807, 758, 877), mask=image.split()[3])
                draw.rounded_rectangle((768, 804, 1573, 880), radius=15, fill=(32, 34, 37))
                draw.rounded_rectangle((768, 804, 1218, 880), radius=15, fill=(24, 26, 27))
                align_text_center(
                    (768, 804, 1218, 880),
                    text=self.remove_unprintable_characters(
                        "Test"
                    ),
                    fill=(255, 255, 255),
                    font=self.bold_font[36],
                )
                align_text_center(
                    (1218, 804, 1573, 880),
                    text=f"{self.number_to_text_with_suffix(0)} hours",
                    fill=(255, 255, 255),
                    font=self.font[36],
                )
                image = Image.open(self.icons["game"])
                image = image.resize((70, 70))
                img.paste(image, (688, 899, 758, 969), mask=image.split()[3])
                draw.rounded_rectangle((768, 896, 1573, 972), radius=15, fill=(32, 34, 37))
                draw.rounded_rectangle((768, 896, 1218, 972), radius=15, fill=(24, 26, 27))
                align_text_center(
                    (768, 896, 1218, 972),
                    text="Test",
                    fill=(255, 255, 255),
                    font=self.bold_font[36],
                )
                align_text_center(
                    (1218, 896, 1573, 972),
                    text=f"{self.number_to_text_with_suffix(0)} hours",
                    fill=(255, 255, 255),
                    font=self.font[36],
                )

                if show_graphic:
                    # Graphic. box = 940 / empty = 0 | + 411 (381 + 30) / 1 case / box = 264 / empty = 0
                    draw.rounded_rectangle(
                        (30, 1026, 1910, 1407 + 200), radius=15, fill=(47, 49, 54)
                    )
                    align_text_center(
                        (50, 1036, 50, 1106),
                        text="Graphic",
                        fill=(255, 255, 255),
                        font=self.bold_font[40],
                    )
                    image = Image.open(self.icons["query_stats"])
                    image = image.resize((70, 70))
                    img.paste(image, (1830, 1036, 1900, 1106), mask=image.split()[3])
                    draw.rounded_rectangle(
                        (50, 1123, 1890, 1387 + 200), radius=15, fill=(32, 34, 37)
                    )
                    image: Image.Image = graphic
                    image = image.resize((1840, 464))
                    img.paste(image, (50, 1123, 1890, 1387 + 200))


        if not to_file:
            return img
        buffer = io.BytesIO()
        img.save(buffer, format="png", optimize=True)
        buffer.seek(0)
        return discord.File(buffer, filename="image.png")

    async def generate_image(
        self,
        _object: typing.Union[
            discord.Member,
            typing.Tuple[discord.Member, typing.Literal["activities"]],
            discord.Role,
            discord.Guild,
            typing.Tuple[
                discord.Guild,
                typing.Union[
                    typing.Literal["messages", "voice", "activities"],
                    typing.Tuple[
                        typing.Literal["top", "weekly", "monthly"],
                        typing.Literal["messages", "voice"],
                        typing.Literal["members", "channels"],
                    ],
                    typing.Tuple[typing.Literal["activity"], str],
                ],
            ],
            discord.CategoryChannel,
            discord.TextChannel,
            discord.VoiceChannel,
        ],
        members_type: typing.Literal["humans", "bots", "both"] = "humans",
        show_graphic: bool = False,
        data: typing.Optional[dict] = None,
        to_file: bool = True,
    ) -> typing.Union[Image.Image, discord.File]:
        if isinstance(_object, typing.Tuple):
            _object, _type = _object
        else:
            _type = None
        img: Image.Image = await self.generate_prefix_image(
            _object if _type is None else (_object, _type),
            size=(1942, 1437 + 200 + 70 if show_graphic else 1026 + 70),
            to_file=False,
        )  # (1940, 1481) / 1942 + 636
        if data is None:
            data = await self.get_data(
                _object if _type is None else (_object, _type), members_type=members_type
            )
        if show_graphic:
            graphic = await self.generate_graphic(
                _object, size=(1840, 464), data=data, to_file=False
            )
        elif _type == "activities" or (
            isinstance(_type, typing.Tuple)
            and _type[0] in ("top", "weekly", "monthly", "activity")
        ):
            graphic = await self.generate_graphic(
                _object, size=(885, 675), data=data, to_file=False
            )
        else:
            graphic = None
        return await asyncio.to_thread(
            self._generate_image,
            _object=_object if _type is None else (_object, _type),
            members_type=members_type,
            data=data,
            to_file=to_file,
            img=img,
            show_graphic=show_graphic,
            graphic=graphic,
        )

    @commands.guild_only()
    @commands.bot_has_permissions(attach_files=True)
    @commands.hybrid_group(invoke_without_command=True)
    async def guildstats(
        self,
        ctx: commands.Context,
        members_type: typing.Optional[typing.Literal["humans", "bots", "both"]] = "humans",
        show_graphic: typing.Optional[bool] = False,
        *,
        _object: ObjectConverter,
    ) -> None:
        """Generate images"""
        await GuildStatsView(
            cog=self,
            _object=_object,
            members_type=(
                ("bots" if _object.bot else "humans")
                if isinstance(_object, discord.Member)
                else members_type
            ),
            show_graphic_in_main=show_graphic if _object != "activities" else False,
            graphic_mode=False,
        ).start(ctx)

    @guildstats.command()
    async def member(
        self,
        ctx: commands.Context,
        show_graphic: typing.Optional[bool] = False,
        *,
        member: discord.Member = commands.Author,
    ) -> None:
        """Display stats for a specified member."""
        await GuildStatsView(
            cog=self,
            _object=member,
            members_type="bots" if member.bot else "humans",
            show_graphic_in_main=show_graphic,
            graphic_mode=False,
        ).start(ctx)