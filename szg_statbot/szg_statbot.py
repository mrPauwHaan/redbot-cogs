from datetime import datetime, timezone
import discord
from discord.ext import tasks
import logging
from redbot.core import Config, checks, commands
from redbot.core.bot import Red

from .statbot_api import StatbotClient, format_category_name

log = logging.getLogger("red.szg_statbot")


class SZGStatbot(commands.Cog):
    """Beheert live voice-gamification via Statbot v1 sums API en Discord categorieën."""

    def __init__(self, bot: Red) -> None:
        self.bot = bot
        self.config = Config.get_conf(self, identifier=9812471923, force_registration=True)

        default_guild = {
            "tracked_category_id": None,
            "cached_30d_target": 10.0,
            "last_target_update_day": -1
        }
        self.config.register_guild(**default_guild)

    async def cog_load(self) -> None:
        self.hourly_voice_tracker.start()

    async def cog_unload(self) -> None:
        self.hourly_voice_tracker.cancel()

    async def _get_api_key(self) -> str:
        """Haalt de Statbot API-sleutel op uit de gedeelde Red bot tokens."""
        tokens = await self.bot.get_shared_api_tokens("statbot")
        return tokens.get("api_key", "")

    @tasks.loop(minutes=60.0)
    async def hourly_voice_tracker(self) -> None:
        """Update ieder uur de voortgang en vernieuwt om 00:00 UTC de 30-daagse baseline."""
        api_key = await self._get_api_key()
        if not api_key:
            return

        for guild in self.bot.guilds:
            category_id = await self.config.guild(guild).tracked_category_id()
            if not category_id:
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
                log.info(f"[{guild.name}] Nieuw 30-daags gemiddelde berekend: {target_hours}u")

            # 2. Haal actuele voice-uren van vandaag op
            current_hours = await client.get_today_voice_hours()

            # 3. Categorienaam bijwerken indien gewijzigd
            new_name = format_category_name(current_hours, target_hours)
            if category.name != new_name:
                try:
                    await category.edit(name=new_name, reason="Statbot Voice Progress Tracker")
                    log.info(f"[{guild.name}] Categorie gewijzigd naar: {new_name}")
                except discord.Forbidden:
                    log.warning(f"[{guild.name}] Ontbrekende rechten om categorie te hernoemen.")
                except discord.HTTPException as e:
                    log.warning(f"[{guild.name}] HTTP fout bij wijzigen categorie: {e}")

    @hourly_voice_tracker.before_loop
    async def before_tracker(self) -> None:
        await self.bot.wait_until_ready()

    # --- COMMANDS ---

    @commands.group(name="statbotset", aliases=["sbset"])
    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    async def statbotset(self, ctx: commands.Context) -> None:
        """Beheerinstellingen voor Statbot voice progressie tracking."""
        pass

    @statbotset.command(name="category")
    async def set_category(self, ctx: commands.Context, category: discord.CategoryChannel) -> None:
        """Koppel de spraakcategorie die de progressiebalk weergeeft."""
        await self.config.guild(ctx.guild).tracked_category_id.set(category.id)
        await ctx.send(f"✅ Voice tracking gekoppeld aan categorie: **{category.name}** (`{category.id}`)")

    @statbotset.command(name="forcesync")
    async def force_sync(self, ctx: commands.Context) -> None:
        """Forceer direct een herberekening van de 30-daagse baseline en urenvoortgang."""
        api_key = await self._get_api_key()
        if not api_key:
            return await ctx.send("❌ Geen Statbot API-sleutel gevonden. Stel deze in via `[p]set api statbot api_key,<JOUW_TOKEN>`.")

        category_id = await self.config.guild(ctx.guild).tracked_category_id()
        if not category_id:
            return await ctx.send("❌ Geen categorie gekoppeld. Gebruik `[p]statbotset category <categorie>`.")

        category = ctx.guild.get_channel(category_id)
        if not isinstance(category, discord.CategoryChannel):
            return await ctx.send("❌ Gekoppelde categorie niet gevonden.")

        async with ctx.typing():
            client = StatbotClient(api_key=api_key, guild_id=ctx.guild.id)
            target_hours = await client.get_30_day_daily_average_hours()
            current_hours = await client.get_today_voice_hours()

            now = datetime.now(timezone.utc)
            if target_hours > 0:
                await self.config.guild(ctx.guild).cached_30d_target.set(target_hours)
            await self.config.guild(ctx.guild).last_target_update_day.set(now.day)

            new_name = format_category_name(current_hours, target_hours)
            await category.edit(name=new_name, reason="Handmatige Statbot Voice Sync")

        await ctx.send(
            f"🔄 **Sync Voltooid:**\n"
            f"• 30-daags gemiddelde: **{target_hours}u**\n"
            f"• Vandaag geregistreerd: **{current_hours}u**\n"
            f"• Nieuwe weergave: `{new_name}`"
        )

    @statbotset.command(name="status")
    async def show_status(self, ctx: commands.Context) -> None:
        """Toont de actuele instellingen en status van de koppeling."""
        api_key = await self._get_api_key()
        category_id = await self.config.guild(ctx.guild).tracked_category_id()
        target = await self.config.guild(ctx.guild).cached_30d_target()
        category = ctx.guild.get_channel(category_id) if category_id else None

        embed = discord.Embed(title="Statbot Voice Tracker Status", color=discord.Color.blurple())
        embed.add_field(name="API Key Ingesteld", value="✅ Ja" if api_key else "❌ Nee (`[p]set api statbot api_key,<TOKEN>`)", inline=False)
        embed.add_field(name="Gekoppelde Categorie", value=f"{category.name} (`{category.id}`)" if category else "Geen", inline=False)
        embed.add_field(name="Gecached 30d Gemiddelde", value=f"{target} uur", inline=False)

        await ctx.send(embed=embed)