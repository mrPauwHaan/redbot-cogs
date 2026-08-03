import json
import logging
import datetime
from dateutil.relativedelta import relativedelta
import aiohttp
import pytz
import discord
from discord.ext import tasks
from redbot.core import commands, Config
from redbot.core.bot import Red
from frappeclient import FrappeClient


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
    """Member Applications & Guild Management Cog voor Shadowzone"""

    def __init__(self, bot: Red) -> None:
        self.bot = bot
        self.Frappeclient = None
        self.local_timezone = pytz.timezone('Europe/Amsterdam')
        self.target_guild_id = 331058477541621774
        self.log = logging.getLogger("red.memberapplications")

        # Redbot Config voor instellingen (zoals het kanaal voor toelatingsverzoeken)
        self.config = Config.get_conf(self, identifier=331058477541621774, force_registration=True)
        default_guild = {
            "review_channel_id": None,
            "processed_requests": []
        }
        self.config.register_guild(**default_guild)

        # Dagelijkse time setup
        self.daily_loop_local_time = datetime.time(0, 0, 0, tzinfo=self.local_timezone)

    async def cog_load(self):
        frappe_keys = await self.bot.get_shared_api_tokens("frappelogin")
        api_key = frappe_keys.get("username")
        api_secret = frappe_keys.get("password")
        if api_key and api_secret:
            self.Frappeclient = FrappeClient("https://shadowzone.nl")
            self.Frappeclient.login(api_key, api_secret)
        else:
            self.log.error("API keys voor Frappe ontbreken.")
        
        self.daily_loop.change_interval(time=self.daily_loop_local_time)
        self.daily_loop.start()
        self.hourly_loop.start()
        self.applications_loop.start()

    async def cog_unload(self):
        self.daily_loop.cancel()
        self.hourly_loop.cancel()
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
    # LOOPS
    # ------------------------------------------------------------------
    @tasks.loop()
    async def daily_loop(self):
        await self._serverbanner()
        await self._birthday()

    @daily_loop.before_loop
    async def before_daily_loop(self):
        await self.bot.wait_until_ready()
        self.log.info("Daily loop is ready to start.")

    @tasks.loop(minutes=60)
    async def hourly_loop(self):
        await self._serverevents()

    @hourly_loop.before_loop
    async def before_hourly_loop(self):
        await self.bot.wait_until_ready()
        self.log.info("Hourly loop is ready to start.")

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

    @commands.command(aliases=["banner"])
    @commands.is_owner()
    async def serverbanner(self, ctx: commands.Context):
        await self._serverbanner(ctx)
        await ctx.send("Update completed")
    
    @commands.command(aliases=["bd"])
    @commands.has_permissions(manage_channels=True)
    async def birthday(self, ctx: commands.Context):
        await self._birthday(ctx)
        await ctx.send("Update completed")

    @commands.command()
    @commands.has_permissions(manage_channels=True)
    async def serverevents(self, ctx: commands.Context):
        await self._serverevents(ctx)
        await ctx.send("Update completed")

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

    # ------------------------------------------------------------------
    # EXISTING LOGIC (Banner, Birthday, Events)
    # ------------------------------------------------------------------
    async def _serverbanner(self, ctx: commands.Context = None):
        if not self.Frappeclient:
            self.log.error("FrappeClient is not available. Cannot update banner.")
            return
        response = self.Frappeclient.get_list(
            'Discord server banners', 
            fields=['*'], 
            filters={'datum': str(datetime.datetime.now(self.local_timezone).date())}, 
            limit_page_length=float('inf')
        )
        if response:
            banner_url = "http://shadowzone.nl/" + response[0]['banner']
            guild = self.bot.get_guild(self.target_guild_id)
            async with aiohttp.ClientSession() as session:
                async with session.get(banner_url) as resp:
                    if resp.status == 200:
                        image_data = await resp.read()
                        await guild.edit(
                            banner=image_data,
                            reason=f"De server banner is veranderd naar: {response[0]['name']}",
                        )
                        if response[0]['eenmalig'] == 1:
                            self.Frappeclient.delete('Discord server banners', response[0]['name'])
                        else:
                            doc = self.Frappeclient.get_doc('Discord server banners', response[0]['name'])
                            date = datetime.datetime.strptime(doc['datum'], '%Y-%m-%d').date()
                            newDate = date + relativedelta(years=1)
                            doc['datum'] = str(newDate)
                            self.Frappeclient.update(doc)
                    else:
                        self.log.error(f"Failed to download banner image from {banner_url}. Status: {resp.status}")

    async def _birthday(self, ctx: commands.Context = None):
        frappe_members = self.Frappeclient.get_list(
            'Member', 
            fields=['discord_id', 'geboortedatum', 'custom_status'], 
            filters={'custom_status': 'Actief'}, 
            limit_page_length=float('inf')
        )
        guild = self.bot.get_guild(self.target_guild_id)
        role = guild.get_role(943779141688381470)
        today = datetime.datetime.now(self.local_timezone).date()

        today_birthdays_discord_ids = set()
        if frappe_members:
            for member_data in frappe_members:
                if member_data.get('geboortedatum') and member_data.get('discord_id'):
                    geboortedatum = datetime.datetime.strptime(member_data['geboortedatum'], '%Y-%m-%d').date()
                    if geboortedatum.day == today.day and geboortedatum.month == today.month:
                        today_birthdays_discord_ids.add(member_data['discord_id'])
                        discordmember = guild.get_member(int(member_data['discord_id']))
                        if discordmember and role not in discordmember.roles:
                            await discordmember.add_roles(role, reason="Vandaag jarig")

        for birthdaymember in role.members:
            if str(birthdaymember.id) not in today_birthdays_discord_ids:
                await birthdaymember.remove_roles(role, reason="Verjaardag voorbij")

    async def _serverevents(self, ctx: commands.Context = None):
        response = self.Frappeclient.get_list('Discord events', fields=['*'], filters={'concept': 0}, limit_page_length=float('inf'))
        if response:
            guild = self.bot.get_guild(self.target_guild_id)
            for event in response:
                if event['end_time'] and datetime.datetime.strptime(event['start_time'], '%Y-%m-%d %H:%M:%S') >= datetime.datetime.strptime(event['end_time'], '%Y-%m-%d %H:%M:%S'):
                    self.log.error(f"[{event['title']}] Starttijd moet voor eindtijd zijn")
                    doc_to_update = self.Frappeclient.get_doc('Discord events', event['name'])
                    doc_to_update['status'] = 'Starttijd moet voor eindtijd zijn'
                    self.Frappeclient.update(doc_to_update)
                    continue
                
                start_time_local = self.local_timezone.localize(datetime.datetime.strptime(event['start_time'], '%Y-%m-%d %H:%M:%S'))
                if start_time_local <= datetime.datetime.now(self.local_timezone):
                    doc_to_update = self.Frappeclient.get_doc('Discord events', event['name'])
                    doc_to_update['status'] = 'Starttijd moet in de toekomst zijn'
                    self.Frappeclient.update(doc_to_update)
                    self.log.error(f"[{event['title']}] Starttijd van nieuwe events kan niet in het verleden liggen")
                    continue
                
                if datetime.datetime.strptime(event['date_create'], '%Y-%m-%d %H:%M:%S') <= datetime.datetime.now():
                    event_args = {
                        "name": event['title'],
                        "description": event['description'],
                        "start_time": self.local_timezone.localize(datetime.datetime.strptime(event['start_time'], "%Y-%m-%d %H:%M:%S")).astimezone(datetime.timezone.utc),
                        "end_time": self.local_timezone.localize(datetime.datetime.strptime(event['end_time'], "%Y-%m-%d %H:%M:%S")).astimezone(datetime.timezone.utc) if event['end_time'] else None,
                        "privacy_level": discord.PrivacyLevel.guild_only,
                    }
                    
                    if event['image']:
                        image = "http://shadowzone.nl/" + event['image']
                        async with aiohttp.ClientSession() as session:
                            async with session.get(image) as resp:
                                if resp.status == 200:
                                    image_data = await resp.read()
                                    event_args["image"] = image_data
                                else:
                                    self.log.error(f"[{event['title']}] Kan afbeelding niet downloaden")
                                    doc_to_update = self.Frappeclient.get_doc('Discord events', event['name'])
                                    doc_to_update['status'] = 'Kan afbeelding niet downloaden'
                                    self.Frappeclient.update(doc_to_update)
                                    continue

                    if 'location' in event and event['location']:
                        try:
                            int(event['location'])
                            if guild.get_channel(int(event['location'])):
                                event_args["channel"] = guild.get_channel(int(event['location']))
                            else:
                                event_args["entity_type"] = discord.EntityType.external
                                event_args["location"] = event['location']
                        except ValueError:
                            event_args["entity_type"] = discord.EntityType.external
                            event_args["location"] = event['location']

                    if 'entity_type' in event_args and event_args["entity_type"] == discord.EntityType.external:
                        if not event_args["end_time"] and event['override_check'] == 1: 
                            event_args["end_time"] = event_args["start_time"] + datetime.timedelta(hours=1)
                            self.log.error(f"[{event['title']}] Moet een eindtijd hebben, is automatisch gezet op 1 uur later")

                    await guild.create_scheduled_event(**event_args)
                    self.Frappeclient.delete('Discord events', event['name'])