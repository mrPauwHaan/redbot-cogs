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
                                _("No member/category/text channel/voice channel found.")
                            )


@cog_i18n(_)
class GuildStats(Cog):
    """A cog to generate images with messages and voice stats, for members, roles, guilds, categories, text channels, voice channels and activities!"""

    def __init__(self, bot: Red) -> None:
        self.bot = bot
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

        # Handle `members_type`.
        def is_valid(member_id: int):
            if members_type == "both":
                return True
            elif (
                member := (
                    _object if isinstance(_object, discord.Guild) else _object.guild
                ).get_member(member_id)
            ) is None:
                return True
            elif members_type == "humans" and not member.bot:
                return True
            elif members_type == "bots" and member.bot:
                return True
            else:
                return False

        members_type_key = "" if members_type == "both" else f"{members_type}_"

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
                _("Role {_object.name}").format(_object=_object),
                fill=(255, 255, 255),
                font=self.bold_font[50],
            )
        elif isinstance(_object, discord.Guild):
            if _type is None:
                draw.text(
                    (190, 30), text=_("Guild Stats"), fill=(255, 255, 255), font=self.bold_font[50]
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
                    text=_("Messages Stats"),
                    fill=(255, 255, 255),
                    font=self.bold_font[50],
                )
                image = Image.open(self.icons["#"])
            elif _type == "voice":
                draw.text(
                    (190, 30), text=_("Voice Stats"), fill=(255, 255, 255), font=self.bold_font[50]
                )
                image = Image.open(self.icons["sound"])
            elif _type == "activities":
                draw.text(
                    (190, 30),
                    text=_("Activities Stats"),
                    fill=(255, 255, 255),
                    font=self.bold_font[50],
                )
                image = Image.open(self.icons["game"])
            elif isinstance(_type, typing.Tuple):
                if _type[0] == "top":
                    draw.text(
                        (190, 30),
                        text=_("Top Stats"),
                        fill=(255, 255, 255),
                        font=self.bold_font[50],
                    )
                    image = Image.open(self.icons["#" if _type[1] == "messages" else "sound"])
                elif _type[0] == "weekly":
                    draw.text(
                        (190, 30),
                        text=_("Weekly Top Stats"),
                        fill=(255, 255, 255),
                        font=self.bold_font[50],
                    )
                    image = Image.open(self.icons["#" if _type[1] == "messages" else "sound"])
                elif _type[0] == "monthly":
                    draw.text(
                        (190, 30),
                        text=_("Monthly Top Stats"),
                        fill=(255, 255, 255),
                        font=self.bold_font[50],
                    )
                    image = Image.open(self.icons["#" if _type[1] == "messages" else "sound"])
                elif _type[0] == "activity":
                    draw.text(
                        (190, 30),
                        text=_("Activity - {activity_name}").format(
                            activity_name=self.remove_unprintable_characters(_type[1])
                        ),
                        fill=(255, 255, 255),
                        font=self.bold_font[50],
                    )
                    image = Image.open(self.icons["game"])
            image = image.resize((140, 140))
            img.paste(image, (30, 30, 170, 170), mask=image.split()[3])
        elif isinstance(_object, discord.CategoryChannel):
            draw.text(
                (190, 30),
                _("Category - {_object.name}").format(_object=_object),
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
                text=_object.created_at.strftime("%B %d, %Y"),
                fill=(255, 255, 255),
                font=self.font[36],
            )
            draw.rounded_rectangle((1220, 30, 1476, 90), radius=15, fill=(79, 84, 92))
            align_text_center(
                (1220, 30, 1476, 90),
                text=_("Created On"),
                fill=(255, 255, 255),
                font=self.bold_font[30],
            )
            # `joined_on`
            draw.rounded_rectangle((1200 + 365, 75, 1545 + 365, 175), radius=15, fill=(47, 49, 54))
            align_text_center(
                (1200 + 365, 75, 1545 + 365, 175),
                text=_object.joined_at.strftime("%B %d, %Y"),
                fill=(255, 255, 255),
                font=self.font[36],
            )
            draw.rounded_rectangle((1220 + 365, 30, 1476 + 365, 90), radius=15, fill=(79, 84, 92))
            align_text_center(
                (1220 + 365, 30, 1476 + 365, 90),
                text=_("Joined On"),
                fill=(255, 255, 255),
                font=self.bold_font[30],
            )
        elif isinstance(
            _object,
            (discord.Guild, discord.CategoryChannel, discord.TextChannel, discord.VoiceChannel),
        ):
            # `created_on`
            draw.rounded_rectangle((1200 + 365, 75, 1545 + 365, 175), radius=15, fill=(47, 49, 54))
            align_text_center(
                (1200 + 365, 75, 1545 + 365, 175),
                text=_object.created_at.strftime("%B %d, %Y"),
                fill=(255, 255, 255),
                font=self.font[36],
            )
            draw.rounded_rectangle((1220 + 365, 30, 1476 + 365, 90), radius=15, fill=(79, 84, 92))
            align_text_center(
                (1220 + 365, 30, 1476 + 365, 90),
                text=_("Created On"),
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

    def _generate_graphic(
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
        size: typing.Optional[typing.Tuple[int, int]],
        data: dict,
        to_file: bool,
        img: Image.Image,
    ) -> typing.Union[Image.Image, discord.File]:
        if isinstance(_object, typing.Tuple):
            _object = _object[0]
        draw: ImageDraw.ImageDraw = ImageDraw.Draw(img)
        align_text_center = functools.partial(self.align_text_center, draw)
        if size is None:
            draw.rounded_rectangle((30, 204, 1910, 952), radius=15, fill=(47, 49, 54))
            draw.text((50, 220), text=_("Graphic"), fill=(255, 255, 255), font=self.bold_font[40])
            image = Image.open(self.icons["query_stats"])
            image = image.resize((70, 70))
            img.paste(image, (1830, 214, 1900, 284), mask=image.split()[3])
            draw.rounded_rectangle((50, 301, 1890, 922), radius=15, fill=(32, 34, 37))
        else:
            draw.rounded_rectangle((0, 0, size[0], size[1]), radius=15, fill=(32, 34, 37))

        fig = go.Figure()
        fig.update_layout(
            template="plotly_white",
            paper_bgcolor="rgba(0,0,0,0)",  # Transparent background.
            plot_bgcolor="rgba(0,0,0,0)",  # Transparent background.
            font_color="white",  # White characters font.
            font_size=30,  # Characters font size.
            yaxis2={"overlaying": "y", "side": "right"},
        )
        x = list(range(-30, 1))
        if data["graphic"].get("contributors") is not None:
            if size is None:
                draw.ellipse(
                    (img.width - 110, 321, img.width - 70, 361),
                    fill=(105, 105, 105),
                    outline=(0, 0, 0),
                )
                x1 = (
                    img.width
                    - 110
                    - 10
                    - self.bold_font[30].getbbox(
                        f"{self.number_to_text_with_suffix(data['contributors'][30])} Contributors"
                    )[2]
                )
                align_text_center(
                    (x1, 321, x1, 361),
                    text=f"{self.number_to_text_with_suffix(data['contributors'][30])} Contributors",
                    fill=(255, 255, 255),
                    font=self.bold_font[30],
                )
            else:
                draw.ellipse(
                    (img.width - 60, 20, img.width - 20, 60),
                    fill=(105, 105, 105),
                    outline=(0, 0, 0),
                )
                x1 = (
                    img.width
                    - 60
                    - 10
                    - self.bold_font[30].getbbox(
                        f"{self.number_to_text_with_suffix(data['contributors'][30])} Contributors"
                    )[2]
                )
                align_text_center(
                    (x1, 20, x1, 60),
                    text=f"{self.number_to_text_with_suffix(data['contributors'][30])} Contributors",
                    fill=(255, 255, 255),
                    font=self.bold_font[30],
                )
            y3 = list(data["graphic"]["contributors"].values()) + [0]
            fig.add_trace(
                go.Bar(
                    x=x,
                    y=y3,
                    name=_("Contributors"),
                    showlegend=False,
                    marker={"color": "rgb(105,105,105)"},
                )
            )
        if data["graphic"].get("voice") is not None:
            if size is None:
                draw.ellipse(
                    (img.width - 110, 321, img.width - 70, 361),
                    fill=(255, 0, 0),
                    outline=(0, 0, 0),
                )
                x1 = (
                    img.width
                    - 110
                    - 10
                    - self.bold_font[30].getbbox(
                        f"{self.number_to_text_with_suffix(data['voice_activity'][30])} Voice Hours"
                    )[2]
                )
                align_text_center(
                    (x1, 321, x1, 361),
                    text=f"{self.number_to_text_with_suffix(data['voice_activity'][30])} Voice Hour{'' if 0 < data['voice_activity'][30] <= 1 else 's'}",
                    fill=(255, 255, 255),
                    font=self.bold_font[30],
                )
            else:
                draw.ellipse(
                    (img.width - 60, 20, img.width - 20, 60), fill=(255, 0, 0), outline=(0, 0, 0)
                )
                x1 = (
                    img.width
                    - 60
                    - 10
                    - self.bold_font[30].getbbox(
                        f"{self.number_to_text_with_suffix(data['voice_activity'][30])} Voice Hours"
                    )[2]
                )
                align_text_center(
                    (x1, 20, x1, 60),
                    text=f"{self.number_to_text_with_suffix(data['voice_activity'][30])} Voice Hour{'' if 0 < data['voice_activity'][30] <= 1 else 's'}",
                    fill=(255, 255, 255),
                    font=self.bold_font[30],
                )
            y2 = list(data["graphic"]["voice"].values()) + [0]
            # y2_upper = [5.5, 3, 5.5, 8, 6, 3, 8, 5, 6, 5.5]
            # y2_lower = [4.5, 2, 4.4, 7, 4, 2, 7, 4, 5, 4.75]
            # y2_lower = y2_lower[::-1]
            # fig.add_trace(
            #     go.Scatter(
            #         x=x + x_rev,
            #         y=y2_upper + y2_lower,
            #         fill="toself",
            #         fillcolor="rgba(255,0,0,0.2)",
            #         line_color="rgba(255,255,255,0)",
            #         name="Voice",
            #         showlegend=False,
            #     )
            # )
            fig.add_trace(
                go.Scatter(
                    x=x,
                    y=y2,
                    line_color="rgb(255,0,0)",
                    name="Voice",
                    showlegend=False,
                    line={"width": 14},
                    fill="tozeroy",
                    fillcolor="rgba(255,0,0,0.2)",
                    # yaxis="y2"
                )
            )
        if data["graphic"].get("messages") is not None:
            if size is None:
                draw.ellipse((70, 321, 110, 361), fill=(0, 255, 0), outline=(0, 0, 0))
                align_text_center(
                    (120, 321, 120, 361),
                    text=f"{self.number_to_text_with_suffix(0)} Messages",
                    fill=(255, 255, 255),
                    font=self.bold_font[30],
                )
            else:
                draw.ellipse((20, 20, 60, 60), fill=(0, 255, 0), outline=(0, 0, 0))
                align_text_center(
                    (70, 20, 70, 60),
                    text=f"{self.number_to_text_with_suffix(0)} Messages",
                    fill=(255, 255, 255),
                    font=self.bold_font[30],
                )
            y1 = list(data["graphic"]["messages"].values()) + [0]
            # y1_upper = [2, 3, 4, 5, 6, 7, 8, 9, 10, 11]
            # y1_lower = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]
            # y1_lower = y1_lower[::-1]
            # fig.add_trace(
            #     go.Scatter(
            #         x=x + x_rev,
            #         y=y1_upper + y1_lower,
            #         fill="toself",
            #         fillcolor="rgba(0,255,0,0.2)",
            #         line_color="rgba(255,255,255,0)",
            #         name="Messages",
            #         showlegend=False,
            #     )
            # )
            # fig.add_trace(
            #     go.Scatter(
            #         x=x,
            #         y=y1,
            #         fill="toself",
            #         fillcolor="rgba(0,255,0,0.2)",
            #         line_color="rgba(255,255,255,0)",
            #         name="Messages",
            #         showlegend=False,
            #         line={"width": 15},
            #     )
            # )
            fig.add_trace(
                go.Scatter(
                    x=x,
                    y=y1,
                    line_color="rgb(0,255,0)",
                    name="Messages",
                    showlegend=False,
                    line={"width": 14},
                    fill="tozeroy",
                    fillcolor="rgba(0,255,0,0.2)",
                )
            )
        for key in (
            "activities",
            "top_messages_members",
            "top_messages_channels",
            "top_voice_members",
            "top_voice_channels",
            "top_members",
        ):
            if data["graphic"].get(key) is not None:
                fig.add_trace(
                    go.Pie(
                        labels=[
                            (
                                self.remove_unprintable_characters(label)
                                if key.split("_")[0] != "top"
                                else (
                                    self.get_member_display(_object.get_member(label))
                                    if key.split("_")[-1] == "members"
                                    else self.remove_unprintable_characters(
                                        _object.get_channel(label).name
                                    )
                                )
                            )[:20]
                            for label in data["graphic"][key].keys()
                        ],
                        values=list(data["graphic"][key].values()),
                        hole=0.3,
                        textfont_size=20,
                        textposition="inside",
                        textfont={"color": "rgb(255,255,255)"},
                        textinfo="percent+label",
                        marker={"line": {"color": "rgb(0,0,0)", "width": 2}},
                        direction="clockwise",
                    )
                )
        # fig.update_traces(mode="lines")
        fig.update_xaxes(type="category", tickvals=x)
        fig.update_yaxes(showgrid=True)

        graphic_bytes: bytes = fig.to_image(
            format="png",
            width=1840 if size is None else size[0],
            height=621 if size is None else size[1],
            scale=1,
        )
        image = Image.open(io.BytesIO(graphic_bytes))
        if size is None:
            img.paste(image, (50, 301, 1890, 922), mask=image.split()[3])
        else:
            img.paste(image, (0, 0, size[0], size[1]), mask=image.split()[3])

        if size is None:
            image = Image.open(self.icons["history"])
            image = image.resize((50, 50))
            img.paste(image, (30, 972, 80, 1022), mask=image.split()[3])
            utc_now = datetime.datetime.now(tz=datetime.timezone.utc)
            tracking_data_start_time = 0
            align_text_center(
                (90, 972, 90, 1022),
                text=_("Tracking data in this server for {interval_string}.").format(
                    interval_string=CogsUtils.get_interval_string(
                        tracking_data_start_time, utc_now=utc_now
                    )
                ),
                fill=(255, 255, 255),
                font=self.bold_font[30],
            )
            if members_type != "both":
                members_type_text = _("Only {members_type} are taken into account.").format(
                    members_type=members_type
                )
                image = Image.open(self.icons["person"])
                image = image.resize((50, 50))
                img.paste(
                    image,
                    (
                        1942 - 30 - self.bold_font[30].getbbox(members_type_text)[2] - 10 - 50,
                        972,
                        1942 - 30 - self.bold_font[30].getbbox(members_type_text)[2] - 10,
                        1022,
                    ),
                    mask=image.split()[3],
                )
                align_text_center(
                    (
                        1942 - 30 - self.bold_font[30].getbbox(members_type_text)[2],
                        972,
                        1942 - 30 - self.bold_font[30].getbbox(members_type_text)[2],
                        1022,
                    ),
                    text=members_type_text,
                    fill=(255, 255, 255),
                    font=self.bold_font[30],
                )

        if not to_file:
            return img
        buffer = io.BytesIO()
        img.save(buffer, format="png", optimize=True)
        buffer.seek(0)
        return discord.File(buffer, filename="image.png")

    async def generate_graphic(
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
        size: typing.Optional[typing.Tuple[int, int]] = None,
        data: typing.Optional[dict] = None,
        to_file: bool = True,
    ) -> typing.Union[Image.Image, discord.File]:
        if isinstance(_object, typing.Tuple):
            _object, _type = _object
        else:
            _type = None
        img: Image.Image = await self.generate_prefix_image(
            _object if _type is None else (_object, _type),
            size=(1942, 982 + 70) if size is None else size,
            to_file=False,
        )
        if data is None:
            data = await self.get_data(
                _object if _type is None else (_object, _type), members_type=members_type
            )
        return await asyncio.to_thread(
            self._generate_graphic,
            _object=_object if _type is None else (_object, _type),
            members_type=members_type,
            size=size,
            data=data,
            to_file=to_file,
            img=img,
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
                # Server Lookback. box = 606 / empty = 30 | 2 cases / box = 117 / empty = 30
                draw.rounded_rectangle((30, 204, 636, 585), radius=15, fill=(47, 49, 54))
                align_text_center(
                    (50, 214, 50, 284),
                    text=_("Server Lookback"),
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
                    text=_("Text"),
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
                    text=_("Voice"),
                    fill=(255, 255, 255),
                    font=self.bold_font[36],
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
                    text=_("Messages"),
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
                    text=_("1d"),
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
                    text=_("7d"),
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
                    text=_("30d"),
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
                    text=_("Voice Activity"),
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
                    text=_("1d"),
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
                    text=_("7d"),
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
                    text=_("30d"),
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
                    text=_("Server Ranks"),
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
                    text=_("Voice"),
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
                    text=_("Top Channels & Activity"),
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
                        text=_("Graphic"),
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

            elif _type == "activities":
                # Top Activities (Applications). box = 925 / empty = 30 | 30 cases / box = 76 / empty = 16
                draw.rounded_rectangle((30, 204, 955, 996), radius=15, fill=(47, 49, 54))
                align_text_center(
                    (50, 214, 50, 284),
                    text=_("Top Activities (Applications)"),
                    fill=(255, 255, 255),
                    font=self.bold_font[40],
                )
                image = Image.open(self.icons["game"])
                image = image.resize((70, 70))
                img.paste(image, (865, 214, 935, 284), mask=image.split()[3])
                top_activities = list(data["top_activities"])
                current_y = 301
                for i in range(10):
                    draw.rounded_rectangle(
                        (50, current_y, 935, current_y + 58), radius=15, fill=(32, 34, 37)
                    )
                    draw.rounded_rectangle(
                        (50, current_y, 580, current_y + 58), radius=15, fill=(24, 26, 27)
                    )
                    if len(top_activities) >= i + 1:
                        # align_text_center((50, current_y, 100, current_y + 50), text=str(i), fill=(255, 255, 255), font=self.bold_font[36])
                        # align_text_center((100, current_y, 935, current_y + 50), text=top_activities[i - 1], fill=(255, 255, 255), font=self.font[36])
                        align_text_center(
                            (50, current_y, 580, current_y + 58),
                            text=self.remove_unprintable_characters(top_activities[i][:25]),
                            fill=(255, 255, 255),
                            font=self.bold_font[36],
                        )
                        align_text_center(
                            (580, current_y, 935, current_y + 58),
                            text=f"{self.number_to_text_with_suffix(0)} hours",
                            fill=(255, 255, 255),
                            font=self.font[36],
                        )
                    current_y += 58 + 10

                # Graphic. box = 925 / empty = 30 | 1 case / box = 76 / empty = 16
                draw.rounded_rectangle((985, 204, 1910, 996), radius=15, fill=(47, 49, 54))
                align_text_center(
                    (1005, 214, 1005, 284),
                    text=_("Graphic"),
                    fill=(255, 255, 255),
                    font=self.bold_font[40],
                )
                image = Image.open(self.icons["query_stats"])
                image = image.resize((70, 70))
                img.paste(image, (1820, 214, 1890, 284), mask=image.split()[3])
                draw.rounded_rectangle((1005, 301, 1890, 976), radius=15, fill=(32, 34, 37))
                image: Image.Image = graphic
                image = image.resize((885, 675))
                img.paste(image, (1005, 301, 1890, 976))

        elif isinstance(_object, discord.Guild):
            if _type is None:
                # Server Lookback. box = 606 / empty = 30 | 2 cases / box = 117 / empty = 30
                draw.rounded_rectangle((30, 204, 636, 585), radius=15, fill=(47, 49, 54))
                align_text_center(
                    (50, 214, 50, 284),
                    text=_("Server Lookback"),
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
                    text=_("Text"),
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
                    text=_("Voice"),
                    fill=(255, 255, 255),
                    font=self.bold_font[36],
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
                    text=_("Messages"),
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
                    text=_("1d"),
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
                    text=_("7d"),
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
                    text=_("30d"),
                    fill=(255, 255, 255),
                    font=self.bold_font[36],
                )
                align_text_center(
                    (910, 489, 1254, 565),
                    text=f"{self.number_to_text_with_suffix(0)} messages",
                    fill=(255, 255, 255),
                    font=self.font[36],
                )

                # Voice Activity. box = 606 / empty = 30 | 3 cases / box = 76 / empty = 16
                draw.rounded_rectangle((1306, 204, 1912, 585), radius=15, fill=(47, 49, 54))
                align_text_center(
                    (1326, 214, 1326, 284),
                    text=_("Voice Activity"),
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
                    text=_("1d"),
                    fill=(255, 255, 255),
                    font=self.bold_font[36],
                )
                align_text_center(
                    (1548, 301, 1892, 377),
                    text=f"{self.number_to_text_with_suffix(data['voice_activity'][1])} hour{'' if 0 < data['voice_activity'][1] <= 1 else 's'}",
                    fill=(255, 255, 255),
                    font=self.font[36],
                )
                draw.rounded_rectangle((1326, 395, 1892, 471), radius=15, fill=(32, 34, 37))
                draw.rounded_rectangle((1326, 395, 1548, 471), radius=15, fill=(24, 26, 27))
                align_text_center(
                    (1326, 395, 1548, 471),
                    text=_("7d"),
                    fill=(255, 255, 255),
                    font=self.bold_font[36],
                )
                align_text_center(
                    (1548, 395, 1892, 471),
                    text=f"{self.number_to_text_with_suffix(data['voice_activity'][7])} hour{'' if 0 < data['voice_activity'][7] <= 1 else 's'}",
                    fill=(255, 255, 255),
                    font=self.font[36],
                )
                draw.rounded_rectangle((1326, 489, 1892, 565), radius=15, fill=(32, 34, 37))
                draw.rounded_rectangle((1326, 489, 1548, 565), radius=15, fill=(24, 26, 27))
                align_text_center(
                    (1326, 489, 1548, 565),
                    text=_("30d"),
                    fill=(255, 255, 255),
                    font=self.bold_font[36],
                )
                align_text_center(
                    (1548, 489, 1892, 565),
                    text=f"{self.number_to_text_with_suffix(data['voice_activity'][30])} hour{'' if 0 < data['voice_activity'][30] <= 1 else 's'}",
                    fill=(255, 255, 255),
                    font=self.font[36],
                )

                # Top Members. box = 925 / empty = 30 | 3 cases / box = 117 / empty = 30
                draw.rounded_rectangle((30, 615, 955, 996), radius=15, fill=(47, 49, 54))
                align_text_center(
                    (50, 625, 50, 695),
                    text=_("Top Members"),
                    fill=(255, 255, 255),
                    font=self.bold_font[40],
                )
                image = Image.open(self.icons["person"])
                image = image.resize((70, 70))
                img.paste(image, (865, 625, 935, 695), mask=image.split()[3])
                image = Image.open(self.icons["#"])
                image = image.resize((70, 70))
                img.paste(image, (50, 735, 120, 805), mask=image.split()[3])
                draw.rounded_rectangle((150, 712, 935, 829), radius=15, fill=(32, 34, 37))
                draw.rounded_rectangle((150, 712, 600, 829), radius=15, fill=(24, 26, 27))
                if (
                    data["top_members"]["text"]["member"] is not None
                    and data["top_members"]["text"]["value"] is not None
                ):
                    align_text_center(
                        (150, 712, 600, 829),
                        text=self.get_member_display(
                            _object.get_member(data["top_members"]["text"]["member"])
                        ),
                        fill=(255, 255, 255),
                        font=self.bold_font[36],
                    )
                    align_text_center(
                        (600, 712, 935, 829),
                        text=f"{self.number_to_text_with_suffix(data['top_members']['text']['value'])} message{'' if 0 < data['top_members']['text']['value'] <= 1 else 's'}",
                        fill=(255, 255, 255),
                        font=self.font[36],
                    )
                image = Image.open(self.icons["sound"])
                image = image.resize((70, 70))
                img.paste(image, (50, 882, 120, 952), mask=image.split()[3])
                draw.rounded_rectangle((150, 859, 935, 976), radius=15, fill=(32, 34, 37))
                draw.rounded_rectangle((150, 859, 600, 976), radius=15, fill=(24, 26, 27))
                if (
                    data["top_members"]["voice"]["member"] is not None
                    and data["top_members"]["voice"]["value"] is not None
                ):
                    align_text_center(
                        (150, 859, 600, 976),
                        text=self.get_member_display(
                            _object.get_member(data["top_members"]["voice"]["member"])
                        ),
                        fill=(255, 255, 255),
                        font=self.bold_font[36],
                    )
                    align_text_center(
                        (600, 859, 935, 976),
                        text=f"{self.number_to_text_with_suffix(data['top_members']['voice']['value'])} hour{'' if 0 < data['top_members']['voice']['value'] <= 1 else 's'}",
                        fill=(255, 255, 255),
                        font=self.font[36],
                    )

                # Top Channels. box = 925 / empty = 30 | 3 cases / box = 76 / empty = 16
                draw.rounded_rectangle((985, 615, 1910, 996), radius=15, fill=(47, 49, 54))
                align_text_center(
                    (1005, 625, 1005, 695),
                    text=_("Top Channels"),
                    fill=(255, 255, 255),
                    font=self.bold_font[40],
                )
                image = Image.open(self.icons["#"])
                image = image.resize((70, 70))
                img.paste(image, (1820, 625, 1890, 695), mask=image.split()[3])
                image = Image.open(self.icons["#"])
                image = image.resize((70, 70))
                img.paste(image, (1005, 735, 1075, 805), mask=image.split()[3])
                draw.rounded_rectangle((1105, 712, 1890, 829), radius=15, fill=(32, 34, 37))
                draw.rounded_rectangle((1105, 712, 1555, 829), radius=15, fill=(24, 26, 27))
                if (
                    data["top_channels"]["text"]["channel"] is not None
                    and data["top_channels"]["text"]["value"] is not None
                ):
                    align_text_center(
                        (1105, 712, 1555, 829),
                        text=_object.get_channel(data["top_channels"]["text"]["channel"]).name,
                        fill=(255, 255, 255),
                        font=self.bold_font[36],
                    )
                    align_text_center(
                        (1555, 712, 1890, 829),
                        text=f"{self.number_to_text_with_suffix(data['top_channels']['text']['value'])} message{'' if 0 < data['top_channels']['text']['value'] <= 1 else 's'}",
                        fill=(255, 255, 255),
                        font=self.font[36],
                    )
                image = Image.open(self.icons["sound"])
                image = image.resize((70, 70))
                img.paste(image, (1005, 882, 1075, 952), mask=image.split()[3])
                draw.rounded_rectangle((1105, 859, 1890, 976), radius=15, fill=(32, 34, 37))
                draw.rounded_rectangle((1105, 859, 1555, 976), radius=15, fill=(24, 26, 27))
                if (
                    data["top_channels"]["voice"]["channel"] is not None
                    and data["top_channels"]["voice"]["value"] is not None
                ):
                    align_text_center(
                        (1105, 859, 1555, 976),
                        text=self.remove_unprintable_characters(
                            _object.get_channel(data["top_channels"]["voice"]["channel"]).name
                        ),
                        fill=(255, 255, 255),
                        font=self.bold_font[36],
                    )
                    align_text_center(
                        (1555, 859, 1890, 976),
                        text=f"{self.number_to_text_with_suffix(data['top_channels']['voice']['value'])} hour{'' if 0 < data['top_channels']['voice']['value'] <= 1 else 's'}",
                        fill=(255, 255, 255),
                        font=self.font[36],
                    )

            elif _type == "messages":
                # Server Lookback. box = 606 / empty = 30 | 1 case / box = 264 / empty = 0
                draw.rounded_rectangle((30, 204, 636, 585), radius=15, fill=(47, 49, 54))
                align_text_center(
                    (50, 214, 50, 284),
                    text=_("Server Lookback"),
                    fill=(255, 255, 255),
                    font=self.bold_font[40],
                )
                image = Image.open(self.icons["history"])
                image = image.resize((70, 70))
                img.paste(image, (546, 214, 616, 284), mask=image.split()[3])
                draw.rounded_rectangle((50, 301, 616, 565), radius=15, fill=(32, 34, 37))
                align_text_center(
                    (50, 351, 616, 433),
                    text=f"{self.number_to_text_with_suffix(0)}",
                    fill=(255, 255, 255),
                    font=self.bold_font[60],
                )
                align_text_center(
                    (50, 433, 616, 515),
                    text=f"messages",
                    fill=(255, 255, 255),
                    font=self.bold_font[60],
                )

                # Messages. box = 606 / empty = 30 | 3 cases / box = 76 / empty = 16
                draw.rounded_rectangle((668, 204, 1274, 585), radius=15, fill=(47, 49, 54))
                align_text_center(
                    (688, 214, 688, 284),
                    text=_("Messages"),
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
                    text=_("1d"),
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
                    text=_("7d"),
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
                    text=_("30d"),
                    fill=(255, 255, 255),
                    font=self.bold_font[36],
                )
                align_text_center(
                    (910, 489, 1254, 565),
                    text=f"{self.number_to_text_with_suffix(0)} messages",
                    fill=(255, 255, 255),
                    font=self.font[36],
                )

                # Contributors. box = 606 / empty = 30 | 3 cases / box = 76 / empty = 16
                draw.rounded_rectangle((1306, 204, 1912, 585), radius=15, fill=(47, 49, 54))
                align_text_center(
                    (1326, 214, 1326, 284),
                    text=_("Contributors"),
                    fill=(255, 255, 255),
                    font=self.bold_font[40],
                )
                image = Image.open(self.icons["person"])
                image = image.resize((70, 70))
                img.paste(image, (1822, 214, 1892, 284), mask=image.split()[3])
                draw.rounded_rectangle((1326, 301, 1892, 377), radius=15, fill=(32, 34, 37))
                draw.rounded_rectangle((1326, 301, 1548, 377), radius=15, fill=(24, 26, 27))
                align_text_center(
                    (1326, 301, 1548, 377),
                    text=_("1d"),
                    fill=(255, 255, 255),
                    font=self.bold_font[36],
                )
                align_text_center(
                    (1548, 301, 1892, 377),
                    text=f"{self.number_to_text_with_suffix(data['contributors'][1])} member{'' if 0 < data['contributors'][1] <= 1 else 's'}",
                    fill=(255, 255, 255),
                    font=self.font[36],
                )
                draw.rounded_rectangle((1326, 395, 1892, 471), radius=15, fill=(32, 34, 37))
                draw.rounded_rectangle((1326, 395, 1548, 471), radius=15, fill=(24, 26, 27))
                align_text_center(
                    (1326, 395, 1548, 471),
                    text=_("7d"),
                    fill=(255, 255, 255),
                    font=self.bold_font[36],
                )
                align_text_center(
                    (1548, 395, 1892, 471),
                    text=f"{self.number_to_text_with_suffix(data['contributors'][7])} member{'' if 0 < data['contributors'][7] <= 1 else 's'}",
                    fill=(255, 255, 255),
                    font=self.font[36],
                )
                draw.rounded_rectangle((1326, 489, 1892, 565), radius=15, fill=(32, 34, 37))
                draw.rounded_rectangle((1326, 489, 1548, 565), radius=15, fill=(24, 26, 27))
                align_text_center(
                    (1326, 489, 1548, 565),
                    text=_("30d"),
                    fill=(255, 255, 255),
                    font=self.bold_font[36],
                )
                align_text_center(
                    (1548, 489, 1892, 565),
                    text=f"{self.number_to_text_with_suffix(data['contributors'][30])} member{'' if 0 < data['contributors'][30] <= 1 else 's'}",
                    fill=(255, 255, 255),
                    font=self.font[36],
                )

                # Top Messages Members. box = 925 / empty = 30 | 3 cases / box = 76 / empty = 16
                draw.rounded_rectangle((30, 615, 955, 996), radius=15, fill=(47, 49, 54))
                align_text_center(
                    (50, 625, 50, 695),
                    text=_("Top Messages Members"),
                    fill=(255, 255, 255),
                    font=self.bold_font[40],
                )
                image = Image.open(self.icons["#"])
                image = image.resize((70, 70))
                img.paste(image, (865, 625, 935, 695), mask=image.split()[3])
                data["top_messages_members"] = list(data["top_messages_members"].items())
                draw.rounded_rectangle((50, 712, 935, 788), radius=15, fill=(32, 34, 37))
                draw.rounded_rectangle((50, 712, 600, 788), radius=15, fill=(24, 26, 27))
                if len(data["top_messages_members"]) >= 1:
                    align_text_center(
                        (50, 712, 600, 788),
                        text=self.get_member_display(
                            _object.get_member(data["top_messages_members"][0][0])
                        ),
                        fill=(255, 255, 255),
                        font=self.bold_font[36],
                    )
                    align_text_center(
                        (600, 712, 935, 788),
                        text=f"{self.number_to_text_with_suffix(data['top_messages_members'][0][1])} message{'' if 0 < data['top_messages_members'][0][1] <= 1 else 's'}",
                        fill=(255, 255, 255),
                        font=self.font[36],
                    )
                draw.rounded_rectangle((50, 804, 935, 880), radius=15, fill=(32, 34, 37))
                draw.rounded_rectangle((50, 804, 600, 880), radius=15, fill=(24, 26, 27))
                if len(data["top_messages_members"]) >= 2:
                    align_text_center(
                        (50, 804, 600, 880),
                        text=self.get_member_display(
                            _object.get_member(data["top_messages_members"][1][0])
                        ),
                        fill=(255, 255, 255),
                        font=self.bold_font[36],
                    )
                    align_text_center(
                        (600, 804, 935, 880),
                        text=f"{self.number_to_text_with_suffix(data['top_messages_members'][1][1])} message{'' if 0 < data['top_messages_members'][1][1] <= 1 else 's'}",
                        fill=(255, 255, 255),
                        font=self.font[36],
                    )
                draw.rounded_rectangle((50, 896, 935, 972), radius=15, fill=(32, 34, 37))
                draw.rounded_rectangle((50, 896, 600, 972), radius=15, fill=(24, 26, 27))
                if len(data["top_messages_members"]) >= 3:
                    align_text_center(
                        (50, 896, 600, 972),
                        text=self.get_member_display(
                            _object.get_member(data["top_messages_members"][2][0])
                        ),
                        fill=(255, 255, 255),
                        font=self.bold_font[36],
                    )
                    align_text_center(
                        (600, 896, 935, 972),
                        text=f"{self.number_to_text_with_suffix(data['top_messages_members'][2][1])} message{'' if 0 < data['top_messages_members'][2][1] <= 1 else 's'}",
                        fill=(255, 255, 255),
                        font=self.font[36],
                    )

                # Top Messages Channels. box = 925 / empty = 30 | 3 cases / box = 76 / empty = 16
                draw.rounded_rectangle((985, 615, 1910, 996), radius=15, fill=(47, 49, 54))
                align_text_center(
                    (1005, 625, 1005, 695),
                    text=_("Top Messages Channels"),
                    fill=(255, 255, 255),
                    font=self.bold_font[40],
                )
                image = Image.open(self.icons["#"])
                image = image.resize((70, 70))
                img.paste(image, (1820, 625, 1890, 695), mask=image.split()[3])
                data["top_messages_channels"] = list(data["top_messages_channels"].items())
                draw.rounded_rectangle((1005, 712, 1890, 788), radius=15, fill=(32, 34, 37))
                draw.rounded_rectangle((1005, 712, 1555, 788), radius=15, fill=(24, 26, 27))
                if len(data["top_messages_channels"]) >= 1:
                    align_text_center(
                        (1005, 712, 1555, 788),
                        text=self.remove_unprintable_characters(
                            _object.get_channel(data["top_messages_channels"][0][0]).name
                        ),
                        fill=(255, 255, 255),
                        font=self.bold_font[36],
                    )
                    align_text_center(
                        (1555, 712, 1890, 788),
                        text=f"{self.number_to_text_with_suffix(data['top_messages_channels'][0][1])} message{'' if 0 < data['top_messages_channels'][0][1] <= 1 else 's'}",
                        fill=(255, 255, 255),
                        font=self.font[36],
                    )
                draw.rounded_rectangle((1005, 804, 1890, 880), radius=15, fill=(32, 34, 37))
                draw.rounded_rectangle((1005, 804, 1555, 880), radius=15, fill=(24, 26, 27))
                if len(data["top_messages_channels"]) >= 2:
                    align_text_center(
                        (1005, 804, 1555, 880),
                        text=self.remove_unprintable_characters(
                            _object.get_channel(data["top_messages_channels"][1][0]).name
                        ),
                        fill=(255, 255, 255),
                        font=self.bold_font[36],
                    )
                    align_text_center(
                        (1555, 804, 1890, 880),
                        text=f"{self.number_to_text_with_suffix(data['top_messages_channels'][1][1])} message{'' if 0 < data['top_messages_channels'][1][1] <= 1 else 's'}",
                        fill=(255, 255, 255),
                        font=self.font[36],
                    )
                draw.rounded_rectangle((1005, 896, 1890, 972), radius=15, fill=(32, 34, 37))
                draw.rounded_rectangle((1005, 896, 1555, 972), radius=15, fill=(24, 26, 27))
                if len(data["top_messages_channels"]) >= 3:
                    align_text_center(
                        (1005, 896, 1555, 972),
                        text=self.remove_unprintable_characters(
                            _object.get_channel(data["top_messages_channels"][2][0]).name
                        ),
                        fill=(255, 255, 255),
                        font=self.bold_font[36],
                    )
                    align_text_center(
                        (1555, 896, 1890, 972),
                        text=f"{self.number_to_text_with_suffix(data['top_messages_channels'][2][1])} message{'' if 0 < data['top_messages_channels'][2][1] <= 1 else 's'}",
                        fill=(255, 255, 255),
                        font=self.font[36],
                    )

            elif _type == "voice":
                # Server Lookback. box = 606 / empty = 30 | 1 case / box = 264 / empty = 0
                draw.rounded_rectangle((30, 204, 636, 585), radius=15, fill=(47, 49, 54))
                align_text_center(
                    (50, 214, 50, 284),
                    text=_("Server Lookback"),
                    fill=(255, 255, 255),
                    font=self.bold_font[40],
                )
                image = Image.open(self.icons["history"])
                image = image.resize((70, 70))
                img.paste(image, (546, 214, 616, 284), mask=image.split()[3])
                draw.rounded_rectangle((50, 301, 616, 565), radius=15, fill=(32, 34, 37))
                align_text_center(
                    (50, 351, 616, 433),
                    text=f"{self.number_to_text_with_suffix(0)}",
                    fill=(255, 255, 255),
                    font=self.bold_font[60],
                )
                align_text_center(
                    (50, 433, 616, 515),
                    text=f"hours",
                    fill=(255, 255, 255),
                    font=self.bold_font[60],
                )

                # Voice Activity. box = 606 / empty = 30 | 3 cases / box = 76 / empty = 16
                draw.rounded_rectangle((668, 204, 1274, 585), radius=15, fill=(47, 49, 54))
                align_text_center(
                    (688, 214, 688, 284),
                    text=_("Voice Activity"),
                    fill=(255, 255, 255),
                    font=self.bold_font[40],
                )
                image = Image.open(self.icons["sound"])
                image = image.resize((70, 70))
                img.paste(image, (1184, 214, 1254, 284), mask=image.split()[3])
                draw.rounded_rectangle((688, 301, 1254, 377), radius=15, fill=(32, 34, 37))
                draw.rounded_rectangle((688, 301, 910, 377), radius=15, fill=(24, 26, 27))
                align_text_center(
                    (688, 301, 910, 377),
                    text=_("1d"),
                    fill=(255, 255, 255),
                    font=self.bold_font[36],
                )
                align_text_center(
                    (910, 301, 1254, 377),
                    text=f"{self.number_to_text_with_suffix(data['voice_activity'][1])} hour{'' if 0 < data['voice_activity'][1] <= 1 else 's'}",
                    fill=(255, 255, 255),
                    font=self.font[36],
                )
                draw.rounded_rectangle((688, 395, 1254, 471), radius=15, fill=(32, 34, 37))
                draw.rounded_rectangle((688, 395, 910, 471), radius=15, fill=(24, 26, 27))
                align_text_center(
                    (688, 395, 910, 471),
                    text=_("7d"),
                    fill=(255, 255, 255),
                    font=self.bold_font[36],
                )
                align_text_center(
                    (910, 395, 1254, 471),
                    text=f"{self.number_to_text_with_suffix(data['voice_activity'][7])} hour{'' if 0 < data['voice_activity'][7] <= 1 else 's'}",
                    fill=(255, 255, 255),
                    font=self.font[36],
                )
                draw.rounded_rectangle((688, 489, 1254, 565), radius=15, fill=(32, 34, 37))
                draw.rounded_rectangle((688, 489, 910, 565), radius=15, fill=(24, 26, 27))
                align_text_center(
                    (688, 489, 910, 565),
                    text=_("30d"),
                    fill=(255, 255, 255),
                    font=self.bold_font[36],
                )
                align_text_center(
                    (910, 489, 1254, 565),
                    text=f"{self.number_to_text_with_suffix(data['voice_activity'][30])} hour{'' if 0 < data['voice_activity'][30] <= 1 else 's'}",
                    fill=(255, 255, 255),
                    font=self.font[36],
                )

                # Contributors. box = 606 / empty = 30 | 3 cases / box = 76 / empty = 16
                draw.rounded_rectangle((1306, 204, 1912, 585), radius=15, fill=(47, 49, 54))
                align_text_center(
                    (1326, 214, 1326, 284),
                    text=_("Contributors"),
                    fill=(255, 255, 255),
                    font=self.bold_font[40],
                )
                image = Image.open(self.icons["person"])
                image = image.resize((70, 70))
                img.paste(image, (1822, 214, 1892, 284), mask=image.split()[3])
                draw.rounded_rectangle((1326, 301, 1892, 377), radius=15, fill=(32, 34, 37))
                draw.rounded_rectangle((1326, 301, 1548, 377), radius=15, fill=(24, 26, 27))
                align_text_center(
                    (1326, 301, 1548, 377),
                    text=_("1d"),
                    fill=(255, 255, 255),
                    font=self.bold_font[36],
                )
                align_text_center(
                    (1548, 301, 1892, 377),
                    text=f"{self.number_to_text_with_suffix(data['contributors'][1])} member{'' if 0 < data['contributors'][1] <= 1 else 's'}",
                    fill=(255, 255, 255),
                    font=self.font[36],
                )
                draw.rounded_rectangle((1326, 395, 1892, 471), radius=15, fill=(32, 34, 37))
                draw.rounded_rectangle((1326, 395, 1548, 471), radius=15, fill=(24, 26, 27))
                align_text_center(
                    (1326, 395, 1548, 471),
                    text=_("7d"),
                    fill=(255, 255, 255),
                    font=self.bold_font[36],
                )
                align_text_center(
                    (1548, 395, 1892, 471),
                    text=f"{self.number_to_text_with_suffix(data['contributors'][7])} member{'' if 0 < data['contributors'][7] <= 1 else 's'}",
                    fill=(255, 255, 255),
                    font=self.font[36],
                )
                draw.rounded_rectangle((1326, 489, 1892, 565), radius=15, fill=(32, 34, 37))
                draw.rounded_rectangle((1326, 489, 1548, 565), radius=15, fill=(24, 26, 27))
                align_text_center(
                    (1326, 489, 1548, 565),
                    text=_("30d"),
                    fill=(255, 255, 255),
                    font=self.bold_font[36],
                )
                align_text_center(
                    (1548, 489, 1892, 565),
                    text=f"{self.number_to_text_with_suffix(data['contributors'][30])} member{'' if 0 < data['contributors'][30] <= 1 else 's'}",
                    fill=(255, 255, 255),
                    font=self.font[36],
                )

                # Top Voice Members. box = 925 / empty = 30 | 3 cases / box = 76 / empty = 16
                draw.rounded_rectangle((30, 615, 955, 996), radius=15, fill=(47, 49, 54))
                align_text_center(
                    (50, 625, 50, 695),
                    text=_("Top Voice Members"),
                    fill=(255, 255, 255),
                    font=self.bold_font[40],
                )
                image = Image.open(self.icons["#"])
                image = image.resize((70, 70))
                img.paste(image, (865, 625, 935, 695), mask=image.split()[3])
                data["top_voice_members"] = list(data["top_voice_members"].items())
                draw.rounded_rectangle((50, 712, 935, 788), radius=15, fill=(32, 34, 37))
                draw.rounded_rectangle((50, 712, 600, 788), radius=15, fill=(24, 26, 27))
                if len(data["top_voice_members"]) >= 1:
                    align_text_center(
                        (50, 712, 600, 788),
                        text=self.get_member_display(
                            _object.get_member(data["top_voice_members"][0][0])
                        ),
                        fill=(255, 255, 255),
                        font=self.bold_font[36],
                    )
                    align_text_center(
                        (600, 712, 935, 788),
                        text=f"{self.number_to_text_with_suffix(data['top_voice_members'][0][1])} hour{'' if 0 < data['top_voice_members'][0][1] <= 1 else 's'}",
                        fill=(255, 255, 255),
                        font=self.font[36],
                    )
                draw.rounded_rectangle((50, 804, 935, 880), radius=15, fill=(32, 34, 37))
                draw.rounded_rectangle((50, 804, 600, 880), radius=15, fill=(24, 26, 27))
                if len(data["top_voice_members"]) >= 2:
                    align_text_center(
                        (50, 804, 600, 880),
                        text=self.get_member_display(
                            _object.get_member(data["top_voice_members"][1][0])
                        ),
                        fill=(255, 255, 255),
                        font=self.bold_font[36],
                    )
                    align_text_center(
                        (600, 804, 935, 880),
                        text=f"{self.number_to_text_with_suffix(data['top_voice_members'][1][1])} hour{'' if 0 < data['top_voice_members'][1][1] <= 1 else 's'}",
                        fill=(255, 255, 255),
                        font=self.font[36],
                    )
                draw.rounded_rectangle((50, 896, 935, 972), radius=15, fill=(32, 34, 37))
                draw.rounded_rectangle((50, 896, 600, 972), radius=15, fill=(24, 26, 27))
                if len(data["top_voice_members"]) >= 3:
                    align_text_center(
                        (50, 896, 600, 972),
                        text=self.get_member_display(
                            _object.get_member(data["top_voice_members"][2][0])
                        ),
                        fill=(255, 255, 255),
                        font=self.bold_font[36],
                    )
                    align_text_center(
                        (600, 896, 935, 972),
                        text=f"{self.number_to_text_with_suffix(data['top_voice_members'][2][1])} hour{'' if 0 < data['top_voice_members'][2][1] <= 1 else 's'}",
                        fill=(255, 255, 255),
                        font=self.font[36],
                    )

                # Top Voice Channels. box = 925 / empty = 30 | 3 cases / box = 76 / empty = 16
                draw.rounded_rectangle((985, 615, 1910, 996), radius=15, fill=(47, 49, 54))
                align_text_center(
                    (1005, 625, 1005, 695),
                    text=_("Top Voice Channels"),
                    fill=(255, 255, 255),
                    font=self.bold_font[40],
                )
                image = Image.open(self.icons["#"])
                image = image.resize((70, 70))
                img.paste(image, (1820, 625, 1890, 695), mask=image.split()[3])
                data["top_voice_channels"] = list(data["top_voice_channels"].items())
                draw.rounded_rectangle((1005, 712, 1890, 788), radius=15, fill=(32, 34, 37))
                draw.rounded_rectangle((1005, 712, 1555, 788), radius=15, fill=(24, 26, 27))
                if len(data["top_voice_channels"]) >= 1:
                    align_text_center(
                        (1005, 712, 1555, 788),
                        text=self.remove_unprintable_characters(
                            _object.get_channel(data["top_voice_channels"][0][0]).name
                        ),
                        fill=(255, 255, 255),
                        font=self.bold_font[36],
                    )
                    align_text_center(
                        (1555, 712, 1890, 788),
                        text=f"{self.number_to_text_with_suffix(data['top_voice_channels'][0][1])} hour{'' if 0 < data['top_voice_channels'][0][1] <= 1 else 's'}",
                        fill=(255, 255, 255),
                        font=self.font[36],
                    )
                draw.rounded_rectangle((1005, 804, 1890, 880), radius=15, fill=(32, 34, 37))
                draw.rounded_rectangle((1005, 804, 1555, 880), radius=15, fill=(24, 26, 27))
                if len(data["top_voice_channels"]) >= 2:
                    align_text_center(
                        (1005, 804, 1555, 880),
                        text=self.remove_unprintable_characters(
                            _object.get_channel(data["top_voice_channels"][1][0]).name
                        ),
                        fill=(255, 255, 255),
                        font=self.bold_font[36],
                    )
                    align_text_center(
                        (1555, 804, 1890, 880),
                        text=f"{self.number_to_text_with_suffix(data['top_voice_channels'][1][1])} hour{'' if 0 < data['top_voice_channels'][1][1] <= 1 else 's'}",
                        fill=(255, 255, 255),
                        font=self.font[36],
                    )
                draw.rounded_rectangle((1005, 896, 1890, 972), radius=15, fill=(32, 34, 37))
                draw.rounded_rectangle((1005, 896, 1555, 972), radius=15, fill=(24, 26, 27))
                if len(data["top_voice_channels"]) >= 3:
                    align_text_center(
                        (1005, 896, 1555, 972),
                        text=self.remove_unprintable_characters(
                            _object.get_channel(data["top_voice_channels"][2][0]).name
                        ),
                        fill=(255, 255, 255),
                        font=self.bold_font[36],
                    )
                    align_text_center(
                        (1555, 896, 1890, 972),
                        text=f"{self.number_to_text_with_suffix(data['top_voice_channels'][2][1])} hour{'' if 0 < data['top_voice_channels'][2][1] <= 1 else 's'}",
                        fill=(255, 255, 255),
                        font=self.font[36],
                    )

            elif _type == "activities":
                # Top Activities (Applications). box = 925 / empty = 30 | 30 cases / box = 76 / empty = 16
                draw.rounded_rectangle((30, 204, 955, 996), radius=15, fill=(47, 49, 54))
                align_text_center(
                    (50, 214, 50, 284),
                    text=_("Top Activities (Applications)"),
                    fill=(255, 255, 255),
                    font=self.bold_font[40],
                )
                image = Image.open(self.icons["game"])
                image = image.resize((70, 70))
                img.paste(image, (865, 214, 935, 284), mask=image.split()[3])
                top_activities = list(data["top_activities"])
                current_y = 301
                for i in range(10):
                    draw.rounded_rectangle(
                        (50, current_y, 935, current_y + 58), radius=15, fill=(32, 34, 37)
                    )
                    draw.rounded_rectangle(
                        (50, current_y, 580, current_y + 58), radius=15, fill=(24, 26, 27)
                    )
                    if len(top_activities) >= i + 1:
                        # align_text_center((50, current_y, 100, current_y + 50), text=str(i), fill=(255, 255, 255), font=self.bold_font[36])
                        # align_text_center((100, current_y, 935, current_y + 50), text=top_activities[i - 1], fill=(255, 255, 255), font=self.font[36])
                        align_text_center(
                            (50, current_y, 580, current_y + 58),
                            text=self.remove_unprintable_characters(top_activities[i][:25]),
                            fill=(255, 255, 255),
                            font=self.bold_font[36],
                        )
                        align_text_center(
                            (580, current_y, 935, current_y + 58),
                            text=f"{self.number_to_text_with_suffix(data['top_activities'][top_activities[i]])} hour{'' if 0 < data['top_activities'][top_activities[i]] <= 1 else 's'}",
                            fill=(255, 255, 255),
                            font=self.font[36],
                        )
                    current_y += 58 + 10

                # Graphic. box = 925 / empty = 30 | 1 case / box = 76 / empty = 16
                draw.rounded_rectangle((985, 204, 1910, 996), radius=15, fill=(47, 49, 54))
                align_text_center(
                    (1005, 214, 1005, 284),
                    text=_("Graphic"),
                    fill=(255, 255, 255),
                    font=self.bold_font[40],
                )
                image = Image.open(self.icons["query_stats"])
                image = image.resize((70, 70))
                img.paste(image, (1820, 214, 1890, 284), mask=image.split()[3])
                draw.rounded_rectangle((1005, 301, 1890, 976), radius=15, fill=(32, 34, 37))
                image: Image.Image = graphic
                image = image.resize((885, 675))
                img.paste(image, (1005, 301, 1890, 976))

            elif isinstance(_type, typing.Tuple):
                if _type[0] in ("top", "weekly", "monthly"):
                    # Top Messages/Voice Members/Channels. box = 925 / empty = 30 | 30 cases / box = 76 / empty = 16
                    draw.rounded_rectangle((30, 204, 955, 996), radius=15, fill=(47, 49, 54))
                    align_text_center(
                        (50, 214, 50, 284),
                        text=_("Top")
                        + f" {_('Messages') if _type[1] == 'messages' else _('Voice')} {_('Members') if _type[2] == 'members' else _('Channels')}",
                        fill=(255, 255, 255),
                        font=self.bold_font[40],
                    )
                    image = Image.open(self.icons["person" if _type[2] == "members" else "#"])
                    image = image.resize((70, 70))
                    img.paste(image, (865, 214, 935, 284), mask=image.split()[3])
                    top = list(data[f"top_{_type[1]}_{_type[2]}"])
                    current_y = 301
                    for i in range(10):
                        draw.rounded_rectangle(
                            (50, current_y, 935, current_y + 58), radius=15, fill=(32, 34, 37)
                        )
                        draw.rounded_rectangle(
                            (50, current_y, 580, current_y + 58), radius=15, fill=(24, 26, 27)
                        )
                        if len(top) >= i + 1:
                            align_text_center(
                                (50, current_y, 580, current_y + 58),
                                text=(
                                    self.get_member_display(_object.get_member(top[i]))
                                    if _type[2] == "members"
                                    else self.remove_unprintable_characters(
                                        _object.get_channel(top[i]).name
                                    )
                                ),
                                fill=(255, 255, 255),
                                font=self.bold_font[36],
                            )
                            align_text_center(
                                (580, current_y, 935, current_y + 58),
                                text=f"{self.number_to_text_with_suffix(data[f'top_{_type[1]}_{_type[2]}'][top[i]])} {'message' if _type[1] == 'messages' else 'hour'}{'' if 0 < data[f'top_{_type[1]}_{_type[2]}'][top[i]] <= 1 else 's'}",
                                fill=(255, 255, 255),
                                font=self.font[36],
                            )
                        current_y += 58 + 10

                    # Graphic. box = 925 / empty = 30 | 1 case / box = 76 / empty = 16
                    draw.rounded_rectangle((985, 204, 1910, 996), radius=15, fill=(47, 49, 54))
                    align_text_center(
                        (1005, 214, 1005, 284),
                        text=_("Graphic"),
                        fill=(255, 255, 255),
                        font=self.bold_font[40],
                    )
                    image = Image.open(self.icons["query_stats"])
                    image = image.resize((70, 70))
                    img.paste(image, (1820, 214, 1890, 284), mask=image.split()[3])
                    draw.rounded_rectangle((1005, 301, 1890, 976), radius=15, fill=(32, 34, 37))
                    image: Image.Image = graphic
                    image = image.resize((885, 675))
                    img.paste(image, (1005, 301, 1890, 976))
                elif _type[0] == "activity":
                    # Top Members. box = 925 / empty = 30 | 30 cases / box = 76 / empty = 16
                    draw.rounded_rectangle((30, 204, 955, 996), radius=15, fill=(47, 49, 54))
                    align_text_center(
                        (50, 214, 50, 284),
                        text=_("Top Members"),
                        fill=(255, 255, 255),
                        font=self.bold_font[40],
                    )
                    image = Image.open(self.icons["person"])
                    image = image.resize((70, 70))
                    img.paste(image, (865, 214, 935, 284), mask=image.split()[3])
                    top = list(data["top_members"])
                    current_y = 301
                    for i in range(10):
                        draw.rounded_rectangle(
                            (50, current_y, 935, current_y + 58), radius=15, fill=(32, 34, 37)
                        )
                        draw.rounded_rectangle(
                            (50, current_y, 580, current_y + 58), radius=15, fill=(24, 26, 27)
                        )
                        if len(top) >= i + 1:
                            align_text_center(
                                (50, current_y, 580, current_y + 58),
                                text=self.get_member_display(_object.get_member(top[i])),
                                fill=(255, 255, 255),
                                font=self.bold_font[36],
                            )
                            align_text_center(
                                (580, current_y, 935, current_y + 58),
                                text=f"{self.number_to_text_with_suffix(data['top_members'][top[i]])} hour{'' if 0 < data['top_members'][top[i]] <= 1 else 's'}",
                                fill=(255, 255, 255),
                                font=self.font[36],
                            )
                        current_y += 58 + 10

                    # Graphic. box = 925 / empty = 30 | 1 case / box = 76 / empty = 16
                    draw.rounded_rectangle((985, 204, 1910, 996), radius=15, fill=(47, 49, 54))
                    align_text_center(
                        (1005, 214, 1005, 284),
                        text=_("Graphic"),
                        fill=(255, 255, 255),
                        font=self.bold_font[40],
                    )
                    image = Image.open(self.icons["query_stats"])
                    image = image.resize((70, 70))
                    img.paste(image, (1820, 214, 1890, 284), mask=image.split()[3])
                    draw.rounded_rectangle((1005, 301, 1890, 976), radius=15, fill=(32, 34, 37))
                    image: Image.Image = graphic
                    image = image.resize((885, 675))
                    img.paste(image, (1005, 301, 1890, 976))

            if show_graphic:
                # Graphic. box = 940 / empty = 0 | + 411 (381 + 30) / 1 case / box = 264 / empty = 0
                draw.rounded_rectangle((30, 1026, 1910, 1407 + 200), radius=15, fill=(47, 49, 54))
                align_text_center(
                    (50, 1036, 50, 1106),
                    text=_("Graphic"),
                    fill=(255, 255, 255),
                    font=self.bold_font[40],
                )
                image = Image.open(self.icons["query_stats"])
                image = image.resize((70, 70))
                img.paste(image, (1830, 1036, 1900, 1106), mask=image.split()[3])
                draw.rounded_rectangle((50, 1123, 1890, 1387 + 200), radius=15, fill=(32, 34, 37))
                image: Image.Image = graphic
                image = image.resize((1840, 464))
                img.paste(image, (50, 1123, 1890, 1387 + 200))

        elif isinstance(_object, discord.CategoryChannel):
            # Server Lookback. box = 606 / empty = 30 | 2 cases / box = 117 / empty = 30
            draw.rounded_rectangle((30, 204, 636, 585), radius=15, fill=(47, 49, 54))
            align_text_center(
                (50, 214, 50, 284),
                text=_("Server Lookback"),
                fill=(255, 255, 255),
                font=self.bold_font[40],
            )
            image = Image.open(self.icons["history"])
            image = image.resize((70, 70))
            img.paste(image, (546, 214, 616, 284), mask=image.split()[3])
            draw.rounded_rectangle((50, 301, 616, 418), radius=15, fill=(32, 34, 37))
            draw.rounded_rectangle((50, 301, 325, 418), radius=15, fill=(24, 26, 27))
            align_text_center(
                (50, 301, 325, 418), text=_("Text"), fill=(255, 255, 255), font=self.bold_font[36]
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
                (50, 448, 325, 565), text=_("Voice"), fill=(255, 255, 255), font=self.bold_font[36]
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
                text=_("Messages"),
                fill=(255, 255, 255),
                font=self.bold_font[40],
            )
            image = Image.open(self.icons["#"])
            image = image.resize((70, 70))
            img.paste(image, (1184, 214, 1254, 284), mask=image.split()[3])
            draw.rounded_rectangle((688, 301, 1254, 377), radius=15, fill=(32, 34, 37))
            draw.rounded_rectangle((688, 301, 910, 377), radius=15, fill=(24, 26, 27))
            align_text_center(
                (688, 301, 910, 377), text=_("1d"), fill=(255, 255, 255), font=self.bold_font[36]
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
                (688, 395, 910, 471), text=_("7d"), fill=(255, 255, 255), font=self.bold_font[36]
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
                (688, 489, 910, 565), text=_("30d"), fill=(255, 255, 255), font=self.bold_font[36]
            )
            align_text_center(
                (910, 489, 1254, 565),
                text=f"{self.number_to_text_with_suffix(0)} messages",
                fill=(255, 255, 255),
                font=self.font[36],
            )

            # Voice Activity. box = 606 / empty = 30 | 3 cases / box = 76 / empty = 16
            draw.rounded_rectangle((1306, 204, 1912, 585), radius=15, fill=(47, 49, 54))
            align_text_center(
                (1326, 214, 1326, 284),
                text=_("Voice Activity"),
                fill=(255, 255, 255),
                font=self.bold_font[40],
            )
            image = Image.open(self.icons["sound"])
            image = image.resize((70, 70))
            img.paste(image, (1822, 214, 1892, 284), mask=image.split()[3])
            draw.rounded_rectangle((1326, 301, 1892, 377), radius=15, fill=(32, 34, 37))
            draw.rounded_rectangle((1326, 301, 1548, 377), radius=15, fill=(24, 26, 27))
            align_text_center(
                (1326, 301, 1548, 377), text=_("1d"), fill=(255, 255, 255), font=self.bold_font[36]
            )
            align_text_center(
                (1548, 301, 1892, 377),
                text=f"{self.number_to_text_with_suffix(data['voice_activity'][1])} hour{'' if 0 < data['voice_activity'][1] <= 1 else 's'}",
                fill=(255, 255, 255),
                font=self.font[36],
            )
            draw.rounded_rectangle((1326, 395, 1892, 471), radius=15, fill=(32, 34, 37))
            draw.rounded_rectangle((1326, 395, 1548, 471), radius=15, fill=(24, 26, 27))
            align_text_center(
                (1326, 395, 1548, 471), text=_("7d"), fill=(255, 255, 255), font=self.bold_font[36]
            )
            align_text_center(
                (1548, 395, 1892, 471),
                text=f"{self.number_to_text_with_suffix(data['voice_activity'][7])} hour{'' if 0 < data['voice_activity'][7] <= 1 else 's'}",
                fill=(255, 255, 255),
                font=self.font[36],
            )
            draw.rounded_rectangle((1326, 489, 1892, 565), radius=15, fill=(32, 34, 37))
            draw.rounded_rectangle((1326, 489, 1548, 565), radius=15, fill=(24, 26, 27))
            align_text_center(
                (1326, 489, 1548, 565),
                text=_("30d"),
                fill=(255, 255, 255),
                font=self.bold_font[36],
            )
            align_text_center(
                (1548, 489, 1892, 565),
                text=f"{self.number_to_text_with_suffix(data['voice_activity'][30])} hour{'' if 0 < data['voice_activity'][30] <= 1 else 's'}",
                fill=(255, 255, 255),
                font=self.font[36],
            )

            # Top Members. box = 925 / empty = 30 | 3 cases / box = 117 / empty = 30
            draw.rounded_rectangle((30, 615, 955, 996), radius=15, fill=(47, 49, 54))
            align_text_center(
                (50, 625, 50, 695),
                text=_("Top Members"),
                fill=(255, 255, 255),
                font=self.bold_font[40],
            )
            image = Image.open(self.icons["person"])
            image = image.resize((70, 70))
            img.paste(image, (865, 625, 935, 695), mask=image.split()[3])
            image = Image.open(self.icons["#"])
            image = image.resize((70, 70))
            img.paste(image, (50, 735, 120, 805), mask=image.split()[3])
            draw.rounded_rectangle((150, 712, 935, 829), radius=15, fill=(32, 34, 37))
            draw.rounded_rectangle((150, 712, 600, 829), radius=15, fill=(24, 26, 27))
            if (
                data["top_members"]["text"]["member"] is not None
                and data["top_members"]["text"]["value"] is not None
            ):
                align_text_center(
                    (150, 712, 600, 829),
                    text=self.get_member_display(
                        _object.guild.get_member(data["top_members"]["text"]["member"])
                    ),
                    fill=(255, 255, 255),
                    font=self.bold_font[36],
                )
                align_text_center(
                    (600, 712, 935, 829),
                    text=f"{self.number_to_text_with_suffix(data['top_members']['text']['value'])} message{'' if 0 < data['top_members']['text']['value'] <= 1 else 's'}",
                    fill=(255, 255, 255),
                    font=self.font[36],
                )
            image = Image.open(self.icons["sound"])
            image = image.resize((70, 70))
            img.paste(image, (50, 882, 120, 952), mask=image.split()[3])
            draw.rounded_rectangle((150, 859, 935, 976), radius=15, fill=(32, 34, 37))
            draw.rounded_rectangle((150, 859, 600, 976), radius=15, fill=(24, 26, 27))
            if (
                data["top_members"]["voice"]["member"] is not None
                and data["top_members"]["voice"]["value"] is not None
            ):
                align_text_center(
                    (150, 859, 600, 976),
                    text=self.get_member_display(
                        _object.guild.get_member(data["top_members"]["voice"]["member"])
                    ),
                    fill=(255, 255, 255),
                    font=self.bold_font[36],
                )
                align_text_center(
                    (600, 859, 935, 976),
                    text=f"{self.number_to_text_with_suffix(data['top_members']['voice']['value'])} hour{'' if 0 < data['top_members']['voice']['value'] <= 1 else 's'}",
                    fill=(255, 255, 255),
                    font=self.font[36],
                )

            # Top Channels. box = 925 / empty = 30 | 3 cases / box = 76 / empty = 16
            draw.rounded_rectangle((985, 615, 1910, 996), radius=15, fill=(47, 49, 54))
            align_text_center(
                (1005, 625, 1005, 695),
                text=_("Top Channels"),
                fill=(255, 255, 255),
                font=self.bold_font[40],
            )
            image = Image.open(self.icons["#"])
            image = image.resize((70, 70))
            img.paste(image, (1820, 625, 1890, 695), mask=image.split()[3])
            image = Image.open(self.icons["#"])
            image = image.resize((70, 70))
            img.paste(image, (1005, 735, 1075, 805), mask=image.split()[3])
            draw.rounded_rectangle((1105, 712, 1890, 829), radius=15, fill=(32, 34, 37))
            draw.rounded_rectangle((1105, 712, 1555, 829), radius=15, fill=(24, 26, 27))
            if (
                data["top_channels"]["text"]["channel"] is not None
                and data["top_channels"]["text"]["value"] is not None
            ):
                align_text_center(
                    (1105, 712, 1555, 829),
                    text=self.remove_unprintable_characters(
                        _object.guild.get_channel(data["top_channels"]["text"]["channel"]).name
                    ),
                    fill=(255, 255, 255),
                    font=self.bold_font[36],
                )
                align_text_center(
                    (1555, 712, 1890, 829),
                    text=f"{self.number_to_text_with_suffix(data['top_channels']['text']['value'])} message{'' if 0 < data['top_channels']['text']['value'] <= 1 else 's'}",
                    fill=(255, 255, 255),
                    font=self.font[36],
                )
            image = Image.open(self.icons["sound"])
            image = image.resize((70, 70))
            img.paste(image, (1005, 882, 1075, 952), mask=image.split()[3])
            draw.rounded_rectangle((1105, 859, 1890, 976), radius=15, fill=(32, 34, 37))
            draw.rounded_rectangle((1105, 859, 1555, 976), radius=15, fill=(24, 26, 27))
            if (
                data["top_channels"]["voice"]["channel"] is not None
                and data["top_channels"]["voice"]["value"] is not None
            ):
                align_text_center(
                    (1105, 859, 1555, 976),
                    text=self.remove_unprintable_characters(
                        _object.guild.get_channel(data["top_channels"]["voice"]["channel"]).name
                    ),
                    fill=(255, 255, 255),
                    font=self.bold_font[36],
                )
                align_text_center(
                    (1555, 859, 1890, 976),
                    text=f"{self.number_to_text_with_suffix(data['top_channels']['voice']['value'])} hour{'' if 0 < data['top_channels']['voice']['value'] <= 1 else 's'}",
                    fill=(255, 255, 255),
                    font=self.font[36],
                )

        elif isinstance(_object, discord.TextChannel):
            # Server Lookback. box = 606 / empty = 30 | 1 case / box = 264 / empty = 0
            draw.rounded_rectangle((30, 204, 636, 585), radius=15, fill=(47, 49, 54))
            align_text_center(
                (50, 214, 50, 284),
                text=_("Server Lookback"),
                fill=(255, 255, 255),
                font=self.bold_font[40],
            )
            image = Image.open(self.icons["history"])
            image = image.resize((70, 70))
            img.paste(image, (546, 214, 616, 284), mask=image.split()[3])
            draw.rounded_rectangle((50, 301, 616, 565), radius=15, fill=(32, 34, 37))
            align_text_center(
                (50, 351, 616, 433),
                text=f"{self.number_to_text_with_suffix(0)}",
                fill=(255, 255, 255),
                font=self.bold_font[60],
            )
            align_text_center(
                (50, 433, 616, 515),
                text=f"messages",
                fill=(255, 255, 255),
                font=self.bold_font[60],
            )

            # Messages. box = 606 / empty = 30 | 3 cases / box = 76 / empty = 16
            draw.rounded_rectangle((668, 204, 1274, 585), radius=15, fill=(47, 49, 54))
            align_text_center(
                (688, 214, 688, 284),
                text=_("Messages"),
                fill=(255, 255, 255),
                font=self.bold_font[40],
            )
            image = Image.open(self.icons["#"])
            image = image.resize((70, 70))
            img.paste(image, (1184, 214, 1254, 284), mask=image.split()[3])
            draw.rounded_rectangle((688, 301, 1254, 377), radius=15, fill=(32, 34, 37))
            draw.rounded_rectangle((688, 301, 910, 377), radius=15, fill=(24, 26, 27))
            align_text_center(
                (688, 301, 910, 377), text=_("1d"), fill=(255, 255, 255), font=self.bold_font[36]
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
                (688, 395, 910, 471), text=_("7d"), fill=(255, 255, 255), font=self.bold_font[36]
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
                (688, 489, 910, 565), text=_("30d"), fill=(255, 255, 255), font=self.bold_font[36]
            )
            align_text_center(
                (910, 489, 1254, 565),
                text=f"{self.number_to_text_with_suffix(0)} messages",
                fill=(255, 255, 255),
                font=self.font[36],
            )

            # Contributors. box = 606 / empty = 30 | 3 cases / box = 76 / empty = 16
            draw.rounded_rectangle((1306, 204, 1912, 585), radius=15, fill=(47, 49, 54))
            align_text_center(
                (1326, 214, 1326, 284),
                text=_("Contributors"),
                fill=(255, 255, 255),
                font=self.bold_font[40],
            )
            image = Image.open(self.icons["person"])
            image = image.resize((70, 70))
            img.paste(image, (1822, 214, 1892, 284), mask=image.split()[3])
            draw.rounded_rectangle((1326, 301, 1892, 377), radius=15, fill=(32, 34, 37))
            draw.rounded_rectangle((1326, 301, 1548, 377), radius=15, fill=(24, 26, 27))
            align_text_center(
                (1326, 301, 1548, 377), text=_("1d"), fill=(255, 255, 255), font=self.bold_font[36]
            )
            align_text_center(
                (1548, 301, 1892, 377),
                text=f"{self.number_to_text_with_suffix(data['contributors'][1])} members",
                fill=(255, 255, 255),
                font=self.font[36],
            )
            draw.rounded_rectangle((1326, 395, 1892, 471), radius=15, fill=(32, 34, 37))
            draw.rounded_rectangle((1326, 395, 1548, 471), radius=15, fill=(24, 26, 27))
            align_text_center(
                (1326, 395, 1548, 471), text=_("7d"), fill=(255, 255, 255), font=self.bold_font[36]
            )
            align_text_center(
                (1548, 395, 1892, 471),
                text=f"{self.number_to_text_with_suffix(data['contributors'][7])} members",
                fill=(255, 255, 255),
                font=self.font[36],
            )
            draw.rounded_rectangle((1326, 489, 1892, 565), radius=15, fill=(32, 34, 37))
            draw.rounded_rectangle((1326, 489, 1548, 565), radius=15, fill=(24, 26, 27))
            align_text_center(
                (1326, 489, 1548, 565),
                text=_("30d"),
                fill=(255, 255, 255),
                font=self.bold_font[36],
            )
            align_text_center(
                (1548, 489, 1892, 565),
                text=f"{self.number_to_text_with_suffix(data['contributors'][30])} members",
                fill=(255, 255, 255),
                font=self.font[36],
            )

            # Server Rank. box = 606 / empty = 30 | 1 case / box = 264 / empty = 0
            draw.rounded_rectangle((30, 615, 636, 996), radius=15, fill=(47, 49, 54))
            align_text_center(
                (50, 625, 50, 695),
                text=_("Server Rank"),
                fill=(255, 255, 255),
                font=self.bold_font[40],
            )
            image = Image.open(self.icons["trophy"])
            image = image.resize((70, 70))
            img.paste(image, (546, 625, 616, 695), mask=image.split()[3])
            draw.rounded_rectangle((50, 712, 616, 976), radius=15, fill=(32, 34, 37))
            align_text_center(
                (50, 712, 616, 976),
                text=f"#{data['server_rank']}" if data["server_rank"] is not None else "No data.",
                fill=(255, 255, 255),
                font=self.bold_font[60],
            )

            # Top Messages Members. box = 925 / empty = 30 | 3 cases / box = 76 / empty = 16
            draw.rounded_rectangle((668, 615, 1593, 996), radius=15, fill=(47, 49, 54))
            align_text_center(
                (688, 625, 688, 695),
                text=_("Top Messages Members"),
                fill=(255, 255, 255),
                font=self.bold_font[40],
            )
            image = Image.open(self.icons["#"])
            image = image.resize((70, 70))
            img.paste(image, (1503, 625, 1573, 695), mask=image.split()[3])
            data["top_messages_members"] = list(data["top_messages_members"].items())
            draw.rounded_rectangle((688, 712, 1573, 788), radius=15, fill=(32, 34, 37))
            draw.rounded_rectangle((688, 712, 1218, 788), radius=15, fill=(24, 26, 27))
            if len(data["top_messages_members"]) >= 1:
                align_text_center(
                    (688, 712, 1218, 788),
                    text=self.get_member_display(
                        _object.guild.get_member(data["top_messages_members"][0][0])
                    ),
                    fill=(255, 255, 255),
                    font=self.bold_font[36],
                )
                align_text_center(
                    (1218, 712, 1573, 788),
                    text=f"{self.number_to_text_with_suffix(data['top_messages_members'][0][1])} messages",
                    fill=(255, 255, 255),
                    font=self.font[36],
                )
            draw.rounded_rectangle((688, 804, 1573, 880), radius=15, fill=(32, 34, 37))
            draw.rounded_rectangle((688, 804, 1218, 880), radius=15, fill=(24, 26, 27))
            if len(data["top_messages_members"]) >= 2:
                align_text_center(
                    (688, 804, 1218, 880),
                    text=self.get_member_display(
                        _object.guild.get_member(data["top_messages_members"][1][0])
                    ),
                    fill=(255, 255, 255),
                    font=self.bold_font[36],
                )
                align_text_center(
                    (1218, 804, 1573, 880),
                    text=f"{self.number_to_text_with_suffix(data['top_messages_members'][1][1])} messages",
                    fill=(255, 255, 255),
                    font=self.font[36],
                )
            draw.rounded_rectangle((688, 896, 1573, 972), radius=15, fill=(32, 34, 37))
            draw.rounded_rectangle((688, 896, 1218, 972), radius=15, fill=(24, 26, 27))
            if len(data["top_messages_members"]) >= 3:
                align_text_center(
                    (688, 896, 1218, 972),
                    text=self.get_member_display(
                        _object.guild.get_member(data["top_messages_members"][2][0])
                    ),
                    fill=(255, 255, 255),
                    font=self.bold_font[36],
                )
                align_text_center(
                    (1218, 896, 1573, 972),
                    text=f"{self.number_to_text_with_suffix(data['top_messages_members'][2][1])} messages",
                    fill=(255, 255, 255),
                    font=self.font[36],
                )

            if show_graphic:
                # Graphic. box = 940 / empty = 0 | + 411 (381 + 30) / 1 case / box = 264 / empty = 0
                draw.rounded_rectangle((30, 1026, 1910, 1407 + 200), radius=15, fill=(47, 49, 54))
                align_text_center(
                    (50, 1036, 50, 1106),
                    text=_("Graphic"),
                    fill=(255, 255, 255),
                    font=self.bold_font[40],
                )
                image = Image.open(self.icons["query_stats"])
                image = image.resize((70, 70))
                img.paste(image, (1830, 1036, 1900, 1106), mask=image.split()[3])
                draw.rounded_rectangle((50, 1123, 1890, 1387 + 200), radius=15, fill=(32, 34, 37))
                image: Image.Image = graphic
                image = image.resize((1840, 464))
                img.paste(image, (50, 1123, 1890, 1387 + 200))

        elif isinstance(_object, discord.VoiceChannel):
            # Server Lookback. box = 606 / empty = 30 | 1 case / box = 264 / empty = 0
            draw.rounded_rectangle((30, 204, 636, 585), radius=15, fill=(47, 49, 54))
            align_text_center(
                (50, 214, 50, 284),
                text=_("Server Lookback"),
                fill=(255, 255, 255),
                font=self.bold_font[40],
            )
            image = Image.open(self.icons["history"])
            image = image.resize((70, 70))
            img.paste(image, (546, 214, 616, 284), mask=image.split()[3])
            draw.rounded_rectangle((50, 301, 616, 565), radius=15, fill=(32, 34, 37))
            align_text_center(
                (50, 351, 616, 433),
                text=f"{self.number_to_text_with_suffix(0)}",
                fill=(255, 255, 255),
                font=self.bold_font[60],
            )
            align_text_center(
                (50, 433, 616, 515),
                text=f"hours",
                fill=(255, 255, 255),
                font=self.bold_font[60],
            )

            # Voice Activity. box = 606 / empty = 30 | 3 cases / box = 76 / empty = 16
            draw.rounded_rectangle((668, 204, 1274, 585), radius=15, fill=(47, 49, 54))
            align_text_center(
                (688, 214, 688, 284),
                text=_("Voice Activity"),
                fill=(255, 255, 255),
                font=self.bold_font[40],
            )
            image = Image.open(self.icons["sound"])
            image = image.resize((70, 70))
            img.paste(image, (1184, 214, 1254, 284), mask=image.split()[3])
            draw.rounded_rectangle((688, 301, 1254, 377), radius=15, fill=(32, 34, 37))
            draw.rounded_rectangle((688, 301, 910, 377), radius=15, fill=(24, 26, 27))
            align_text_center(
                (688, 301, 910, 377), text=_("1d"), fill=(255, 255, 255), font=self.bold_font[36]
            )
            align_text_center(
                (910, 301, 1254, 377),
                text=f"{self.number_to_text_with_suffix(data['voice_activity'][1])} hours",
                fill=(255, 255, 255),
                font=self.font[36],
            )
            draw.rounded_rectangle((688, 395, 1254, 471), radius=15, fill=(32, 34, 37))
            draw.rounded_rectangle((688, 395, 910, 471), radius=15, fill=(24, 26, 27))
            align_text_center(
                (688, 395, 910, 471), text=_("7d"), fill=(255, 255, 255), font=self.bold_font[36]
            )
            align_text_center(
                (910, 395, 1254, 471),
                text=f"{self.number_to_text_with_suffix(data['voice_activity'][7])} hours",
                fill=(255, 255, 255),
                font=self.font[36],
            )
            draw.rounded_rectangle((688, 489, 1254, 565), radius=15, fill=(32, 34, 37))
            draw.rounded_rectangle((688, 489, 910, 565), radius=15, fill=(24, 26, 27))
            align_text_center(
                (688, 489, 910, 565), text=_("30d"), fill=(255, 255, 255), font=self.bold_font[36]
            )
            align_text_center(
                (910, 489, 1254, 565),
                text=f"{self.number_to_text_with_suffix(data['voice_activity'][30])} hours",
                fill=(255, 255, 255),
                font=self.font[36],
            )

            # Contributors. box = 606 / empty = 30 | 3 cases / box = 76 / empty = 16
            draw.rounded_rectangle((1306, 204, 1912, 585), radius=15, fill=(47, 49, 54))
            align_text_center(
                (1326, 214, 1326, 284),
                text=_("Contributors"),
                fill=(255, 255, 255),
                font=self.bold_font[40],
            )
            image = Image.open(self.icons["person"])
            image = image.resize((70, 70))
            img.paste(image, (1822, 214, 1892, 284), mask=image.split()[3])
            draw.rounded_rectangle((1326, 301, 1892, 377), radius=15, fill=(32, 34, 37))
            draw.rounded_rectangle((1326, 301, 1548, 377), radius=15, fill=(24, 26, 27))
            align_text_center(
                (1326, 301, 1548, 377), text=_("1d"), fill=(255, 255, 255), font=self.bold_font[36]
            )
            align_text_center(
                (1548, 301, 1892, 377),
                text=f"{self.number_to_text_with_suffix(data['contributors'][1])} members",
                fill=(255, 255, 255),
                font=self.font[36],
            )
            draw.rounded_rectangle((1326, 395, 1892, 471), radius=15, fill=(32, 34, 37))
            draw.rounded_rectangle((1326, 395, 1548, 471), radius=15, fill=(24, 26, 27))
            align_text_center(
                (1326, 395, 1548, 471), text=_("7d"), fill=(255, 255, 255), font=self.bold_font[36]
            )
            align_text_center(
                (1548, 395, 1892, 471),
                text=f"{self.number_to_text_with_suffix(data['contributors'][7])} members",
                fill=(255, 255, 255),
                font=self.font[36],
            )
            draw.rounded_rectangle((1326, 489, 1892, 565), radius=15, fill=(32, 34, 37))
            draw.rounded_rectangle((1326, 489, 1548, 565), radius=15, fill=(24, 26, 27))
            align_text_center(
                (1326, 489, 1548, 565),
                text=_("30d"),
                fill=(255, 255, 255),
                font=self.bold_font[36],
            )
            align_text_center(
                (1548, 489, 1892, 565),
                text=f"{self.number_to_text_with_suffix(data['contributors'][30])} members",
                fill=(255, 255, 255),
                font=self.font[36],
            )

            # Server Rank. box = 606 / empty = 30 | 1 case / box = 264 / empty = 0
            draw.rounded_rectangle((30, 615, 636, 996), radius=15, fill=(47, 49, 54))
            align_text_center(
                (50, 625, 50, 695),
                text=_("Server Rank"),
                fill=(255, 255, 255),
                font=self.bold_font[40],
            )
            image = Image.open(self.icons["trophy"])
            image = image.resize((70, 70))
            img.paste(image, (546, 625, 616, 695), mask=image.split()[3])
            draw.rounded_rectangle((50, 712, 616, 976), radius=15, fill=(32, 34, 37))
            align_text_center(
                (50, 712, 616, 976),
                text=f"#{data['server_rank']}" if data["server_rank"] is not None else "No data.",
                fill=(255, 255, 255),
                font=self.bold_font[60],
            )

            # Top Voice Members. box = 925 / empty = 30 | 3 cases / box = 76 / empty = 16
            draw.rounded_rectangle((668, 615, 1593, 996), radius=15, fill=(47, 49, 54))
            align_text_center(
                (688, 625, 688, 695),
                text=_("Top Voice Members"),
                fill=(255, 255, 255),
                font=self.bold_font[40],
            )
            image = Image.open(self.icons["sound"])
            image = image.resize((70, 70))
            img.paste(image, (1503, 625, 1573, 695), mask=image.split()[3])
            data["top_voice_members"] = list(data["top_voice_members"].items())
            draw.rounded_rectangle((688, 712, 1573, 788), radius=15, fill=(32, 34, 37))
            draw.rounded_rectangle((688, 712, 1218, 788), radius=15, fill=(24, 26, 27))
            if len(data["top_voice_members"]) >= 1:
                align_text_center(
                    (688, 712, 1218, 788),
                    text=self.get_member_display(
                        _object.guild.get_member(data["top_voice_members"][0][0])
                    ),
                    fill=(255, 255, 255),
                    font=self.bold_font[36],
                )
                align_text_center(
                    (1218, 712, 1573, 788),
                    text=f"{self.number_to_text_with_suffix(data['top_voice_members'][0][1])} hours",
                    fill=(255, 255, 255),
                    font=self.font[36],
                )
            draw.rounded_rectangle((688, 804, 1573, 880), radius=15, fill=(32, 34, 37))
            draw.rounded_rectangle((688, 804, 1218, 880), radius=15, fill=(24, 26, 27))
            if len(data["top_voice_members"]) >= 2:
                align_text_center(
                    (688, 804, 1218, 880),
                    text=self.get_member_display(
                        _object.guild.get_member(data["top_voice_members"][1][0])
                    ),
                    fill=(255, 255, 255),
                    font=self.bold_font[36],
                )
                align_text_center(
                    (1218, 804, 1573, 880),
                    text=f"{self.number_to_text_with_suffix(data['top_voice_members'][1][1])} hours",
                    fill=(255, 255, 255),
                    font=self.font[36],
                )
            draw.rounded_rectangle((688, 896, 1573, 972), radius=15, fill=(32, 34, 37))
            draw.rounded_rectangle((688, 896, 1218, 972), radius=15, fill=(24, 26, 27))
            if len(data["top_voice_members"]) >= 3:
                align_text_center(
                    (688, 896, 1218, 972),
                    text=self.get_member_display(
                        _object.guild.get_member(data["top_voice_members"][2][0])
                    ),
                    fill=(255, 255, 255),
                    font=self.bold_font[36],
                )
                align_text_center(
                    (1218, 896, 1573, 972),
                    text=f"{self.number_to_text_with_suffix(data['top_voice_members'][2][1])} hour{'' if 0 < data['top_voice_members'][2][1] <= 1 else 's'}",
                    fill=(255, 255, 255),
                    font=self.font[36],
                )

            if show_graphic:
                # Graphic. box = 940 / empty = 0 | + 411 (381 + 30) / 1 case / box = 264 / empty = 0
                draw.rounded_rectangle((30, 1026, 1910, 1407 + 200), radius=15, fill=(47, 49, 54))
                align_text_center(
                    (50, 1036, 50, 1106),
                    text=_("Graphic"),
                    fill=(255, 255, 255),
                    font=self.bold_font[40],
                )
                image = Image.open(self.icons["query_stats"])
                image = image.resize((70, 70))
                img.paste(image, (1830, 1036, 1900, 1106), mask=image.split()[3])
                draw.rounded_rectangle((50, 1123, 1890, 1387 + 200), radius=15, fill=(32, 34, 37))
                image: Image.Image = graphic
                image = image.resize((1840, 464))
                img.paste(image, (50, 1123, 1890, 1387 + 200))

        utc_now = datetime.datetime.now(tz=datetime.timezone.utc)
        tracking_data_start_time = 0
        if show_graphic:
            image = Image.open(self.icons["history"])
            image = image.resize((50, 50))
            img.paste(image, (30, 1427 + 200, 80, 1477 + 200), mask=image.split()[3])
            align_text_center(
                (90, 1427 + 200, 90, 1477 + 200),
                text=_("Tracking data in this server for {interval_string}.").format(
                    interval_string=CogsUtils.get_interval_string(
                        tracking_data_start_time, utc_now=utc_now
                    )
                ),
                fill=(255, 255, 255),
                font=self.bold_font[30],
            )
            if members_type != "both":
                members_type_text = _("Only {members_type} are taken into account.").format(
                    members_type=members_type
                )
                image = Image.open(self.icons["person"])
                image = image.resize((50, 50))
                img.paste(
                    image,
                    (
                        1942 - 30 - self.bold_font[30].getbbox(members_type_text)[2] - 10 - 50,
                        1427 + 200,
                        1942 - 30 - self.bold_font[30].getbbox(members_type_text)[2] - 10,
                        1477 + 200,
                    ),
                    mask=image.split()[3],
                )
                align_text_center(
                    (
                        1942 - 30 - self.bold_font[30].getbbox(members_type_text)[2],
                        1427 + 200,
                        1942 - 30 - self.bold_font[30].getbbox(members_type_text)[2],
                        1477 + 200,
                    ),
                    text=members_type_text,
                    fill=(255, 255, 255),
                    font=self.bold_font[30],
                )
        else:
            image = Image.open(self.icons["history"])
            image = image.resize((50, 50))
            img.paste(image, (30, 1016, 80, 1066), mask=image.split()[3])
            align_text_center(
                (90, 1016, 90, 1066),
                text=_("Tracking data in this server for {interval_string}.").format(
                    interval_string=CogsUtils.get_interval_string(
                        tracking_data_start_time, utc_now=utc_now
                    )
                ),
                fill=(255, 255, 255),
                font=self.bold_font[30],
            )
            if members_type != "both":
                members_type_text = _("Only {members_type} are taken into account.").format(
                    members_type=members_type
                )
                image = Image.open(self.icons["person"])
                image = image.resize((50, 50))
                img.paste(
                    image,
                    (
                        1942 - 30 - self.bold_font[30].getbbox(members_type_text)[2] - 10 - 50,
                        1016,
                        1942 - 30 - self.bold_font[30].getbbox(members_type_text)[2] - 10,
                        1066,
                    ),
                    mask=image.split()[3],
                )
                align_text_center(
                    (
                        1942 - 30 - self.bold_font[30].getbbox(members_type_text)[2],
                        1016,
                        1942 - 30 - self.bold_font[30].getbbox(members_type_text)[2],
                        1066,
                    ),
                    text=members_type_text,
                    fill=(255, 255, 255),
                    font=self.bold_font[30],
                )

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
        """Generate images with messages and voice stats, for members, roles, guilds, categories, text channels, voice channels and activities."""
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

    @guildstats.command()
    async def role(
        self,
        ctx: commands.Context,
        show_graphic: typing.Optional[bool] = False,
        *,
        role: discord.Role = None,
    ) -> None:
        """Display stats for a specified role."""
        if role is None:
            role = ctx.author.top_role
        await GuildStatsView(
            cog=self,
            _object=role,
            members_type="both",
            show_graphic_in_main=show_graphic,
            graphic_mode=False,
        ).start(ctx)

    @guildstats.command(aliases=["server"])
    async def guild(
        self,
        ctx: commands.Context,
        members_type: typing.Optional[typing.Literal["humans", "bots", "both"]] = "humans",
        show_graphic: typing.Optional[bool] = False,
    ) -> None:
        """Display stats for this guild."""
        await GuildStatsView(
            cog=self,
            _object=ctx.guild,
            members_type=members_type,
            show_graphic_in_main=show_graphic,
            graphic_mode=False,
        ).start(ctx)

    @guildstats.command()
    async def messages(
        self,
        ctx: commands.Context,
        members_type: typing.Optional[typing.Literal["humans", "bots", "both"]] = "humans",
        show_graphic: typing.Optional[bool] = False,
    ) -> None:
        """Display stats for the messages in this guild."""
        await GuildStatsView(
            cog=self,
            _object=(ctx.guild, "messages"),
            members_type=members_type,
            show_graphic_in_main=show_graphic,
            graphic_mode=False,
        ).start(ctx)

    @guildstats.command()
    async def voice(
        self,
        ctx: commands.Context,
        members_type: typing.Optional[typing.Literal["humans", "bots", "both"]] = "humans",
        show_graphic: typing.Optional[bool] = False,
    ) -> None:
        """Display stats for the voice in this guild."""
        await GuildStatsView(
            cog=self,
            _object=(ctx.guild, "voice"),
            members_type=members_type,
            show_graphic_in_main=show_graphic,
            graphic_mode=False,
        ).start(ctx)

    @guildstats.command()
    async def activities(
        self,
        ctx: commands.Context,
        members_type: typing.Optional[typing.Literal["humans", "bots", "both"]] = "humans",
    ) -> None:
        """Display stats for activities in this guild."""
        await GuildStatsView(
            cog=self,
            _object=(ctx.guild, "activities"),
            members_type=members_type,
            show_graphic_in_main=False,
            graphic_mode=False,
        ).start(ctx)

    @guildstats.command()
    async def category(
        self,
        ctx: commands.Context,
        members_type: typing.Optional[typing.Literal["humans", "bots", "both"]] = "humans",
        show_graphic: typing.Optional[bool] = False,
        *,
        category: discord.CategoryChannel = None,
    ) -> None:
        """Display stats for a specified category."""
        if category is None:
            if ctx.channel.category is not None:
                category = ctx.channel.category
            else:
                raise commands.UserInputError()
        await GuildStatsView(
            cog=self,
            _object=category,
            members_type=members_type,
            show_graphic_in_main=show_graphic,
            graphic_mode=False,
        ).start(ctx)

    @guildstats.command()
    async def channel(
        self,
        ctx: commands.Context,
        members_type: typing.Optional[typing.Literal["humans", "bots", "both"]] = "humans",
        show_graphic: typing.Optional[bool] = False,
        *,
        channel: typing.Union[discord.TextChannel, discord.VoiceChannel] = commands.CurrentChannel,
    ) -> None:
        """Display stats for a specified channel."""
        if isinstance(channel, discord.Thread):
            raise commands.UserFeedbackCheckFailure(_("Threads aren't supported by this cog."))
        await GuildStatsView(
            cog=self,
            _object=channel,
            members_type=members_type,
            show_graphic_in_main=show_graphic,
            graphic_mode=False,
        ).start(ctx)

    @guildstats.command(aliases=["lb"])
    async def top(
        self,
        ctx: commands.Context,
        members_type: typing.Optional[typing.Literal["humans", "bots", "both"]] = "humans",
        _type_1: typing.Optional[typing.Literal["messages", "voice"]] = "messages",
        _type_2: typing.Optional[typing.Literal["members", "channels"]] = "members",
    ) -> None:
        """Display top stats leaderboard for voice/messages members/channels."""
        if members_type is None:
            members_type = "humans"
        await GuildStatsView(
            cog=self,
            _object=(ctx.guild, ("top", _type_1, _type_2)),
            members_type=members_type,
            show_graphic_in_main=False,
            graphic_mode=False,
        ).start(ctx)

    @guildstats.command(aliases=["wtop", "wlb"])
    async def weekly(
        self,
        ctx: commands.Context,
        members_type: typing.Optional[typing.Literal["humans", "bots", "both"]] = "humans",
        _type_1: typing.Optional[typing.Literal["messages", "voice"]] = "messages",
        _type_2: typing.Optional[typing.Literal["members", "channels"]] = "members",
    ) -> None:
        """Display weekly stats leaderboard for voice/messages members/channels."""
        if members_type is None:
            members_type = "humans"
        await GuildStatsView(
            cog=self,
            _object=(ctx.guild, ("weekly", _type_1, _type_2)),
            members_type=members_type,
            show_graphic_in_main=False,
            graphic_mode=False,
        ).start(ctx)

    @guildstats.command(aliases=["mtop", "mlb"])
    async def monthly(
        self,
        ctx: commands.Context,
        members_type: typing.Optional[typing.Literal["humans", "bots", "both"]] = "humans",
        _type_1: typing.Optional[typing.Literal["messages", "voice"]] = "messages",
        _type_2: typing.Optional[typing.Literal["members", "channels"]] = "members",
    ) -> None:
        """Display monthly stats leaderboard for voice/messages members/channels."""
        await GuildStatsView(
            cog=self,
            _object=(ctx.guild, ("monthly", _type_1, _type_2)),
            members_type=members_type,
            show_graphic_in_main=False,
            graphic_mode=False,
        ).start(ctx)

    @guildstats.command()
    async def activity(
        self,
        ctx: commands.Context,
        members_type: typing.Optional[typing.Literal["humans", "bots", "both"]] = "humans",
        *,
        activity_name: str,
    ) -> None:
        """Display stats for a specific activity in this guild."""
        await GuildStatsView(
            cog=self,
            _object=(ctx.guild, ("activity", activity_name)),
            members_type=members_type,
            show_graphic_in_main=False,
            graphic_mode=False,
        ).start(ctx)

    @guildstats.command(aliases=["mactivites", "mact"])
    async def memberactivities(
        self,
        ctx: commands.Context,
        *,
        member: discord.Member = commands.Author,
    ) -> None:
        """Display stats for the activities of a specified member."""
        await GuildStatsView(
            cog=self,
            _object=(member, "activities"),
            members_type="both",
            show_graphic_in_main=False,
            graphic_mode=False,
        ).start(ctx)

    @guildstats.command(aliases=["graph"])
    async def graphic(
        self,
        ctx: commands.Context,
        members_type: typing.Optional[typing.Literal["humans", "bots", "both"]] = "humans",
        *,
        _object: ObjectConverter = None,
    ) -> None:
        """Display graphic for members, roles guilds, text channels, voice channels and activities."""
        if _object is None:
            _object = ctx.guild
        await GuildStatsView(
            cog=self,
            _object=(
                _object
                if _object not in ("voice", "messages", "activities")
                else (ctx.guild, _object)
            ),
            members_type=members_type,
            show_graphic_in_main=False,
            graphic_mode=True,
        ).start(ctx)