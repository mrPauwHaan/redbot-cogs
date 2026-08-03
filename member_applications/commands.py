import logging
import discord
from discord.ext import tasks
from redbot.core import commands, Config
from redbot.core.bot import Red


# ==========================================
# DISCORD UI VIEW VOOR GOEDKEUREN / AFWIJZEN
# ==========================================
class JoinRequestView(discord.ui.View):
    def __init__(self, cog: commands.Cog, guild_id: int, user_id: int, request_key: str):
        super().__init__(timeout=None)
        self.cog = cog
        self.guild_id = guild_id
        self.user_id = user_id
        self.request_key = request_key
        self.rejections = set()  # Slaat user_ids op van leden die voor afwijzen stemmen

    @discord.ui.button(label="Goedkeuren", style=discord.ButtonStyle.green, custom_id="btn_approve_join")
    async def approve_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        success = await self.cog.patch_join_request(self.guild_id, self.user_id, action="APPROVED")
        
        if success:
            # Verwijder uit cache zodat een eventuele toekomstige re-join weer opgepakt kan worden
            await self.cog.remove_processed_request(self.guild_id, self.request_key)
            await interaction.edit_original_response(
                content=f"✅ **Aanvraag goedgekeurd door {interaction.user.mention}!**",
                embed=interaction.message.embeds[0] if interaction.message.embeds else None,
                view=None
            )
        else:
            await interaction.followup.send("⚠️ Er is iets misgegaan bij het goedkeuren via de Discord API.", ephemeral=True)

    @discord.ui.button(label="Afwijzen (0/3)", style=discord.ButtonStyle.red, custom_id="btn_reject_join")
    async def reject_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Voorkom dat een gebruiker meerdere keren stemt
        if interaction.user.id in self.rejections:
            await interaction.response.send_message("⚠️ Je hebt al voor afwijzen gestemd op deze aanvraag!", ephemeral=True)
            return

        self.rejections.add(interaction.user.id)
        votes = len(self.rejections)

        # Als er nog geen 3 stemmen zijn, update de knop
        if votes < 3:
            button.label = f"Afwijzen ({votes}/3)"
            await interaction.response.edit_message(view=self)
        else:
            # Bij 3 stemmen sturen we de definitieve afwijzing naar Discord
            await interaction.response.defer()
            success = await self.cog.patch_join_request(self.guild_id, self.user_id, action="REJECTED")
            
            if success:
                await self.cog.remove_processed_request(self.guild_id, self.request_key)
                voters_str = ", ".join([f"<@{v_id}>" for v_id in self.rejections])
                await interaction.edit_original_response(
                    content=f"❌ **Aanvraag definitief afgewezen door {voters_str} (3/3 stemmen).**",
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
        self.log = logging.getLogger(__name__)

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
    # TASKS LOOP (EXACT ZOALS IN AUTOMATEDEVENTS)
    # ------------------------------------------------------------------
    @tasks.loop(minutes=1)
    async def applications_loop(self):
        """
        This task will run every minute to check for join requests.
        """
        try:
            await self._check_applications()
        except Exception as e:
            self.log.exception(f"Fout tijdens de minuut-loop van memberapplications: {e}")

    @applications_loop.before_loop
    async def before_applications_loop(self):
        await self.bot.wait_until_ready()
        self.log.info("Applications loop is ready to start.")

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
            if isinstance(response, list):
                return response
            elif isinstance(response, dict):
                return response.get("guild_join_requests") or response.get("requests") or []
            return []
        except discord.HTTPException as e:
            if e.status != 403:
                self.log.error(f"HTTP Fout {e.status} bij ophalen van join requests via REST: {e}")
            return []
        except Exception as e:
            self.log.exception(f"Onverwachte fout bij fetch_join_requests: {e}")
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
            self.log.error(f"HTTP Fout bij bijwerken van join request voor user {user_id}: {e}")
            return False
        except Exception as e:
            self.log.exception(f"Onverwachte fout bij patch_join_request voor user {user_id}: {e}")
            return False

    async def remove_processed_request(self, guild_id: int, request_key: str):
        """Verwijder een verwerkte sleutel uit de config zodra deze is afgehandeld."""
        guild = self.bot.get_guild(guild_id)
        if guild:
            async with self.config.guild(guild).processed_requests() as proc_list:
                if request_key in proc_list:
                    proc_list.remove(request_key)

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
        """Handmatig direct controleren op nieuwe lidmaatschapsaanvragen."""
        try:
            count = await self._check_applications(ctx.guild)
            await ctx.send(f"Verwerking voltooid. {count} nieuwe aanvraag/aanvragen verwerkt.")
        except Exception as e:
            self.log.exception(f"Fout bij handmatig uitvoeren van checkapps commando: {e}")
            await ctx.send(f"❌ Er is een fout opgetreden: {e}")

    # ------------------------------------------------------------------
    # CORE LOGIC FOR APPLICATIONS
    # ------------------------------------------------------------------
    async def _process_single_request(self, req: dict, guild: discord.Guild) -> bool:
        """Verwerkt één en enkel openstaand (SUBMITTED) verzoek."""
        try:
            status = req.get("status")
            if status and status != "SUBMITTED":
                return False

            user_id = int(req.get("user_id") or req.get("user", {}).get("id", 0))
            if not user_id:
                return False

            raw_req_id = req.get("id") or req.get("request_id") or str(user_id)
            created_at = req.get("created_at", "")
            request_key = f"{raw_req_id}_{created_at}"

            processed = await self.config.guild(guild).processed_requests()
            if request_key in processed:
                self.log.debug(f"Aanvraag voor user {user_id} overgeslagen (staat al in processed cache).")
                return False

            review_channel_id = await self.config.guild(guild).review_channel_id()
            if not review_channel_id:
                return False

            channel = guild.get_channel(review_channel_id)
            if not channel:
                try:
                    channel = await guild.fetch_channel(review_channel_id)
                except Exception as e:
                    self.log.error(f"Kanaal met ID {review_channel_id} kon niet worden opgehaald: {e}")
                    return False

            user_data = req.get("user", {})
            username = user_data.get("username", "Onbekend")
            form_responses = req.get("form_responses", [])

            # Bouw de embed op met de nieuwe titel en kleur (#ff0502)
            embed = discord.Embed(
                title="Aanvraag server joinen",
                description=f"**Gebruiker:** <@{user_id}> (`{username}`)\n**Aangemaakt:** {created_at or 'Zojuist'}",
                color=discord.Color(0xff0502)
            )

            for form_item in form_responses:
                label = form_item.get("label", "Vraag")
                response = form_item.get("response", "Geen antwoord")
                if isinstance(response, list):
                    response = ", ".join(response)
                embed.add_field(name=label, value=response or "—", inline=False)

            view = JoinRequestView(cog=self, guild_id=guild.id, user_id=user_id, request_key=request_key)
            await channel.send(embed=embed, view=view)

            # Sla op in geheugen (maximaal 100 items bewaren)
            async with self.config.guild(guild).processed_requests() as proc_list:
                proc_list.append(request_key)
                if len(proc_list) > 100:
                    proc_list[:] = proc_list[-100:]

            self.log.info(f"✅ Nieuwe aanvraag verwerkt voor user {user_id} (key: {request_key})")
            return True
        except Exception as e:
            self.log.exception(f"Fout tijdens het verwerken van een enkele request: {e}")
            return False

    async def _check_applications(self, guild: discord.Guild = None):
        """Controleert op verzoeken via de REST API."""
        try:
            if not guild:
                guild = self.bot.get_guild(self.target_guild_id)

            if not guild:
                try:
                    guild = await self.bot.fetch_guild(self.target_guild_id)
                except Exception as e:
                    self.log.error(f"Kan server {self.target_guild_id} niet ophalen: {e}")
                    return 0

            requests = await self.fetch_join_requests(guild.id)
            new_count = 0
            for req in requests:
                if await self._process_single_request(req, guild):
                    new_count += 1

            return new_count
        except Exception as e:
            self.log.exception(f"Fout tijdens _check_applications: {e}")
            return 0


# ==========================================
# REDBOT SETUP ENTRY POINT
# ==========================================
async def setup(bot: Red):
    await bot.add_cog(memberapplications(bot))