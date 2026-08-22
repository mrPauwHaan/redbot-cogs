import io
import discord
from PIL import Image, ImageDraw, ImageFont
from redbot.core.data_manager import bundled_data_path

class UserCard(commands.Cog):
    # ... existing __init__ and methods ...

    async def render_stats_card(self, member: discord.Member, stats: dict) -> io.BytesIO:
        """Renders a customized voice statistics card matching the cog theme."""
        data_dir = bundled_data_path(self)
        bg_path = data_dir / "background.png"
        font_path = data_dir / "arial.ttf"
        font_bold_path = data_dir / "arial_bold.ttf"

        # 1. Base Background
        if bg_path.exists():
            base_img = Image.open(bg_path).convert("RGBA")
        else:
            base_img = Image.new("RGBA", (1000, 500), (32, 34, 37, 255))

        draw = ImageDraw.Draw(base_img)

        # 2. Load Fonts
        try:
            title_font = ImageFont.truetype(str(font_bold_path), 36)
            header_font = ImageFont.truetype(str(font_bold_path), 24)
            body_font = ImageFont.truetype(str(font_path), 20)
            small_font = ImageFont.truetype(str(font_path), 16)
        except Exception:
            title_font = header_font = body_font = small_font = ImageFont.load_default()

        # 3. Avatar Processing (Circular Mask)
        try:
            avatar_bytes = await member.display_avatar.read()
            avatar_img = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA").resize((120, 120))
            
            mask = Image.new("L", (120, 120), 0)
            mask_draw = ImageDraw.Draw(mask)
            mask_draw.ellipse((0, 0, 120, 120), fill=255)
            
            base_img.paste(avatar_img, (50, 50), mask)
        except Exception:
            pass

        # 4. User Header Details
        draw.text((190, 60), member.display_name, fill=(255, 255, 255), font=title_font)
        draw.text((190, 110), f"Voice Activity (Last 30 Days)", fill=(180, 180, 180), font=body_font)

        # 5. Divider Line
        draw.line([(50, 190), (950, 190)], fill=(70, 75, 80), width=2)

        # 6. Total Time Metric Box
        total_hours = stats.get("total_hours", 0)
        draw.text((50, 215), "TOTAL TIME IN VOICE", fill=(114, 137, 218), font=header_font)
        draw.text((50, 255), f"{total_hours} Hours", fill=(255, 255, 255), font=title_font)

        # 7. Top Channels Breakdown
        draw.text((450, 215), "MOST ACTIVE CHANNELS", fill=(114, 137, 218), font=header_font)
        
        top_channels = stats.get("top_channels", [])
        y_offset = 260
        
        if not top_channels:
            draw.text((450, y_offset), "No voice activity logged recently.", fill=(150, 150, 150), font=body_font)
        else:
            for rank, (ch_id, duration) in enumerate(top_channels, start=1):
                channel = member.guild.get_channel(int(ch_id)) if str(ch_id).isdigit() else None
                ch_name = f"#{channel.name}" if channel else f"#deleted-channel ({ch_id})"
                ch_hours = round(duration / 3600, 1)

                # Channel line
                draw.text((450, y_offset), f"{rank}. {ch_name}", fill=(255, 255, 255), font=body_font)
                draw.text((800, y_offset), f"{ch_hours} hrs", fill=(200, 200, 200), font=body_font)
                y_offset += 35

        # 8. Footer
        draw.text((50, 440), "Powered by Statbot API", fill=(100, 100, 100), font=small_font)

        # 9. Return Bytes Buffer
        buf = io.BytesIO()
        base_img.save(buf, format="PNG")
        buf.seek(0)
        return buf