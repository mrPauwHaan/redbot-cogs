import discord
from discord.ext import tasks
import logging
from redbot.core.bot import Red
from redbot.core import commands
import datetime
from dateutil.relativedelta import relativedelta
import aiohttp
from frappeclient import FrappeClient
import pytz

class automatedevents(commands.Cog):
    def __init__(self, bot: Red) -> None:
        self.bot = bot
        self.Frappeclient = None
        self.local_timezone = pytz.timezone('Europe/Amsterdam')
        self.target_guild_id = 331058477541621774
        self.log = logging.getLogger(__name__)

        # Set local time for loop
        self.daily_loop_local_time = datetime.time(0, 0, 0, tzinfo=self.local_timezone)

    async def cog_load(self):
        frappe_keys = await self.bot.get_shared_api_tokens("frappelogin")
        api_key =  frappe_keys.get("username")
        api_secret = frappe_keys.get("password")
        if api_key and api_secret:
            self.Frappeclient = FrappeClient("https://shadowzone.nl")
            self.Frappeclient.login(api_key, api_secret)
        else:
            self.log.error("API keys for Frappe are missing.")
        
        self.daily_loop.change_interval(time=self.daily_loop_local_time)
        self.daily_loop.start()
        self.hourly_loop.start()

    async def cog_unload(self):
        self.daily_loop.cancel()
        self.hourly_loop.cancel()

    @tasks.loop()
    async def daily_loop(self):
        """
        This task will run daily at the specified time.
        """
        await self._serverbanner()
        await self._birthday()

    @daily_loop.before_loop
    async def before_daily_loop(self):
        await self.bot.wait_until_ready()
        self.log.info("Daily loop is ready to start.")

    @tasks.loop(minutes=60)
    async def hourly_loop(self):
        """
        This task will run every hour.
        """
        await self._serverevents()

    @hourly_loop.before_loop
    async def before_hourly_loop(self):
        await self.bot.wait_until_ready()
        self.log.info("Hourly loop is ready to start.")

    @commands.command(aliases=["banner"])
    @commands.is_owner()
    async def serverbanner(self, ctx: commands.Context):
        """Update server banner based on database"""
        await self._serverbanner(ctx)
        await ctx.send("Update completed")
    
    @commands.command(aliases=["bd"])
    @commands.has_permissions(manage_channels=True)
    async def birthday(self, ctx: commands.Context):
        """
        Updates birthday roles based on Frappe data.
        Adds role to members whose birthday is today and removes role
        from members who have the role but their birthday is not today.
        """
        await self._birthday(ctx)
        await ctx.send("Update completed")

    @commands.command()
    @commands.has_permissions(manage_channels=True)
    async def serverevents(self, ctx: commands.Context):
        """Add server events based on database"""
        await self._serverevents(ctx)
        await ctx.send("Update completed")

    async def _serverbanner(self, ctx: commands.Context = None):
        """Update server banner based on database"""
        if not self.Frappeclient:
            self.log.error("FrappeClient is not available. Cannot update banner.")
            return
        response = self.Frappeclient.get_list('Discord server banners', fields = ['*'], filters = {'datum':str(datetime.datetime.now(self.local_timezone).date())}, limit_page_length=float('inf'))
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
        """
        Updates birthday roles based on Frappe data.
        Adds role to members whose birthday is today and removes role
        from members who have the role but their birthday is not today.
        """
        frappe_members = self.Frappeclient.get_list('Member', fields=['discord_id', 'geboortedatum', 'custom_status'], filters={'custom_status': 'Actief'}, limit_page_length=float('inf'))
        guild = self.bot.get_guild(self.target_guild_id)
        role = guild.get_role(943779141688381470)
        today = datetime.datetime.now(self.local_timezone).date()

        # Build a set of Discord IDs for members whose birthday is today according to Frappe
        today_birthdays_discord_ids = set()
        if frappe_members:
            for member_data in frappe_members:
                # Ensure 'geboortedatum' and 'discord_id' exist and are not None
                if member_data.get('geboortedatum') and member_data.get('discord_id'):

                    geboortedatum = datetime.datetime.strptime(member_data['geboortedatum'], '%Y-%m-%d').date()

                    if geboortedatum.day == today.day and geboortedatum.month == today.month:
                        # Add the discord_id (as a string) to the set
                        today_birthdays_discord_ids.add(member_data['discord_id'])

                        # Get the discord.Member object and add the role
                        discordmember = guild.get_member(int(member_data['discord_id']))
                        if discordmember and role not in discordmember.roles:
                            await discordmember.add_roles(role, reason="Vandaag jarig")

        # Remove the role if their ID is NOT in the set of today's birthdays
        for birthdaymember in role.members:
            # Check if the member's ID (as a string) is in our set of today's birthdays
            if str(birthdaymember.id) not in today_birthdays_discord_ids:
                await birthdaymember.remove_roles(role, reason="Verjaardag voorbij")

    def _add_one_year(dt: datetime.datetime) -> datetime.datetime:
        """Voegt veilig 1 jaar toe en vangt 29 februari op bij schrikkeljaren."""
        try:
            return dt.replace(year=dt.year + 1)
        except ValueError:
            # 29 februari in een schrikkeljaar -> val terug op 28 februari volgend jaar
            return dt.replace(year=dt.year + 1, day=28)

    async def _serverevents(self, ctx: commands.Context = None):
        """Maak server events gepland via de database"""
        # Haal lijst op (eventueel via asyncio.to_thread als Frappeclient synchroon is)
        response = self.Frappeclient.get_list(
            'Discord events', 
            fields=['*'], 
            filters={'concept': 0}, 
            limit_page_length=float('inf')
        )
        if not response:
            return

        guild = self.bot.get_guild(self.target_guild_id)
        if not guild:
            self.log.error(f"Guild met ID {self.target_guild_id} niet gevonden.")
            return

        now_local = datetime.datetime.now(self.local_timezone)
        date_format = '%Y-%m-%d %H:%M:%S'

        for event in response:
            # 1. Parse datums eenmalig
            try:
                dt_start_naive = datetime.datetime.strptime(event['start_time'], date_format)
                dt_start_local = self.local_timezone.localize(dt_start_naive)
            except (ValueError, TypeError, KeyError) as e:
                self.log.error(f"[{event.get('title', 'Onbekend')}] Ongeldige start_time: {e}")
                continue

            dt_end_local = None
            if event.get('end_time'):
                try:
                    dt_end_naive = datetime.datetime.strptime(event['end_time'], date_format)
                    dt_end_local = self.local_timezone.localize(dt_end_naive)
                except ValueError:
                    pass

            # 2. Validatie start- en eindtijd
            if dt_end_local and dt_start_local >= dt_end_local:
                self.log.error(f"[{event['title']}] Starttijd moet voor eindtijd zijn")
                doc = self.Frappeclient.get_doc('Discord events', event['name'])
                doc['status'] = 'Starttijd moet voor eindtijd zijn'
                self.Frappeclient.update(doc)
                continue

            if dt_start_local <= now_local:
                doc = self.Frappeclient.get_doc('Discord events', event['name'])
                doc['status'] = 'Starttijd moet in de toekomst zijn'
                self.Frappeclient.update(doc)
                self.log.error(f"[{event['title']}] Starttijd van nieuwe events kan niet in het verleden liggen")
                continue

            # 3. Controleer creatiedatum
            if event.get('date_create'):
                try:
                    dt_create_naive = datetime.datetime.strptime(event['date_create'], date_format)
                    dt_create_local = self.local_timezone.localize(dt_create_naive)
                    if dt_create_local > now_local:
                        continue  # Nog niet publiceren
                except ValueError:
                    pass

            # 4. Stel Discord event payload samen
            event_args = {
                "name": event['title'],
                "description": event.get('description') or '',
                "start_time": dt_start_local.astimezone(datetime.timezone.utc),
                "end_time": dt_end_local.astimezone(datetime.timezone.utc) if dt_end_local else None,
                "privacy_level": discord.PrivacyLevel.guild_only,
            }

            # Afbeelding downloaden indien aanwezig
            if event.get('image'):
                image_url = "http://shadowzone.nl/" + event['image']
                async with aiohttp.ClientSession() as session:
                    async with session.get(image_url) as resp:
                        if resp.status == 200:
                            event_args["image"] = await resp.read()
                        else:
                            self.log.error(f"[{event['title']}] Kan afbeelding niet downloaden (HTTP {resp.status})")
                            doc = self.Frappeclient.get_doc('Discord events', event['name'])
                            doc['status'] = 'Kan afbeelding niet downloaden'
                            self.Frappeclient.update(doc)
                            continue

            # Kanaal- / Externe locatie-logica
            location_raw = event.get('location')
            if location_raw:
                target_channel = None
                if str(location_raw).isdigit():
                    target_channel = guild.get_channel(int(location_raw))

                if target_channel and isinstance(target_channel, (discord.VoiceChannel, discord.StageChannel)):
                    event_args["channel"] = target_channel
                else:
                    event_args["entity_type"] = discord.EntityType.external
                    event_args["location"] = str(location_raw)
            else:
                # Fallback als er geen kanaal/locatie is opgegeven
                event_args["entity_type"] = discord.EntityType.external
                event_args["location"] = "Online"

            # Discord vereist altijd een end_time voor external events
            if event_args.get("entity_type") == discord.EntityType.external and not event_args.get("end_time"):
                event_args["end_time"] = event_args["start_time"] + datetime.timedelta(hours=1)
                self.log.info(f"[{event['title']}] Eindtijd automatisch ingesteld op 1 uur na starttijd voor external event")

            # 5. Event aanmaken in Discord
            try:
                await guild.create_scheduled_event(**event_args)
            except discord.HTTPException as e:
                self.log.error(f"[{event['title']}] Fout bij aanmaken Discord event: {e}")
                continue

            # 6. Afhandeling jaarlijks vs eenmalig
            is_yearly = str(event.get('jaarlijks', '0')).lower() in ('1', 'true')

            if is_yearly:
                doc = self.Frappeclient.get_doc('Discord events', event['name'])
                
                # Starttijd + 1 jaar
                doc['start_time'] = _add_one_year(dt_start_naive).strftime(date_format)

                # Eindtijd + 1 jaar (indien aanwezig)
                if event.get('end_time'):
                    dt_end_orig = datetime.datetime.strptime(event['end_time'], date_format)
                    doc['end_time'] = _add_one_year(dt_end_orig).strftime(date_format)

                # Creatiedatum + 1 jaar (indien aanwezig)
                if event.get('date_create'):
                    dt_create_orig = datetime.datetime.strptime(event['date_create'], date_format)
                    doc['date_create'] = _add_one_year(dt_create_orig).strftime(date_format)

                doc['status'] = 'Jaarlijks event verzet naar volgend jaar'
                self.Frappeclient.update(doc)
                self.log.info(f"[{event['title']}] Jaarlijks event succesvol doorgeschoven naar volgend jaar")
            else:
                self.Frappeclient.delete('Discord events', event['name'])
                self.log.info(f"[{event['title']}] Eenmalig event verwijderd uit Frappe")