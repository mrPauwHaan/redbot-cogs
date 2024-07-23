import discord
from discord.ext import tasks
import asyncio
from redbot.core.bot import Red
from redbot.core import commands, app_commands
from redbot.core import Config
import requests
import json


class Frappe(commands.Cog):
    def __init__(self, bot: Red) -> None:
        self.bot = bot

    @commands.guild_only()
    @commands.hybrid_command(name="id", description="Return the user ID")
    async def id(self, ctx, *, user: discord.Member=None):
        """Send back the user ID of the sender"""
        author = ctx.author

        if not user:
            user = author

        await ctx.send(user.id)

    @commands.guild_only()
    @commands.hybrid_command(name="sponsorkliks", description="Zie de Sponsorkliks status")
    async def sponsorkliks(self, ctx):
        """Zie de Sponsorkliks statu"""
        response = requests.get("https://www.sponsorkliks.com/api/?club=11592&call=commissions_total", headers={'User-Agent': 'My User Agent 1.0'})
        json_object = response.json()
        pending = float(json_object['commissions_total']['pending'])
        accepted = float(json_object['commissions_total']['accepted'])
        ontvangen = float(json_object['commissions_total']['sponsorkliks'])
        qualified = float(json_object['commissions_total']['qualified'])
        total = float(json_object['commissions_total']['transferred'])

        description = "P: " +str(round(pending, 2))+ " \n A: " +str(round(accepted, 2))+ " \n S: " +str(round(ontvangen, 2))+ " \n Q: " +str(round(qualified, 2))+ " \n\n T: " +str(round(total, 2))
        
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
        """Group of commands to use Frappe."""
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
                    await ctx.send(birthday['content'])
                    member = ctx.guild.get_member(int(birthday['discord_id']))
                    await member.add_roles(role, reason="Birthday starts today")
            else:
                for birthdaymember in role.members:
                    await birthdaymember.remove_roles(role, reason="Birthday is over")
            pass

        else:
            return await ctx.send("Status code:" +str(api.status_code))
    
    @commands.guild_only()
    @commands.is_owner()
    @commands.bot_has_permissions(embed_links=True)
    @commands.hybrid_group()
    async def events(self, ctx: commands.Context) -> None:
        """Commands voor Shadowzone events"""
        pass

    @events.command()
    @commands.has_permissions(manage_channels=True)
    async def list(self, ctx: commands.Context):
        frappe_keys = await self.bot.get_shared_api_tokens("frappe")
        """Get events"""
        if frappe_keys.get("api_key") is None:
            return await ctx.send("The Frappe API key has not been set. Use `[p]set api` to do this.")
        api_key =  frappe_keys.get("api_key")
        api_secret = frappe_keys.get("api_secret")
        headers = {'Authorization': 'token ' +api_key+ ':' +api_secret}
        api = requests.get('http://shadowzone.nl/api/method/event_ranking', headers=headers)

        if api.status_code == 200:
            response = api.json()
            data = ""
            prevamount = max(response['result'], key=lambda x:x['events'])
            embed = discord.Embed()
            if response['result']:
                for member in response['result']:
                    name = member['name']
                    amount = member['events']
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
    @commands.has_permissions(manage_channels=True)
    async def roleupdate(self, ctx: commands.Context):
        frappe_keys = await self.bot.get_shared_api_tokens("frappe")
        """Update the events roles"""
        if frappe_keys.get("api_key") is None:
            return await ctx.send("The Frappe API key has not been set. Use `[p]set api` to do this.")
        api_key =  frappe_keys.get("api_key")
        api_secret = frappe_keys.get("api_secret")
        headers = {'Authorization': 'token ' +api_key+ ':' +api_secret}
        api = requests.get('http://shadowzone.nl/api/method/event_ranking', headers=headers)
        embed = discord.Embed()

        if api.status_code == 200:
            response = api.json()
            embed = discord.Embed()
            if response['result']:
                for member in response['result']:
                    discord_id = member['name']
                    amount = member['events']

                    member = ctx.guild.get_member(int(discord_id))

                    memberroles = member.roles
                    for role in memberroles:
                        if 'events' in role.name:
                            currentrole = "<@" +discord_id+ "> heeft " +role.name

                    if not any('events' in role.name for role in memberroles):
                        currentrole = "<@" +discord_id+ "> heeft geen event rollen"

                    if amount == 1:
                        role = discord.utils.get(ctx.guild.roles, name="1 event")
                        newrole = "<@" +discord_id+ "> krijgt " +role.name
                    else:
                        try:
                            role = discord.utils.get(ctx.guild.roles, name= str(amount) + " events")
                            if role:
                                newrole = "<@" +discord_id+ "> krijgt " +role.name
                            else:
                                newrole = "Rol `" +str(amount)+ " events` bestaat niet"

                            embed.description = currentrole + "\n " +newrole
                            embed.title = "Eventrol wijziging"
                            embed.colour = int("ff0502", 16)
                            embed.set_footer(text="© Shadowzone Gaming")
                            await ctx.send(embed=embed)
                        except Exception as error:
                            return await ctx.send("Error: `" +str(error)+ "`")
            pass

        else:
            return await ctx.send("Status code:" +str(api.status_code))