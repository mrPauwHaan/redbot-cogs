import discord
from discord.ext import tasks
import asyncio
from redbot.core.bot import Red
from redbot.core import commands, app_commands
from redbot.core import Config
import requests
import json
import datetime
from dateutil.relativedelta import relativedelta
import aiohttp
from frappeclient import FrappeClient


class Frappe(commands.Cog):
    def __init__(self, bot: Red) -> None:
        self.bot = bot
        self.Frappeclient = None

    async def cog_load(self):
        frappe_keys = await self.bot.get_shared_api_tokens("frappelogin")
        api_key =  frappe_keys.get("username")
        api_secret = frappe_keys.get("password")
        if api_key and api_secret:
            self.Frappeclient = FrappeClient("https://shadowzone.nl")
            self.Frappeclient.login(api_key, api_secret)
        else:
            print("API keys for Frappe are missing.")

    @commands.guild_only()
    @commands.hybrid_command(name="id", description="Return the user ID")
    async def id(self, ctx, *, user: discord.Member=None):
        """Krijg Discord ID van gebruiker"""
        author = ctx.author

        if not user:
            user = author

        await ctx.send(user.id)

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
    @commands.is_owner()
    @commands.bot_has_permissions(embed_links=True)
    @commands.hybrid_group()
    async def frappe(self, ctx: commands.Context) -> None:
        """Commando's voor interactie met website"""
        pass
    
    @frappe.command(aliases=["bd"])
    @commands.has_permissions(manage_channels=True)
    async def birthday(self, ctx: commands.Context):
        frappe_keys = await self.bot.get_shared_api_tokens("frappe")
        """Get birthdays of today"""
        if frappe_keys.get("api_key") is None:
            return await ctx.send("The Frappe API key has not been set. Use `[p]set api` to do this.")
        api_key =  frappe_keys.get("api_key")
        api_secret = frappe_keys.get("api_secret")
        headers = {'Authorization': 'token ' +api_key+ ':' +api_secret}
        api = requests.get('http://shadowzone.nl/api/method/birthday', headers=headers)

        if api.status_code == 200:
            response = api.json()
            role = ctx.guild.get_role(943779141688381470)
            
            
            if response['result']:
                for birthdaymember in role.members:
                    if birthdaymember not in response['result']:
                        await birthdaymember.remove_roles(role, reason="Birthday is over")
                
                for birthday in response['result']:
                    message = await ctx.send(birthday['content'])
                    await message.add_reaction("🥳")
                    member = ctx.guild.get_member(int(birthday['discord_id']))
                    await member.add_roles(role, reason="Birthday starts today")
            else:
                for birthdaymember in role.members:
                    await birthdaymember.remove_roles(role, reason="Birthday is over")
            pass

        else:
            return await ctx.send("Status code:" +str(api.status_code))
        
    @frappe.command(aliases=["banner"])
    @commands.is_owner()
    async def serverbanner(self, ctx: commands.Context):
        """Update server banner based on database"""
        response = self.Frappeclient.get_list('Discord server banners', fields = ['name', 'banner'], filters = {'datum':str(datetime.date.today())})
        if response:
            banner_url = "http://shadowzone.nl/" + response[0]['banner']
            async with aiohttp.ClientSession() as session:
                async with session.get(banner_url) as resp:
                    if resp.status == 200:
                        image_data = await resp.read()
                        await ctx.guild.edit(
                            banner=image_data,
                            reason=f"De server banner is veranderd naar: {response[0]['name']}",
                        )
                        doc = self.Frappeclient.get_doc('Discord server banners', response[0]['name'])
                        date = datetime.datetime.strptime(doc['datum'], '%Y-%m-%d').date()
                        newDate = date + relativedelta(years=1)
                        doc['datum'] = str(newDate)
                        self.Frappeclient.update(doc)
                    else:
                        await ctx.send("Failed to download the banner image")

    @frappe.command()
    @commands.is_owner()
    async def contributie(self, ctx: commands.Context, jaar: str = None):
        """Check of contributie betaald is"""
        if jaar:
            data = self.Frappeclient.get_list('Member', fields = ['name','discord_id', 'custom_status'], filters = {})
            if data:
                for mtc in data:
                    doc = self.Frappeclient.get_doc("Member",mtc['name'])
                    await ctx.send(doc)

                    for item in doc.get("Member_betalingen"):
                        await ctx.send(item.field)

            if members:
                for member in members:
                    contributie = self.Frappeclient.get_list('Member_betalingen', fields = ['jaar', 'contributie', 'donaties'], filters = {'parent': member['name']})
                    if contributie:
                        if jaar in contributie:
                            await ctx.send(member['name'])
                    else:
                        await ctx.send("Er is een fout opgetreden in de API")  
            else:
                await ctx.send("Er is een fout opgetreden in de API")
        else:
            await ctx.send("Geef een jaar in")
    
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
                        if data["events"] == 1:
                            description = description + '\n' + str(data["events"]) + ' event\n' + data["icon"] + '<@' + data["member"] + '> ' + '\n'
                        else:
                            description = description + '\n' + str(data["events"]) + ' events\n' + data["icon"] + '<@' + data["member"] + '> ' + '\n'
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
    async def aanmeldingen(self, ctx: commands.Context, event: str = None):
        """Krijg een lijst van de aanmeldingen voor een specifiek event"""
        deelnemers = self.Frappeclient.get_list('Event deelnemers', fields = ["event"], order_by = 'creation desc')
        if not event:
            event = deelnemers[0]['event']
        eventcheck = self.Frappeclient.get_value("Beheer events", "event_name", {"event_name": event})
        data = ""
        amount = 0
        if eventcheck:
            deelnemers = self.Frappeclient.get_list('Event deelnemers', fields = ["event", "payment_status", "discord_id", "pakket1", "vertrek", "aankomst"], filters = {'event':event}, order_by = 'creation desc')
            embed = discord.Embed()
            if deelnemers:
                for deelnemer in deelnemers:
                    if not deelnemer['payment_status'] == "Cancelled":
                        amount = amount + 1
                        if deelnemer['payment_status'] == "Completed":
                            data = data + "\n <@" + deelnemer['discord_id'] + "> "
                        else: 
                            data = data + "\n <:min:1137646894827454565> <@" + deelnemer['discord_id'] + "> "
                        if deelnemer['pakket1']:
                            data = data + "(BBQ only)"
                        else:
                            data = data + "(" + deelnemer['aankomst'] + " - " + deelnemer['vertrek'] + ")"
                data = str(amount) + " aanmeldingen \n" + data + "\n\n" + "-# <:min:1137646894827454565> betekent niet betaald"
            else:
                data = "Geen deelnemers gevonden"
            embed.description = data
            embed.title = event + " deelnemers:"
            embed.colour = int("ff0502", 16)
            embed.set_footer(text="© Shadowzone Gaming")
            await ctx.send(embed=embed)
        else:
            events = self.Frappeclient.get_list('Beheer events', fields = ['event_name'], order_by = 'creation desc')
            for event in events:
                    data = data + '\n `"' + event['event_name'] + '"`'
            return await ctx.send("Event niet gevonden. Zorg dat je de volledige titel invult tussen aanhalingstekens \n\n __**Alle events:**__ " +str(data))