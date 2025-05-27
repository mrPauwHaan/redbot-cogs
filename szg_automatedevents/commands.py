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

        # --- Set UTC times for the loops ---
        self.daily_loop_utc = self.local_timezone.localize(datetime.datetime.combine(datetime.date.today(), datetime.time(0, 0, 0))).astimezone(datetime.timezone.utc).time()

    async def cog_load(self):
        frappe_keys = await self.bot.get_shared_api_tokens("frappelogin")
        api_key =  frappe_keys.get("username")
        api_secret = frappe_keys.get("password")
        if api_key and api_secret:
            self.Frappeclient = FrappeClient("https://shadowzone.nl")
            self.Frappeclient.login(api_key, api_secret)
        else:
            self.log.error("API keys for Frappe are missing.")
        
        self.daily_loop.change_interval(time=self.daily_loop_utc)
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
        self.log.info("Automated daily loop triggered.")
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
        self.log.info("Automated hourly loop triggered.")
        await self._serverbanner()
        await self._birthday()
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
        response = self.Frappeclient.get_list('Discord server banners', fields = ['name', 'banner'], filters = {'datum':str(datetime.date.today())}, limit_page_length=float('inf'))
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
        today = datetime.date.today()

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

    async def _serverevents(self, ctx: commands.Context = None):
        """Maak server events gepland via de database"""
        response = self.Frappeclient.get_list('Discord events', fields = ['*'], filters = {'concept': 0}, limit_page_length=float('inf'))
        if response:
            guild = self.bot.get_guild(self.target_guild_id)
            image_data = None
            for event in response:
                if event['end_time'] and datetime.datetime.strptime(event['start_time'], '%Y-%m-%d %H:%M:%S') >= datetime.datetime.strptime(event['end_time'], '%Y-%m-%d %H:%M:%S'):
                    self.log.error(f"[{event['title']}] Starttijd moet voor eindtijd zijn")
                    doc_to_update = self.Frappeclient.get_doc('Discord events', event['name'])
                    doc_to_update['status'] = 'Starttijd moet voor eindtijd zijn'
                    self.Frappeclient.update(doc_to_update)
                    continue
                if datetime.datetime.strptime(event['start_time'], '%Y-%m-%d %H:%M:%S') <= datetime.datetime.now():
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