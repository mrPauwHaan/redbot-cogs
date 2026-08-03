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
        super().__init__(timeout=None)
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
                view=None
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
                view=None
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
    # RAW WEBSOCKET LISTENER (REALTIME PARSING WITHOUT REST GET)
    # ------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_socket_raw_receive(self, msg):
        """
        Vangt 'GUILD_JOIN_REQUEST_CREATE' op en verwerkt de data DIRECT
        uit de payload, zonder afhankelijk te zijn van het (defecte) REST GET-endpoint.
        """
        if isinstance(msg, bytes):
            return

        try:
            data = json.loads(msg)
            event_type = data.get("t")
            
            if event_type in ("GUILD_JOIN_REQUEST_CREATE", "GUILD_JOIN_REQUEST_UPDATE"):
                payload = data.get("d", {})
                guild_id = int(payload.get("guild_id", 0))
                
                if guild_id == self.target_guild_id:
                    self.log.info("📥 Realtime Join Request ontvangen via WebSocket! Direct verwerken...")
                    guild = self.bot.get_guild(self.target_guild_id)
                    if guild:
                        # De payload bevat vaak 'request' of is direct het object
                        req_data = payload.get("request", payload)
                        await self._process_single_request(req_data, guild)
        except Exception as e:
            pass

    # ------------------------------------------------------------------
    # DISCORD REST API ENDPOINTS
    # ------------------------------------------------------------------
    async def fetch_join_requests(self, guild_id: int, limit: int = 25):
        """
        Haalt openstaande join requests op.
        Inclusief `status=SUBMITTED` om de 500 error van Discord te voorkomen.
        """
        route = discord.http.Route("GET", f"/guilds/{guild_id}/requests?status=SUBMITTED&limit={limit}")
        try:
            response = await self.bot.http.request(route)
            return response.get("guild_join_requests", [])
        except discord.HTTPException as e:
            if e.status == 403:
                self.log.warning("Discord API: Het GET-endpoint is momenteel uitgeschakeld door Discord (403). Realtime WebSocket verwerking blijft wel gewoon werken.")
            else:
                self.log.error(f"Fout bij ophalen van join requests via REST: {e}")
            return []

    async def patch_join_request(self, guild_id: int, user_id: int, action: str):
        """
        Keurt een request goed of wijst af via:
        PATCH /guilds/{guild_id}/requests/{user_id}
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
        """Achtergrond-back-up voor als de bot tijdelijk offline was."""
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
        await ctx.send(f"Verwerking voltooid. {count} nieuwe aanvraag/aanvragen verwerkt.")

    # ------------------------------------------------------------------
    # CORE LOGIC FOR APPLICATIONS
    # ------------------------------------------------------------------
    async def _process_single_request(self, req: dict, guild: discord.Guild) -> bool:
        """Verwerkt één enkele request (afkomstig uit WebSocket óf REST API)."""
        user_id = int(req.get("user_id") or req.get("user", {}).get("id", 0))
        if not user_id:
            return False

        processed = await self.config.guild(guild).processed_requests()
        if user_id in processed:
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

        # Bouw de embed op
        embed = discord.Embed(
            title="📥 Nieuwe Lidmaatschapsaanvraag",
            description=f"**Gebruiker:** <@{user_id}> (`{username}`)\n**Aangemaakt:** {req.get('created_at', 'Zojuist')}",
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

        # Sla op dat dit verzoek al geplaatst is
        async with self.config.guild(guild).processed_requests() as proc_list:
            proc_list.append(user_id)

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