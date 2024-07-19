import discord
from discord.ext import tasks
import asyncio
from redbot.core.bot import Red
from redbot.core import commands
from redbot.core import Config
import requests


class Frappe(commands.Cog):
    def __init__(self, bot: Red) -> None:
        self.bot = bot
        self.dailybirthday.start()
    
    @tasks.loop(seconds=10)
    async def dailybirthday(self):
        channel = self.bot.get_channel(621338866955321345)

        frappe_keys = await self.bot.get_shared_api_tokens("frappe")
        """Get birthdays of today"""
        if frappe_keys.get("api_key") is None:
            return await channel.send("The Frappe API key has not been set. Use `[p]set api` to do this.")
        api_key =  frappe_keys.get("api_key")
        api_secret = frappe_keys.get("api_secret")
        headers = {'Authorization': 'token ' +api_key+ ':' +api_secret}
        api = requests.get('http://shadowzone.nl/api/method/birthday', headers=headers)

        if api.status_code == 200:
            response = api.json()
            if response['result']:
                for birthday in response['result']:
                    await channel.send(birthday['content'])
            pass

        else:
            return await channel.send("Status code:" +str(api.status_code))

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
            if response['result']:
                for birthday in response['result']:
                    await ctx.send(birthday['content'])
            pass

        else:
            return await ctx.send("Status code:" +str(api.status_code))