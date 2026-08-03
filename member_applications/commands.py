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
    # RAW WEBSOCKET LISTENER (REALTIME & STRIKT)
    # ------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_socket_raw_receive(self, msg):
        """
        Luistert live naar het ruwe WebSocket-verkeer van Discord.
        Vangt 'GUILD_JOIN_REQUEST_CREATE' en 'UPDATE' op.
        """
        if isinstance(msg, bytes):
            return  # Sla audio/voice pakketjes over voor performance

        try:
            data = json.loads(msg)
            event_type = data.get("t")
            
            if event_type in ("GUILD_JOIN_REQUEST_CREATE", "GUILD_JOIN_REQUEST_UPDATE"):
                payload = data.get("d", {})
                req_data = payload.get("request", payload)
                
                # Haal guild_id op uit root payload óf uit het request object
                guild_id_raw = payload.get("guild_id") or req_data.get("guild_id", 0)
                guild_id = int(guild_id_raw)
                
                if guild_id == self.target_guild_id:
                    guild = self.bot.get_guild(self.target_guild_id)
                    if guild:
                        # Verwerkt het verzoek direct vanuit het pakket
                        await self._process_single_request(req_data, guild)
        except Exception as e:
            self.log.debug(f"Fout bij verwerken van WebSocket event: {e}")

    # ------------------------------------------------------------------
    # DISCORD REST API ENDPOINTS
    # ------------------------------------------------------------------
    async def fetch_join_requests(self, guild_id: int, limit: int = 25):
        """
        Haalt openstaande join requests op via het REST endpoint.
        Status query `status=SUBMITTED` voorkomt Discord 500 errors.
        """
        route = discord.http.Route("GET", f"/guilds/{guild_id}/requests?status=SUBMITTED&limit={limit}")
        try:
            response = await self.bot.http.request(route)
            return response.get("guild_join_requests", [])
        except discord.HTTPException as e:
            if e.status != 403:
                self.log.error(f"Fout bij ophalen van join requests via REST: {e}")
            return []

    async def patch_join_request(self, guild_id: int, user_id: int, action: str):
        """
        Keurt een request goed of wijst af via:
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

    @appset.command(name="reset")
    async def reset_processed(self, ctx: commands.Context):
        """Wist het geheugen van reeds verwerkte verzoeken (handig bij testen)."""
        await self.config.guild(ctx.guild).processed_requests.set([])
        await ctx.send("🧹 Het geheugen van verwerkte verzoeken is gewist!")

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def checkapps(self, ctx: commands.Context):
        """Handmatig controleren op nieuwe lidmaatschapsaanvragen."""
        count = await self._check_applications(ctx.guild)
        await ctx.send(f"Verwerking voltooid. {count} nieuwe aanvraag/aanvragen verwerkt.")

    # ------------------------------------------------------------------
    # CORE LOGIC FOR APPLICATIONS
    # ------------------------------------------------------------------
    async def _process_single_request(self, req: dict, guild: discord.Guild) -> bool:
        """Verwerkt één en enkel openstaand (SUBMITTED) verzoek."""
        # 1. Negeer verzoeken die niet de status 'SUBMITTED' hebben (voorkomt verwerking van APPROVED/REJECTED updates)
        status = req.get("status")
        if status and status != "SUBMITTED":
            return False

        user_id = int(req.get("user_id") or req.get("user", {}).get("id", 0))
        if not user_id:
            return False

        # 2. Unieke sleutel per SPECIFIEKE INZENDING (combineert request_id met de aanmaaktijd)
        raw_req_id = req.get("id") or req.get("request_id") or str(user_id)
        created_at = req.get("created_at", "")
        request_key = f"{raw_req_id}_{created_at}"

        processed = await self.config.guild(guild).processed_requests()
        if request_key in processed:
            return False

        review_channel_id = await self.config.guild(guild).review_channel_id()
        if not review_channel_id:
            return False

        channel = guild.get_channel(review_channel_id)
        if not channel:
            return False

        user_data = req.get("user", {})
        username = user_data.get("username", "Onbekend")
        form_responses = req.get("form_responses", [])

        # 3. Bouw de embed op
        embed = discord.Embed(
            title="📥 Nieuwe Lidmaatschapsaanvraag",
            description=f"**Gebruiker:** <@{user_id}> (`{username}`)\n**Aangemaakt:** {created_at or 'Zojuist'}",
            color=discord.Color.blue()
        )

        for form_item in form_responses:
            label = form_item.get("label", "Vraag")
            response = form_item.get("response", "Geen antwoord")
            if isinstance(response, list):
                response = ", ".join(response)
            embed.add_field(name=label, value=response or "—", inline=False)

        view = JoinRequestView(cog=self, guild_id=guild.id, user_id=user_id)
        await channel.send(embed=embed, view=view)

        # 4. Sla op in geheugen (maximaal 100 items bewaren)
        async with self.config.guild(guild).processed_requests() as proc_list:
            proc_list.append(request_key)
            if len(proc_list) > 100:
                proc_list[:] = proc_list[-100:]

        self.log.info(f"✅ Nieuwe aanvraag verwerkt voor user {user_id} (key: {request_key})")
        return True

    async def _check_applications(self, guild: discord.Guild = None):
        """Controleert op verzoeken via de REST API (back-up)."""
        if not guild:
            guild = self.bot.get_guild(self.target_guild_id)
        if not guild:
            return 0

        requests = await self.fetch_join_requests(guild.id)
        new_count = 0
        for req in requests:
            if await self._process_single_request(req, guild):
                new_count += 1

        return new_count