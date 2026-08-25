from datetime import datetime, timezone
import discord
from discord.ext import tasks
import logging
from redbot.core import Config, checks, commands
from redbot.core.bot import Red

from .statbot_api import StatbotClient, format_category_name

log = logging.getLogger("red.szg_statbot")


class SZGStatbot(commands.Cog):
    """Beheert Statbot API integratie en live voice-gamification via categorieën."""

    def __init__(self, bot: Red) -> None:
        self.bot = bot
        self.config = Config.get_conf(self, identifier=9812471923, force_registration=True)

        default_guild = {
            "statbot_api_key": "",
            "tracked_category_id": None,
            "cached_30d_target": 10.0,
            "last_target_update_day": -1
        }
        self.config.register_guild(**default_guild)

    async def cog_load(self) -> None:
        self.hourly_voice_tracker.start()

    async def cog_unload(self) -> None:
        self.hourly_voice_tracker.cancel()

    @tasks.loop(minutes=60.0)
    async def hourly_voice_tracker(self) -> None:
        """Update elk uur de categorienaam en vernieuwt om 00:00 UTC de 30-daagse baseline."""
        for guild in self.bot.guilds:
            api_key = await self.config.guild(guild).statbot_api_key()
            category_id = await self.config.guild(guild).tracked_category_id()

            if not api_key or not category_id:
                continue

            category = guild.get_channel(category_id)
            if not isinstance(category, discord.CategoryChannel):
                continue

            client = StatbotClient(api_key=api_key, guild_id=guild.id)
            now = datetime.now(timezone.utc)

            # 1. Update de baseline om 00:00 UTC
            last_day = await self.config.guild(guild).last_target_update_day()
            target_hours = await self.config.guild(guild).cached_30d_target()

            if now.day != last_day:
                fresh_target = await client.get_30_day_daily_average_hours()
                if fresh_target > 0:
                    target_hours = fresh_target
                    await self.config.guild(guild).cached_30d_target.set(target_hours)
                await self.config.guild(guild).last_target_update_day.set(now.day)
                log.info(f"[{guild.name}] Nieuw 30-daags voice-gemiddelde vastgezet: {target_hours}u")

            # 2. Haal cumulatieve uren van vandaag op
            current_hours = await client.get_today_voice_hours()

            # 3. Categorienaam wijzigen bij verandering
            new_name = format_category_name(current_hours, target_hours)
            if category.name != new_name:
                try:
                    await category.edit(name=new_name, reason="Statbot Voice Progress Update")
                    log.info(f"[{guild.name}] Categorienaam geüpdatet naar: {new_name}")
                except discord.Forbidden:
                    log.warning(f"[{guild.name}] Geen rechten om categorienaam te wijzigen.")
                except discord.HTTPException as e:
                    log.warning(f"[{guild.name}] HTTP fout bij wijzigen van categorie: {e}")

    @hourly_voice_tracker.before_loop
    async def before_tracker(self) -> None:
        await self.bot.wait_until_ready()

    # --- COMMANDS ---

    @commands.group(name="statbotset", aliases=["sbset"])
    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    async def statbotset(self, ctx: commands.Context) -> None:
        """Beheerinstellingen voor Statbot tracking en categorie visualisatie."""
        pass

    @statbotset.command(name="apikey")
    async def set_api_key(self, ctx: commands.Context, api_key: str) -> None:
        """Stel de Statbot API-sleutel in voor deze server."""
        await self.config.guild(ctx.guild).statbot_api_key.set(api_key)
        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass
        await ctx.send("✅ Statbot API-sleutel opgeslagen.", delete_after=10)

    @statbotset.command(name="category")
    async def set_category(self, ctx: commands.Context, category: discord.CategoryChannel) -> None:
        """Koppel de spraakcategorie die de progressiebalk moet tonen."""
        await self.config.guild(ctx.guild).tracked_category_id.set(category.id)
        await ctx.send(f"✅ Voice tracking gekoppeld aan: **{category.name}** (`{category.id}`)")

    @statbotset.command(name="forcesync")
    async def force_sync(self, ctx: commands.Context) -> None:
        """Forceer direct een herberekening van baseline en live uren."""
        api_key = await self.config.guild(ctx.guild).statbot_api_key()
        category_id = await self.config.guild(ctx.guild).tracked_category_id()

        if not api_key:
            await ctx.send("❌ Geen API-sleutel gevonden. Gebruik `[p]statbotset apikey`.")
            return
        if not category_id:
            await ctx.send("❌ Geen categorie gekoppeld. Gebruik `[p]statbotset category`.")
            return

        category = ctx.guild.get_channel(category_id)
        if not isinstance(category, discord.CategoryChannel):
            await ctx.send("❌ Gekoppelde categorie is niet meer vindbaar.")
            return

        async with ctx.typing():
            client = StatbotClient(api_key=api_key, guild_id=ctx.guild.id)
            target_hours = await client.get_30_day_daily_average_hours()
            current_hours = await client.get_today_voice_hours()

            now = datetime.now(timezone.utc)
            if target_hours > 0:
                await self.config.guild(ctx.guild).cached_30d_target.set(target_hours)
            await self.config.guild(ctx.guild).last_target_update_day.set(now.day)

            new_name = format_category_name(current_hours, target_hours)
            await category.edit(name=new_name, reason="Handmatige Statbot Sync")

        await ctx.send(
            f"🔄 **Sync voltooid:**\n"
            f"• 30-daags gemiddelde: **{target_hours}u**\n"
            f"• Vandaag behaald: **{current_hours}u**\n"
            f"• Nieuwe weergave: `{new_name}`"
        )

    @statbotset.command(name="status")
    async def show_status(self, ctx: commands.Context) -> None:
        """Toont de actuele instellingen en gecachte metrics."""
        category_id = await self.config.guild(ctx.guild).tracked_category_id()
        target = await self.config.guild(ctx.guild).cached_30d_target()
        has_key = bool(await self.config.guild(ctx.guild).statbot_api_key())
        category = ctx.guild.get_channel(category_id) if category_id else None

        embed = discord.Embed(title="Statbot Tracker Status", color=discord.Color.green())
        embed.add_field(name="API Key Geconfigureerd", value="Ja" if has_key else "Nee", inline=True)
        embed.add_field(name="Gekoppelde Categorie", value=category.name if category else "Geen", inline=True)
        embed.add_field(name="Actueel Doel (30d Gemiddelde)", value=f"{target}u", inline=True)

        await ctx.send(embed=embed)