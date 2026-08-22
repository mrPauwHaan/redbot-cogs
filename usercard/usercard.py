import io
import discord
from PIL import Image, ImageDraw, ImageFont
from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.data_manager import bundled_data_path

from .view import UserCardView


class usercard(commands.Cog):
    """Genereert Lid, ID en Statistieken kaarten."""

    def __init__(self, bot: Red):
        self.bot = bot

    def _get_fonts(self):
        data_dir = bundled_data_path(self)
        font_path = data_dir / "arial.ttf"
        font_bold_path = data_dir / "arial_bold.ttf"

        try:
            title_font = ImageFont.truetype(str(font_bold_path), 32)
            header_font = ImageFont.truetype(str(font_bold_path), 24)
            body_font = ImageFont.truetype(str(font_path), 20)
            small_font = ImageFont.truetype(str(font_path), 16)
        except Exception:
            title_font = header_font = body_font = small_font = ImageFont.load_default()

        return title_font, header_font, body_font, small_font

    async def _get_base_image(self) -> Image.Image:
        bg_path = bundled_data_path(self) / "background.png"
        if bg_path.exists():
            return Image.open(bg_path).convert("RGBA")
        return Image.new("RGBA", (1000, 500), (32, 34, 37, 255))

    async def _draw_avatar(self, base_img: Image.Image, member: discord.Member, pos=(50, 50)):
        try:
            avatar_bytes = await member.display_avatar.read()
            avatar_img = (
                Image.open(io.BytesIO(avatar_bytes)).convert("RGBA").resize((120, 120))
            )

            mask = Image.new("L", (120, 120), 0)
            mask_draw = ImageDraw.Draw(mask)
            mask_draw.ellipse((0, 0, 120, 120), fill=255)

            base_img.paste(avatar_img, pos, mask)
        except Exception:
            pass

    async def render_lid_card(self, member: discord.Member) -> io.BytesIO:
        """Rendert de standaard Lid profielkaart."""
        base_img = await self._get_base_image()
        draw = ImageDraw.Draw(base_img)
        title_font, header_font, body_font, small_font = self._get_fonts()

        await self._draw_avatar(base_img, member)

        # Header Info
        draw.text((190, 60), member.display_name, fill=(255, 255, 255), font=title_font)
        draw.text(
            (190, 110),
            f"Lid sinds: {member.joined_at.strftime('%d-%m-%Y') if member.joined_at else 'Onbekend'}",
            fill=(180, 180, 180),
            font=body_font,
        )

        draw.line([(50, 190), (950, 190)], fill=(70, 75, 80), width=2)

        # Content Box
        draw.text((50, 220), "LIDMAATSCHAP STATUS", fill=(114, 137, 218), font=header_font)
        roles = [r.name for r in member.roles if r.name != "@everyone"]
        role_str = ", ".join(roles[:3]) if roles else "Geen specifieke rollen"
        draw.text((50, 260), f"Rollen: {role_str}", fill=(255, 255, 255), font=body_font)

        draw.text((50, 310), "EVENEMENTEN", fill=(114, 137, 218), font=header_font)
        draw.text((50, 350), "Bezochte events: Ingeschreven", fill=(255, 255, 255), font=body_font)

        buf = io.BytesIO()
        base_img.save(buf, format="PNG")
        buf.seek(0)
        return buf

    async def render_id_card(self, member: discord.Member) -> io.BytesIO:
        """Rendert de digitale ID kaart."""
        base_img = await self._get_base_image()
        draw = ImageDraw.Draw(base_img)
        title_font, header_font, body_font, small_font = self._get_fonts()

        await self._draw_avatar(base_img, member)

        # Header Info
        draw.text((190, 60), f"ID Kaart — {member.name}", fill=(255, 255, 255), font=title_font)
        draw.text((190, 110), f"Tag: {member.discriminator if member.discriminator != '0' else '@' + member.name}", fill=(180, 180, 180), font=body_font)

        draw.line([(50, 190), (950, 190)], fill=(70, 75, 80), width=2)

        # Identity Details
        draw.text((50, 220), "DISCORD IDENTIFICATIE", fill=(114, 137, 218), font=header_font)
        draw.text((50, 260), f"Gebruiker ID: {member.id}", fill=(255, 255, 255), font=body_font)
        draw.text(
            (50, 300),
            f"Account Aangemaakt: {member.created_at.strftime('%d-%m-%Y')}",
            fill=(255, 255, 255),
            font=body_font,
        )

        draw.text((50, 360), f"Server: {member.guild.name}", fill=(150, 150, 150), font=small_font)

        buf = io.BytesIO()
        base_img.save(buf, format="PNG")
        buf.seek(0)
        return buf

    async def render_stats_card(self, member: discord.Member, stats: dict) -> io.BytesIO:
        """Rendert de voice statistieken kaart."""
        base_img = await self._get_base_image()
        draw = ImageDraw.Draw(base_img)
        title_font, header_font, body_font, small_font = self._get_fonts()

        await self._draw_avatar(base_img, member)

        # Header Info
        draw.text((190, 60), member.display_name, fill=(255, 255, 255), font=title_font)
        draw.text((190, 110), "Voice Activiteit (Laatste 30 Dagen)", fill=(180, 180, 180), font=body_font)

        draw.line([(50, 190), (950, 190)], fill=(70, 75, 80), width=2)

        # Voice Duration Box
        total_hours = stats.get("total_hours", 0)
        draw.text((50, 220), "TOTALE TIJD IN VOICE", fill=(114, 137, 218), font=header_font)
        draw.text((50, 260), f"{total_hours} Uur", fill=(255, 255, 255), font=title_font)

        # Top Channels Box
        draw.text((450, 220), "MEEST ACTIEVE KANALEN", fill=(114, 137, 218), font=header_font)

        top_channels = stats.get("top_channels", [])
        y_offset = 265

        if not top_channels:
            draw.text(
                (450, y_offset),
                "Geen voice activiteit geregistreerd.",
                fill=(150, 150, 150),
                font=body_font,
            )
        else:
            for rank, (ch_id, duration) in enumerate(top_channels, start=1):
                channel = member.guild.get_channel(int(ch_id)) if str(ch_id).isdigit() else None
                ch_name = f"#{channel.name}" if channel else f"Kanaal ({ch_id})"
                ch_hours = round(duration / 3600, 1)

                draw.text((450, y_offset), f"{rank}. {ch_name}", fill=(255, 255, 255), font=body_font)
                draw.text((800, y_offset), f"{ch_hours} uur", fill=(200, 200, 200), font=body_font)
                y_offset += 35

        draw.text((50, 440), "Powered by Statbot API", fill=(100, 100, 100), font=small_font)

        buf = io.BytesIO()
        base_img.save(buf, format="PNG")
        buf.seek(0)
        return buf

    @commands.command(name="usercard")
    @commands.guild_only()
    async def usercard(self, ctx: commands.Context, *, member: discord.Member = None):
        """Toont de interactieve gebruikerskaart met Lid, ID en Stats weergaven."""
        member = member or ctx.author

        lid_buf = await self.render_lid_card(member)
        lid_bytes = lid_buf.getvalue()

        file = discord.File(io.BytesIO(lid_bytes), filename="lid_card.png")
        view = UserCardView(
            cog=self, member=member, author=ctx.author, initial_lid_bytes=lid_bytes
        )

        await ctx.send(file=file, view=view)