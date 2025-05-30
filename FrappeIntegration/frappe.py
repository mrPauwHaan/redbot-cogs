import discord
import logging
from redbot.core.bot import Red
from redbot.core import commands
import requests
import datetime
import aiohttp
import io
from frappeclient import FrappeClient
import pytz

class Frappe(commands.Cog):
    def __init__(self, bot: Red) -> None:
        self.bot = bot
        self.Frappeclient = None
        self.local_timezone = pytz.timezone('Europe/Amsterdam')
        self.target_guild_id = 331058477541621774
        self.log = logging.getLogger(__name__)

    async def cog_load(self):
        frappe_keys = await self.bot.get_shared_api_tokens("frappelogin")
        api_key =  frappe_keys.get("username")
        api_secret = frappe_keys.get("password")
        if api_key and api_secret:
            self.Frappeclient = FrappeClient("https://shadowzone.nl")
            self.Frappeclient.login(api_key, api_secret)
        else:
            self.log.error("API keys for Frappe are missing.")

    @commands.guild_only()
    @commands.hybrid_command(name="sponsorkliks", description="Zie de Sponsorkliks status")
    async def sponsorkliks(self, ctx):
        """Zie de Sponsorkliks status"""
        response = requests.get("https://www.sponsorkliks.com/api/?club=11592&call=commissions_total", headers={'User-Agent': 'My User Agent 1.0'})
        json_object = response.json()
        pending = float(json_object['commissions_total']['pending'])
        accepted = float(json_object['commissions_total']['accepted'])
        ontvangen = float(json_object['commissions_total']['sponsorkliks'])
        qualified = float(json_object['commissions_total']['qualified'])
        total = float(json_object['commissions_total']['transferred'])

        description = "P: € " +str(round(pending, 2))+ " \n A: € " +str(round(accepted, 2))+ " \n S: € " +str(round(ontvangen, 2))+ " \n Q: € " +str(round(qualified, 2))+ " \n\n T: € " +str(round(total, 2))
        
        embed = discord.Embed()
        embed.set_footer(text="© Shadowzone Gaming")
        embed.title = "Sponsorkliks"
        embed.colour = int("ff0502", 16)
        embed.add_field(name="\u200B", value=description, inline=False)
        embed.add_field(name="\u200B", value="-# P: In behandeling • A: Geaccepteerd • S: Ontvangen door Sponsorkliks • Q: Onderweg naar Shadowzone • T: Totaal overgemaakt", inline=False)
        await ctx.send(embed=embed)

    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    @commands.bot_has_permissions(embed_links=True)
    @commands.hybrid_group()
    async def frappe(self, ctx: commands.Context) -> None:
        """Commando's voor interactie met website"""
        pass

    @frappe.command()
    @commands.is_owner()
    async def steljezelfvoor(self, ctx: commands.Context):
        """Send stel jezelf voor berichten"""
        response = self.Frappeclient.get_list('Stel jezelf voor planner', filters = {'concept': 0}, fields = ['concept', 'name', 'dag', 'titel', 'url', 'text', 'url_ai'], limit_page_length=float('inf'))
        
        channel = ctx.guild.get_channel(1053344324487761980)
        if response:
            for aankondiging in response:
                if datetime.datetime.strptime(aankondiging['dag'], '%Y-%m-%d').date() <= datetime.date.today():
                    if aankondiging['url_ai']:
                        url = aankondiging['url_ai']
                        async with aiohttp.ClientSession() as session:
                                async with session.get(url) as resp:
                                    if resp.status == 200:
                                        image_data = await resp.read()
                                        with io.BytesIO(image_data) as file:
                                            await channel.create_thread(name = aankondiging['titel'], content = aankondiging['text'] + '\n\n [Lees verder...](' + aankondiging['url'] + ') \n\n Of luister naar een door AI gegenereerde podcast over deze persoon:', file=discord.File(file, aankondiging['titel'] + ".wav"))
                                            self.Frappeclient.delete('Stel jezelf voor planner', aankondiging['name'])
                    else:
                        await channel.create_thread(name = aankondiging['titel'], content = aankondiging['text'] + '\n\n [Lees verder...](' + aankondiging['url'] + ')')
                        self.Frappeclient.delete('Stel jezelf voor planner', aankondiging['name'])           

    @frappe.command()
    @commands.has_permissions(administrator=True)
    async def contributie(self, ctx: commands.Context, jaar: int):
        """Check of contributie betaald is"""
        if jaar > 2018:
            data = self.Frappeclient.get_list('Member', fields = ['name', 'membership_type','member_name', 'custom_achternaam', 'custom_status', 'custom_startdatum_donateur', 'custom_einddatum_donateur', 'custom_begin_datum', 'custom_start_lidmaatschap', 'custom_einde_datum'], order_by = 'member_name asc', filters=None, limit_start=0, limit_page_length=float('inf'))
            if data:
                message = ""
                aantal = 0
                for member in data:
                    progress = 0
                    if member['membership_type'] == 'Lid':
                        if datetime.datetime.strptime(member['custom_start_lidmaatschap'], '%Y-%m-%d').year <= jaar:
                            if member['custom_einde_datum']:
                                if datetime.datetime.strptime(member['custom_einde_datum'], '%Y-%m-%d').year >= jaar:
                                    logo = '<:szglogo:945293100824277002>'
                                    progress = 1
                            else:
                                logo = '<:szglogo:945293100824277002>'
                                progress = 1
                    if progress == 0:
                        if member['custom_startdatum_donateur']:
                            startdatum = member['custom_startdatum_donateur']
                        else:
                            startdatum = member['custom_begin_datum']
                        if startdatum:
                            if datetime.datetime.strptime(startdatum, '%Y-%m-%d').year <= jaar:
                                if member['custom_einddatum_donateur']:
                                    if datetime.datetime.strptime(member['custom_einddatum_donateur'], '%Y-%m-%d').year >= jaar:
                                        logo = '<:SZGplus:1188373927119040562>'
                                        progress = 1
                                elif not member['custom_einde_datum']:
                                    logo = '<:SZGplus:1188373927119040562>'
                                    progress = 1

                    if progress == 1:
                        jaarcheck = 0
                        doc = self.Frappeclient.get_doc("Member", member['name'])
                        for item in doc.get("custom_contributies"):
                            if item['jaar'] == jaar:
                                jaarcheck = 1
                            
                        if jaarcheck == 0:
                            message = message + '<:wrong:847044649679716383> ' + logo + member['member_name'] + ' ' + member['custom_achternaam'] + '\n'
                            aantal = aantal + 1
                        else:
                            message = message + '<:check:847044460666814484> ' + logo + member['member_name'] + ' ' + member['custom_achternaam'] + '\n'
                            aantal = aantal + 1
                if message:
                    embed = discord.Embed()
                    embed.description = "Aantal: " + str(aantal) + '\n\n' + message
                    embed.title = " Betaalde contributies/donaties " + str(jaar)
                    embed.colour = int("ff0502", 16)
                    embed.set_footer(text="© Shadowzone Gaming")
                    await ctx.send(embed=embed)
                else:
                    await ctx.send('Niks gevonden voor dit jaar')
            else:
                await ctx.send("Er is een fout opgetreden in de API")
        else:
            await ctx.send("Pas sinds 2019 zijn betalingen mogelijk")
    
    @commands.guild_only()
    @commands.bot_has_permissions(embed_links=True)
    @commands.hybrid_group()
    async def events(self, ctx: commands.Context) -> None:
        """Commands voor Shadowzone events"""
        pass

    @events.command()
    async def list(self, ctx: commands.Context):
        frappe_keys = await self.bot.get_shared_api_tokens("frappe")
        """Krijg een lijst op basis van de eventrollen"""
        if frappe_keys.get("api_key") is None:
            return await ctx.send("The Frappe API key has not been set. Use `[p]set api` to do this.")
        api_key =  frappe_keys.get("api_key")
        api_secret = frappe_keys.get("api_secret")
        headers = {'Authorization': 'token ' +api_key+ ':' +api_secret}
        api = requests.get('http://shadowzone.nl/api/method/event_ranking', headers=headers)
        if api.status_code == 200:
            response = api.json()
            embed = discord.Embed()
            data = ""
            prevamount = ""

            if response['result']:
                maxevents = max(response['result'], key=lambda x:x['events'])
                for eventnumber in reversed(range(1, maxevents['events'] + 1)):
                    if eventnumber == 1:
                        role = discord.utils.get(ctx.guild.roles, name="1 event")
                    else:
                        role = discord.utils.get(ctx.guild.roles, name= str(eventnumber) + " events")
                    
                    if role:
                        for member in role.members:
                            if any('SZGlid' in role.name for role in member.roles):
                                icon = "<:szglogo:945293100824277002>"
                            elif any('SZG+' in role.name for role in member.roles):
                                icon = "<:SZGplus:1188373927119040562>"
                            else:
                                icon = "<:szglogozwart:945293372099272724>"

                            if eventnumber == prevamount:
                                data = data + icon + '<@' + str(member.id) + '> ' + '\n'
                            else:
                                if eventnumber == 1:
                                    data = data + '\n' + str(eventnumber) + ' event\n' + icon + '<@' + str(member.id) + '> ' + '\n'
                                else:
                                    data = data + '\n' + str(eventnumber) + ' events\n' + icon + '<@' + str(member.id) + '> ' + '\n'
                            prevamount = eventnumber
                
                embed.title = "Event ranking"
                embed.set_footer(text="© Shadowzone Gaming")
                embed.colour = int("ff0502", 16)
                embed.description = data
                await ctx.send(embed=embed)
        else:
            return await ctx.send("Status code:" +str(api.status_code))

    @events.command()
    async def listdatabase(self, ctx: commands.Context):
        frappe_keys = await self.bot.get_shared_api_tokens("frappe")
        """Krijg een lijst op basis van de events in de database"""
        if frappe_keys.get("api_key") is None:
            return await ctx.send("The Frappe API key has not been set. Use `[p]set api` to do this.")
        api_key =  frappe_keys.get("api_key")
        api_secret = frappe_keys.get("api_secret")
        headers = {'Authorization': 'token ' +api_key+ ':' +api_secret}
        api = requests.get('http://shadowzone.nl/api/method/event_ranking', headers=headers)

        if api.status_code == 200:
            response = api.json()
            data = ""
            prevamount = ""
            embed = discord.Embed()
            if response['result']:
                for member in response['result']:
                    name = member['discord_id']
                    amount = member['events']
                    if member['status'] == 'Actief' and amount > 0:
                        if amount == prevamount:
                            data = data + '<@' + name + '> ' + '\n'
                        else:
                            if amount == 1:
                                data = data + '\n' + str(amount) + ' event\n <@' + name + '> ' + '\n'
                            else:
                                data = data + '\n' + str(amount) + ' events\n <@' + name + '> ' + '\n'
                        
                        embed.description = data
                        prevamount = amount
                embed.title = "Aantal bezochte events:"
                embed.colour = int("ff0502", 16)
                embed.set_footer(text="© Shadowzone Gaming")
                await ctx.send(embed=embed)
            pass

        else:
            return await ctx.send("Status code:" +str(api.status_code))
    
    @events.command()
    @commands.has_permissions(administrator=True)
    async def roleupdate(self, ctx: commands.Context):
        frappe_keys = await self.bot.get_shared_api_tokens("frappe")
        """Checkt op basis van de events in de database of gebruikers de juiste rollen hebben"""
        if frappe_keys.get("api_key") is None:
            return await ctx.send("The Frappe API key has not been set. Use `[p]set api` to do this.")
        api_key =  frappe_keys.get("api_key")
        api_secret = frappe_keys.get("api_secret")
        headers = {'Authorization': 'token ' +api_key+ ':' +api_secret}
        api = requests.get('http://shadowzone.nl/api/method/event_ranking', headers=headers)
        if api.status_code == 200:
            response = api.json()
            embed = discord.Embed()
            notfound = None
            amount_changes = 0
            if response['result']:
                for member in response['result']:
                    discord_id = member['discord_id']
                    amount = member['events']

                    member = ctx.guild.get_member(int(discord_id))
                    if member:
                        embed.title = "Eventrol wijziging"
                        embed.set_footer(text="© Shadowzone Gaming")
                        embed.colour = int("ff0502", 16)
                        try:
                            for role in member.roles:
                                if 'events' in role.name:
                                    currentrole = role
                                elif '1 event' in role.name:
                                    currentrole = role

                            if not any('events' in role.name for role in member.roles):
                                if not any('1 event' in role.name for role in member.roles):
                                    currentrole = None

                            if amount == 1:
                                role = discord.utils.get(ctx.guild.roles, name="1 event")
                            else:
                                role = discord.utils.get(ctx.guild.roles, name= str(amount) + " events")
                            
                            if role:
                                if currentrole:
                                    if not currentrole.name == role.name:
                                        embed.description = "Gebruiker: <@" + discord_id + "> \n\n <:wrong:847044649679716383> <@&" +str(currentrole.id)+ "> \n <:check:847044460666814484> <@&" +str(role.id)+ ">"
                                        await ctx.send(embed=embed)
                                        amount_changes = amount_changes + 1
                                else:
                                    embed.description = "Gebruiker: <@" + discord_id + "> \n\n <:check:847044460666814484> <@&" +str(role.id)+ ">"
                                    await ctx.send(embed=embed)
                                    amount_changes = amount_changes + 1
                            elif amount == 0:
                                if currentrole:
                                    embed.description = "Gebruiker: <@" + discord_id + "> \n\n <:wrong:847044649679716383> <@&" +str(currentrole.id)+ ">"
                                    await ctx.send(embed=embed)
                                    amount_changes = amount_changes + 1
                            else:
                                embed.description = "Gebruiker: <@" + discord_id + "> \n\n Rol `" +str(amount)+ " events` bestaat niet"
                                await ctx.send(embed=embed)
                                amount_changes = amount_changes + 1 
                        except Exception as error:
                            return await ctx.send("Error: `" +str(error)+ "`")
                    else:
                        if notfound:
                            notfound = notfound + "<@" + discord_id + "> "
                        else:
                            notfound = "<@" + discord_id + "> "
                if amount_changes == 0:
                    if notfound:
                        await ctx.send("<:check:847044460666814484> eventrollen zijn up-to-date voor leden en SZG+ \n" + "-# Gebruikers" + notfound + "niet gevonden in deze server")
                    else:
                        await ctx.send("<:check:847044460666814484> eventrollen zijn up-to-date voor leden en SZG+")
                else:
                    await ctx.send(str(amount_changes) + " wijzigingen voor leden en SZG+ \n" + "-# Gebruikers" + notfound + "niet gevonden in deze server")
        else:
            return await ctx.send("Status code:" +str(api.status_code))
        

    @events.command()
    @commands.has_permissions(administrator=True)
    async def checksystem(self, ctx: commands.Context):
        frappe_keys = await self.bot.get_shared_api_tokens("frappe")
        """Check of de eventrollen overeenkomen met de database en geeft de verschillen weer"""
        if frappe_keys.get("api_key") is None:
            return await ctx.send("The Frappe API key has not been set. Use `[p]set api` to do this.")
        api_key =  frappe_keys.get("api_key")
        api_secret = frappe_keys.get("api_secret")
        headers = {'Authorization': 'token ' +api_key+ ':' +api_secret}
        api = requests.get('http://shadowzone.nl/api/method/event_ranking', headers=headers)
        if api.status_code == 200:
            response = api.json()
            embed = discord.Embed()
            notfoundDatabase = "\n\n Wel rol, niet in database: \n"
            notfoundServertext = "\n\n Wel in database, niet in server: \n"
            notfoundServer = []
            data = []
            prevamount = ""
            description = ""

            if response['result']:
                maxevents = max(response['result'], key=lambda x:x['events'])
                for eventnumber in reversed(range(1, maxevents['events'] + 1)):
                    if eventnumber == 1:
                        role = discord.utils.get(ctx.guild.roles, name="1 event")
                    else:
                        role = discord.utils.get(ctx.guild.roles, name= str(eventnumber) + " events")
                    
                    if role:
                        for member in role.members:
                            if any(str(member.id) in user['discord_id'] for user in response['result']):
                                for user in response['result']:
                                    if user['discord_id'] == str(member.id):
                                        if user['events'] == eventnumber:
                                            icon = ":heavy_minus_sign:"
                                        else:
                                            userdata = {
                                                "events": user['events'],
                                                "member": str(member.id),
                                                "icon": "<:plus:1137646873042243625>",
                                            }
                                            if not any(user['discord_id'] in x['member'] for x in data):
                                                data.append(userdata)
                                            else:
                                                for x in data:
                                                    if user['discord_id'] == x['member']:
                                                        if not any(str(user['events']) in str(x['events']) for x in data):
                                                            data.append(userdata)
                                            icon = "<:min:1137646894827454565>"
                                            
                                        userdata = {
                                            "events": eventnumber,
                                            "member": str(member.id),
                                            "icon": icon,
                                        }
                                        data.append(userdata)
                            else:
                                notfoundDatabase = notfoundDatabase + "<@" + str(member.id) + "> "
                    else:
                        await ctx.send("Rol voor `" + str(eventnumber) + " events` niet gevonden")
                    
                for user in response['result']:
                    if not str(user['discord_id']) in notfoundServer:
                        serveruser = ctx.guild.get_member(int(user['discord_id']))
                        if not serveruser:
                            notfoundServertext = notfoundServertext + "<@" + str(user['discord_id']) + "> "
                            notfoundServer.append(str(user['discord_id']))
                        elif not any(user['discord_id'] in x['member'] for x in data):
                            if user['events'] > 0:
                                userdata = {
                                    "events": user['events'],
                                    "member": user['discord_id'],
                                    "icon": "<:plus:1137646873042243625>",
                                }
                                data.append(userdata)

                data.sort(key= lambda x:x['events'], reverse=True)
                for data in data:
                    if data["events"] == prevamount:
                        description = description + data["icon"] + '<@' + data["member"] + '> ' + '\n'
                    else:
                        description = description + f'\n{str(data["events"])} event{"s" if data["events"] > 1 else ""}\n{data["icon"]}<@{data["member"]}>\n'
                    prevamount = data["events"]

                embed.title = "Check systeem op eventrollen"
                embed.set_footer(text="© Shadowzone Gaming")
                embed.colour = int("ff0502", 16)
                embed.description = description + notfoundDatabase + notfoundServertext
                await ctx.send(embed=embed)
        else:
            return await ctx.send("Status code:" +str(api.status_code))

    @events.command()
    @commands.has_permissions(administrator=True)
    async def aanmeldingen(self, ctx: commands.Context, event: str = None, betalingen: int = 1):
        """Krijg een lijst van de aanmeldingen voor een specifiek event"""
        deelnemers = self.Frappeclient.get_list('Event deelnemers', fields = ["event"], order_by = 'creation desc', limit_page_length=float('inf'))
        if not event:
            event = deelnemers[0]['event']
        eventcheck = self.Frappeclient.get_value("Beheer events", "event_name", {"event_name": event})
        data = ""
        amount = 0
        if eventcheck:
            deelnemers = self.Frappeclient.get_list('Event deelnemers', fields = ["event", "payment_status", "discord_id", "pakket1", "vertrek", "aankomst"], filters = {'event':event}, order_by = 'creation asc', limit_page_length=float('inf'))
            embed = discord.Embed()
            if deelnemers:
                for deelnemer in deelnemers:
                    if not deelnemer['payment_status'] == "Cancelled":
                        amount = amount + 1
                        data = data + f"\n {'<:min:1137646894827454565>' if deelnemer['payment_status'] != 'Completed' and betalingen == 1 else ''} <@{deelnemer['discord_id']}>"
                        if deelnemer['pakket1']:
                            data = data + "(BBQ only)"
                        else:
                            data = data + f"({deelnemer['aankomst']} - {deelnemer['vertrek']})"
                data = str(amount) + " aanmeldingen \n" + data + f"\n\n{'-# <:min:1137646894827454565> betekent niet betaald' if betalingen == 1 else ''}"
            else:
                data = "Geen deelnemers gevonden"
            embed.description = data
            embed.title = event + " deelnemers:"
            embed.colour = int("ff0502", 16)
            embed.set_footer(text="© Shadowzone Gaming")
            await ctx.send(embed=embed)
        else:
            events = self.Frappeclient.get_list('Beheer events', fields = ['event_name'], order_by = 'creation desc', limit_page_length=float('inf'))
            for event in events:
                    data = data + f"\n `{event['event_name']}`" 
            return await ctx.send("Event niet gevonden. Zorg dat je de volledige titel invult tussen aanhalingstekens \n\n __**Alle events:**__ " +str(data))
    
    @events.command()
    @commands.has_permissions(administrator=True)
    async def opmerkingen(self, ctx: commands.Context, event: str = None):
        """Krijg een lijst van de opmerkingen, dieetwensen en ideeën voor een specifiek event"""
        deelnemers = self.Frappeclient.get_list('Event deelnemers', fields = ["event"], order_by = 'creation desc', limit_page_length=float('inf'))
        if not event:
            event = deelnemers[0]['event']
        eventcheck = self.Frappeclient.get_value("Beheer events", "event_name", {"event_name": event})
        data = ""
        amount = 0
        if eventcheck:
            deelnemers = self.Frappeclient.get_list('Event deelnemers', fields = ["event", "discord_id", "dieetwensen_ideeën_voor_tussendoortjes_etc", "ideeën_voor_het_event", "opmerkingen", "payment_status"], filters = {'event':event}, order_by = 'creation desc', limit_page_length=float('inf'))
            embed = discord.Embed()
            if deelnemers:
                for deelnemer in deelnemers:
                    if not deelnemer['payment_status'] == "Cancelled":
                        eten_part = f'\n **Eten:** {deelnemer["dieetwensen_ideeën_voor_tussendoortjes_etc"]}' if deelnemer.get('dieetwensen_ideeën_voor_tussendoortjes_etc') else ''
                        dieet_part = f'\n **Ideeën:** {deelnemer["ideeën_voor_het_event"]}' if deelnemer.get('ideeën_voor_het_event') else ''
                        opmerkingen_part = f'\n **Opmerkingen:** {deelnemer["opmerkingen"]}' if deelnemer.get('opmerkingen') else ''
                        if eten_part or dieet_part or opmerkingen_part:
                            data = data + f"\n\n <@{deelnemer['discord_id']}>  {eten_part}{dieet_part}{opmerkingen_part}"
            else:
                data = "Geen deelnemers gevonden"
            embed.description = data
            embed.title = event + " deelnemers:"
            embed.colour = int("ff0502", 16)
            embed.set_footer(text="© Shadowzone Gaming")
            await ctx.send(embed=embed)
        else:
            events = self.Frappeclient.get_list('Beheer events', fields = ['event_name'], order_by = 'creation desc', limit_page_length=float('inf'))
            for event in events:
                    data = data + '\n `"' + event['event_name'] + '"`'
            return await ctx.send("Event niet gevonden. Zorg dat je de volledige titel invult tussen aanhalingstekens \n\n __**Alle events:**__ " +str(data))