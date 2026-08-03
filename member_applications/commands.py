import json
import logging
import discord
from discord.ext import tasks
from redbot.core import commands, Config
from redbot.core.bot import Red


# ==========================================
# DISCORD UI VIEW VOOR GOEDKEUREN / AFWIJZEN
# ==========================================
class JoinRequestView(discord.ui.View):
    def __init__(self, cog: commands.Cog, guild_id: int, user_id: int):
        super().__init__(timeout=None)  # Knoppen blijven actief zolang het bericht bestaat
        self.cog = cog
        self.guild_id = guild_id
        self.user_id = user_id

    @discord.ui.button(label="Goedkeuren", style=discord.ButtonStyle.green, custom_id="btn_approve_join")
    async def approve_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        success = await self.cog.patch_join_request(self.guild_id, self.user_id, action="APPROVED")
        
        if success:
            await interaction.edit_original_response(
                content=f"✅ **Aanvraag goedgekeurd door {interaction.user.mention}!**",
                embed=interaction.message.embeds[0] if interaction.message.embeds else None,
                view=None  # Verwijder de knoppen na afhandeling
            )
        else:
            await interaction.followup.send("⚠️ Er is iets misgegaan bij het goedkeuren via de Discord API.", ephemeral=True)

    @discord.ui.button(label="Afwijzen", style=discord.ButtonStyle.red, custom_id="btn_reject_join")
    async def reject_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        success = await self.cog.patch_join_request(self.guild_id, self.user_id, action="REJECTED")
        
        if success:
            await interaction.edit_original_response(
                content=f"❌ **Aanvraag afgewezen door {interaction.user.mention}.**",
                embed=interaction.message.embeds[0] if interaction.message.embeds else None,
                view=None  # Verwijder de knoppen na afhandeling
            )
        else:
            await interaction.followup.send("⚠️ Er is iets misgegaan bij het afwijzen via de Discord API.", ephemeral=True)


