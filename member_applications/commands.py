import asyncio
import logging
import discord
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
        self.log = logging.getLogger("red.memberapplications")

        # Redbot Config voor instellingen
        self.config = Config.get_conf(self, identifier=331058477541621774, force_registration=True)
        default_guild = {
            "review_channel_id": None,
            "processed_requests": []
        }
        self.config.register_guild(**default_guild)

        # START DE TIMER DIRECT BIJ INITIALISATIE IN REDBOT
        self.log.info("🚀 [MemberApps] Initialiseren... Timer wordt aangemaakt in __init__.")
        self.loop_task = self.bot.loop.create_task(self._auto_check_loop())

    def cog_unload(self):
        # Stop de achtergrond-timer netjes bij unload/reload
        if hasattr(self, "loop_task") and self.loop_task:
            self.loop_task.cancel()
            self.log.info("🛑 [MemberApps] Achtergrond-timer is gestopt bij unload.")

    # ------------------------------------------------------------------
    # AUTOMATISCHE TIMER (DIRECT IN INIT GEKOPPELD)
    # ------------------------------------------------------------------
    async def _auto_check_loop(self):
        """Draait elke 60 seconden op de achtergrond van de bot."""
        await self.bot.wait_until_ready()
        self.log.info("✅ [MemberApps] Bot is ready! De 60-seconden achtergrond-timer loopt nu actief.")
        
        while True:
            try:
                self.log.info("⏰ [Timer Tik] Bezig met automatische minuut-check voor aanvragen...")
                count = await self._check_applications()
                self.log.info(f"🏁 [Timer Tik] Minuut-check voltooid. {count} nieuwe verzoeken verwerkt.")
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.log.exception(f"❌ [Timer Fout] Fout tijdens automatische minuut-check: {e}")
            
            await asyncio.sleep(60)

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

            # Unieke sleutel per SPECIFIEKE INZENDING
            raw_req_id = req.get("id") or req.get("request_id") or str(user_id)
            created_at = req.get("created_at", "")
            request_key = f"{raw_req_id}_{created_at}"

            processed = await self.config.guild(guild).processed_requests()
            if request_key in processed:
                return False

            review_channel_id = await self.config.guild(guild).review_channel_id()
            if not review_channel_id:
                return False

            # Haal kanaal op uit geheugen of doe een actieve API fetch
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

            # Bouw de embed op
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
        """Controleert op verzoeken via de REST API voor alle relevante guilds."""
        try:
            guilds_to_check = [guild] if guild else self.bot.guilds
            total_new = 0

            for g in guilds_to_check:
                review_channel_id = await self.config.guild(g).review_channel_id()
                if not review_channel_id:
                    continue

                requests = await self.fetch_join_requests(g.id)
                for req in requests:
                    if await self._process_single_request(req, g):
                        total_new += 1

            return total_new
        except Exception as e:
            self.log.exception(f"Fout tijdens _check_applications: {e}")
            return 0


# ==========================================
# REDBOT SETUP ENTRY POINT
# ==========================================
async def setup(bot: Red):
    await bot.add_cog(memberapplications(bot))