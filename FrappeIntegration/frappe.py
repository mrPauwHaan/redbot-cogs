import discord
from discord.ext import commands
import asyncio
from redbot.core.bot import Red
from redbot.core import commands
from redbot.core import Config
import requests


class Frappe(commands.Cog):
    def __init__(self, bot: Red) -> None:
        self.bot = bot
    
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
        headers = {'Authorization': 'token' +api_key+ ':' +api_secret}
        response = requests.get('http://shadowzone.nl/api/method/birthday', headers=headers)

        return await ctx.send(response.status_code)