# ==========================================
# REDBOT COG
# ==========================================
class memberapplications(commands.Cog):
    """Member Applications Cog voor Shadowzone"""

    def __init__(self, bot: Red) -> None:
        self.bot = bot
        self.target_guild_id = 331058477541621774
        self.log = logging.getLogger("red.memberapplications")

        # Redbot Config voor instellingen
        self.config = Config.get_conf(self, identifier=331058477541621774, force_registration=True)
        default_guild = {
            "review_channel_id": None,
            "processed_requests": []
        }
        self.config.register_guild(**default_guild)

    async def cog_load(self):
        self.applications_loop.start()

    async def cog_unload(self):
        self.applications_loop.cancel()

    # ------------------------------------------------------------------
    # RAW WEBSOCKET LISTENER (REALTIME)
    # ------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_socket_raw_receive(self, msg):
        """
        Luistert live naar het ruwe WebSocket-verkeer van Discord.
        Vangt 'GUILD_JOIN_REQUEST_CREATE' op voor directe verwerking!
        """
        if isinstance(msg, bytes):
            return  # Sla audio/voice pakketjes over voor performance

        try:
            data = json.loads(msg)
            if data.get("t") in ("GUILD_JOIN_REQUEST_CREATE", "GUILD_JOIN_REQUEST_UPDATE"):
                guild_id = int(data.get("d", {}).get("guild_id", 0))
                
                if guild_id == self.target_guild_id:
                    self.log.info("📥 Realtime Join Request ontvangen via WebSocket!")
                    await self._check_applications()
        except Exception:
            pass  # Negeer parse errors van ongerelateerd netwerkverkeer

    # ------------------------------------------------------------------
    # DISCORD REST API ENDPOINTS FOR JOIN REQUESTS
    # ------------------------------------------------------------------
    async def fetch_join_requests(self, guild_id: int, limit: int = 25):
        """
        Haalt openstaande join requests op via het Discord API endpoint:
        GET /guilds/{guild_id}/requests
        """
        route = discord.http.Route("GET", f"/guilds/{guild_id}/requests?limit={limit}")
        try:
            response = await self.bot.http.request(route)
            return response.get("guild_join_requests", [])
        except discord.HTTPException as e:
            self.log.error(f"Fout bij ophalen van join requests: {e}")
            return []

    async def patch_join_request(self, guild_id: int, user_id: int, action: str):
        """
        Keurt een request goed of wijst af via het Discord API endpoint:
        PATCH /guilds/{guild_id}/requests/{user_id}
        action kan 'APPROVED' of 'REJECTED' zijn.
        """
        route = discord.http.Route("PATCH", f"/guilds/{guild_id}/requests/{user_id}")
        payload = {"action": action}
        try:
            await self.bot.http.request(route, json=payload)
            return True
        except discord.HTTPException as e:
            self.log.error(f"Fout bij bijwerken van join request voor user {user_id}: {e}")
            return False

    # ------------------------------------------------------------------
    # BACKUP LOOP
    # ------------------------------------------------------------------
    @tasks.loop(minutes=15)
    async def applications_loop(self):
        """Achtergrond-back-up die elke 15 minuten controleert voor het geval een WebSocket event gemist is."""
        await self._check_applications()

    @applications_loop.before_loop
    async def before_applications_loop(self):
        await self.bot.wait_until_ready()

    # ------------------------------------------------------------------
    # COMMANDS
    # ------------------------------------------------------------------
    @commands.group(name="appset")
    @commands.has_permissions(administrator=True)
    async def appset(self, ctx: commands.Context):
        """Beheer de instellingen voor lidmaatschapsaanvragen."""
        pass

    @appset.command(name="channel")
    async def set_review_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        """Stel het kanaal in waar aanvragen binnenkomen."""
        await self.config.guild(ctx.guild).review_channel_id.set(channel.id)
        await ctx.send(f"✅ Aanvragen worden vanaf nu gestuurd naar {channel.mention}.")

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def checkapps(self, ctx: commands.Context):
        """Handmatig controleren op nieuwe lidmaatschapsaanvragen."""
        count = await self._check_applications(ctx.guild)
        await ctx.send(f"Verwerking voltooid. {count} nieuwe aanvraag/aanvragen gevonden.")

    # ------------------------------------------------------------------
    # CORE LOGIC FOR APPLICATIONS
    # ------------------------------------------------------------------
    async def _check_applications(self, guild: discord.Guild = None):
        if not guild:
            guild = self.bot.get_guild(self.target_guild_id)
        if not guild:
            return 0

        review_channel_id = await self.config.guild(guild).review_channel_id()
        if not review_channel_id:
            return 0

        channel = guild.get_channel(review_channel_id)
        if not channel:
            return 0

        requests = await self.fetch_join_requests(guild.id)
        processed = await self.config.guild(guild).processed_requests()

        new_count = 0
        for req in requests:
            user_id = int(req.get("user_id"))
            
            # Voorkom dat hetzelfde verzoek meerdere keren in het kanaal geplaatst wordt
            if user_id in processed:
                continue

            user_data = req.get("user", {})
            username = user_data.get("username", "Onbekend")
            form_responses = req.get("form_responses", [])

            # Bouw de embed op
            embed = discord.Embed(
                title="📥 Nieuwe Lidmaatschapsaanvraag",
                description=f"**Gebruiker:** <@{user_id}> (`{username}`)\n**Aangemaakt:** {req.get('created_at', 'Onbekend')}",
                color=discord.Color.blue()
            )

            # Voeg antwoorden uit het onboarding-formulier toe
            for form_item in form_responses:
                label = form_item.get("label", "Vraag")
                response = form_item.get("response", "Geen antwoord")
                if isinstance(response, list):
                    response = ", ".join(response)
                embed.add_field(name=label, value=response or "—", inline=False)

            view = JoinRequestView(cog=self, guild_id=guild.id, user_id=user_id)
            await channel.send(embed=embed, view=view)

            # Sla op dat dit verzoek al verwerkt/geplaatst is
            async with self.config.guild(guild).processed_requests() as proc_list:
                proc_list.append(user_id)

            new_count += 1

        return new_count