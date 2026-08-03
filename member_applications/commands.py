import logging
import discord
from discord.ext import tasks
from redbot.core import commands, Config
from redbot.core.bot import Red


class memberapplications(commands.Cog):
    """Member Applications Cog voor Shadowzone met Components V2 Containers"""

    def __init__(self, bot: Red) -> None:
        self.bot = bot
        self.target_guild_id = 331058477541621774
        self.log = logging.getLogger(__name__)

        # Slaat stemmen op voor afwijzing: { user_id: set(voter_ids) }
        self.rejection_votes = {}
        # Slaat raw request data op in het geheugen voor snelle toegang bij verwerking
        self.request_cache = {}

        # Redbot Config voor instellingen
        self.config = Config.get_conf(self, identifier=331058477541621774, force_registration=True)
        default_guild = {
            "review_channel_id": None,
            "forum_channel_id": 1053344324487761980,  # Standaard ingesteld op jouw forumkanaal
            "processed_requests": []
        }
        self.config.register_guild(**default_guild)

    async def cog_load(self):
        self.applications_loop.start()

    async def cog_unload(self):
        self.applications_loop.cancel()

    # ------------------------------------------------------------------
    # TASKS LOOP
    # ------------------------------------------------------------------
    @tasks.loop(minutes=1)
    async def applications_loop(self):
        """
        Draait elke minuut automatisch om aanvragen via REST op te halen.
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
    # DISCORD COMPONENTS V2 INTERACTION LISTENER
    # ------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        """Luistert naar knop-interacties van de Components V2 containers."""
        if interaction.type != discord.InteractionType.component:
            return

        custom_id = interaction.data.get("custom_id", "")
        if not custom_id.startswith("v2_app_"):
            return

        # 1. GOEDKEUREN
        if custom_id.startswith("v2_app_approve_"):
            await interaction.response.defer()
            user_id = int(custom_id.replace("v2_app_approve_", ""))
            guild_id = interaction.guild_id or self.target_guild_id

            success = await self.patch_join_request(guild_id, user_id, action="APPROVED")
            if success:
                req_data = self.request_cache.get(user_id, {})
                guild = interaction.guild or self.bot.get_guild(guild_id)
                
                # Plaats automatisch de voorstel-post in V2 Container-vorm in het forum
                if guild:
                    await self.post_to_intro_forum_v2(guild, user_id, req_data)

                # Werk de V2 Container in het review-kanaal bij naar 'Goedgekeurd'
                updated_components = self.build_v2_container_payload(
                    user_id=user_id,
                    username=req_data.get("user", {}).get("username", "Onbekend"),
                    created_at=req_data.get("created_at", ""),
                    form_responses=req_data.get("form_responses", []),
                    status_banner=f"✅ **Aanvraag goedgekeurd door {interaction.user.mention}!**"
                )
                
                route = discord.http.Route("PATCH", f"/channels/{interaction.channel_id}/messages/{interaction.message.id}")
                await self.bot.http.request(route, json={
                    "flags": 32768,  # IS_COMPONENTS_V2
                    "components": updated_components
                })
            else:
                await interaction.followup.send("⚠️ Er is iets misgegaan bij het goedkeuren via de Discord API.", ephemeral=True)

        # 2. AFWIJZEN (MET 3 STEMMEN REGEL)
        elif custom_id.startswith("v2_app_reject_"):
            user_id = int(custom_id.replace("v2_app_reject_", ""))
            guild_id = interaction.guild_id or self.target_guild_id

            if user_id not in self.rejection_votes:
                self.rejection_votes[user_id] = set()

            if interaction.user.id in self.rejection_votes[user_id]:
                await interaction.response.send_message("⚠️ Je hebt al voor afwijzen gestemd op deze aanvraag!", ephemeral=True)
                return

            self.rejection_votes[user_id].add(interaction.user.id)
            votes_count = len(self.rejection_votes[user_id])
            req_data = self.request_cache.get(user_id, {})

            if votes_count < 3:
                # Update de knop-teller op de V2 container
                await interaction.response.defer()
                updated_components = self.build_v2_container_payload(
                    user_id=user_id,
                    username=req_data.get("user", {}).get("username", "Onbekend"),
                    created_at=req_data.get("created_at", ""),
                    form_responses=req_data.get("form_responses", []),
                    rejection_votes=votes_count
                )
                route = discord.http.Route("PATCH", f"/channels/{interaction.channel_id}/messages/{interaction.message.id}")
                await self.bot.http.request(route, json={
                    "flags": 32768,  # IS_COMPONENTS_V2
                    "components": updated_components
                })
            else:
                # Bij 3 stemmen definitief afwijzen
                await interaction.response.defer()
                success = await self.patch_join_request(guild_id, user_id, action="REJECTED")
                if success:
                    voters_str = ", ".join([f"<@{v_id}>" for v_id in self.rejection_votes[user_id]])
                    updated_components = self.build_v2_container_payload(
                        user_id=user_id,
                        username=req_data.get("user", {}).get("username", "Onbekend"),
                        created_at=req_data.get("created_at", ""),
                        form_responses=req_data.get("form_responses", []),
                        status_banner=f"❌ **Aanvraag definitief afgewezen door {voters_str} (3/3 stemmen).**"
                    )
                    route = discord.http.Route("PATCH", f"/channels/{interaction.channel_id}/messages/{interaction.message.id}")
                    await self.bot.http.request(route, json={
                        "flags": 32768,  # IS_COMPONENTS_V2
                        "components": updated_components
                    })
                    self.rejection_votes.pop(user_id, None)
                else:
                    await interaction.followup.send("⚠️ Er is iets misgegaan bij het afwijzen via de Discord API.", ephemeral=True)

    # ------------------------------------------------------------------
    # COMPONENTS V2 CONTAINER PAYLOAD BUILDER
    # ------------------------------------------------------------------
    def build_v2_container_payload(self, user_id: int, username: str, created_at: str, form_responses: list, rejection_votes: int = 0, status_banner: str = None) -> list:
        """
        Bouwt de officiële Discord Components V2 Container JSON-structuur op voor de beoordeling.
        """
        header_text = f"## Aanvraag server joinen\n**Gebruiker:** <@{user_id}> (`{username}`)\n**Aangemaakt:** {created_at or 'Zojuist'}"
        if status_banner:
            header_text = f"{status_banner}\n\n" + header_text

        container_children = [
            {
                "type": 10,  # Text Display
                "content": header_text
            },
            {
                "type": 14,  # Separator Component
                "divider": True,
                "spacing": 1
            }
        ]

        # In het reviewkanaal tonen we ALTIJD alle vragen
        for item in form_responses:
            label = item.get("label", "Vraag")
            response = item.get("response", "Geen antwoord")
            if isinstance(response, list):
                response = ", ".join(response)

            container_children.append({
                "type": 10,  # Text Display
                "content": f"**{label}**\n▸ {response or '—'}"
            })

        container_children.append({
            "type": 14,  # Separator Component
            "divider": True,
            "spacing": 1
        })

        container_children.append({
            "type": 10,  # Text Display
            "content": f"-# User ID: `{user_id}`"
        })

        components_payload = [
            {
                "type": 17,  # Container Component
                "components": container_children
            }
        ]

        # Knoppen toevoegen zolang er geen eindstatus is
        if not status_banner:
            components_payload.append({
                "type": 1,  # Action Row
                "components": [
                    {
                        "type": 2,  # Button
                        "style": 3,  # Green / Success
                        "label": "Goedkeuren",
                        "emoji": {"name": "✅"},
                        "custom_id": f"v2_app_approve_{user_id}"
                    },
                    {
                        "type": 2,  # Button
                        "style": 4,  # Red / Danger
                        "label": f"Afwijzen ({rejection_votes}/3)",
                        "emoji": {"name": "❌"},
                        "custom_id": f"v2_app_reject_{user_id}"
                    }
                ]
            })

        return components_payload

    # ------------------------------------------------------------------
    # FORUM POSTING VIA V2 CONTAINERS (MET GEFILTERDE VRAGEN)
    # ------------------------------------------------------------------
    async def post_to_intro_forum_v2(self, guild: discord.Guild, user_id: int, req_data: dict):
        """Plaatst een voorstel-thread in het forumkanaal met een V2 Container."""
        try:
            forum_channel_id = await self.config.guild(guild).forum_channel_id()
            if not forum_channel_id:
                forum_channel_id = 1053344324487761980

            member = guild.get_member(user_id)
            if not member:
                try:
                    member = await guild.fetch_member(user_id)
                except Exception:
                    member = None

            username = member.display_name if member else f"Gebruiker {user_id}"
            thread_title = f"{username}"[:100]

            form_responses = req_data.get("form_responses", [])

            # Vragen uitsluiten die niet in de forum post hoeven
            EXCLUDED_QUESTIONS = [
                "Read and agree to the server rules",
                "Lees en ga akkoord met de serverregels"
            ]

            forum_container_children = [
                {
                    "type": 10,  # Text Display
                    "content": f"## 👋 Welkom in Shadowzone, <@{user_id}>!\nStel je gerust verder voor of klets gezellig mee in de server 🎉"
                }
            ]

            # Haal de vragen op die NIET op de uitsluitlijst staan
            valid_responses = [
                item for item in form_responses 
                if item.get("label") not in EXCLUDED_QUESTIONS
            ]

            if valid_responses:
                forum_container_children.append({
                    "type": 14,  # Separator Component
                    "divider": True,
                    "spacing": 1
                })

                for item in valid_responses:
                    label = item.get("label", "Vraag")
                    response = item.get("response", "Geen antwoord")
                    if isinstance(response, list):
                        response = ", ".join(response)

                    forum_container_children.append({
                        "type": 10,  # Text Display
                        "content": f"**{label}**\n▸ {response or '—'}"
                    })

            # FIX: Top-level "content" verwijderd bij IS_COMPONENTS_V2 flag
            payload = {
                "name": thread_title,
                "message": {
                    "flags": 32768,  # IS_COMPONENTS_V2
                    "components": [
                        {
                            "type": 17,  # Container Component
                            "components": forum_container_children
                        }
                    ]
                }
            }

            route = discord.http.Route("POST", f"/channels/{forum_channel_id}/threads")
            await self.bot.http.request(route, json=payload)
            self.log.info(f"✅ Voorstel-thread in V2 Container succesvol aangemaakt voor user {user_id}")
        except Exception as e:
            self.log.exception(f"Fout bij het aanmaken van V2 forum-thread: {e}")

    # ------------------------------------------------------------------
    # DISCORD REST API ENDPOINTS
    # ------------------------------------------------------------------
    async def fetch_join_requests(self, guild_id: int, limit: int = 25):
        """Haalt openstaande join requests op via het REST endpoint."""
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
        """Keurt een request goed of wijst af via PATCH /guilds/{guild_id}/requests/{user_id}."""
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

    @appset.command(name="forum")
    async def set_forum_channel(self, ctx: commands.Context, channel: discord.ForumChannel):
        """Stel het forumkanaal in voor automatische voorstel-posts."""
        await self.config.guild(ctx.guild).forum_channel_id.set(channel.id)
        await ctx.send(f"✅ Voorstel-posts worden vanaf nu gestuurd naar {channel.mention}.")

    @appset.command(name="reset")
    async def reset_processed(self, ctx: commands.Context):
        """Wist het geheugen van reeds verwerkte verzoeken."""
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
        """Verwerkt één en enkel openstaand (SUBMITTED) verzoek via Components V2 Container."""
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
                return False

            review_channel_id = await self.config.guild(guild).review_channel_id()
            if not review_channel_id:
                return False

            user_data = req.get("user", {})
            username = user_data.get("username", "Onbekend")
            form_responses = req.get("form_responses", [])

            # Sla de raw request op in het tijdelijke geheugen
            self.request_cache[user_id] = req

            # Bouw de V2 Container payload op
            v2_components = self.build_v2_container_payload(
                user_id=user_id,
                username=username,
                created_at=created_at,
                form_responses=form_responses
            )

            # Verstuur het bericht rechtstreeks via REST met V2 flags
            route = discord.http.Route("POST", f"/channels/{review_channel_id}/messages")
            payload = {
                "flags": 32768,  # IS_COMPONENTS_V2
                "components": v2_components
            }
            await self.bot.http.request(route, json=payload)

            # Sla op in de Redbot Config
            async with self.config.guild(guild).processed_requests() as proc_list:
                proc_list.append(request_key)
                if len(proc_list) > 100:
                    proc_list[:] = proc_list[-100:]

            self.log.info(f"✅ Nieuwe V2 Container aanvraag verwerkt voor user {user_id} (key: {request_key})")
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