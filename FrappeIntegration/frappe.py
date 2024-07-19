import discord
from discord.ext import tasks
import asyncio
from redbot.core.bot import Red
from redbot.core import commands, app_commands
from redbot.core import Config
import requests


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
        
    @app_commands.command(name="id", description="Return the user ID")
    @app_commands.describe(
        user="user",
    )
    @app_commands.default_permissions()
    @app_commands.guild_only()
    async def slash_say(
        self,
        interaction: discord.Interaction,
        user: Optional[str] = discord.Member=None,
    ):
        guild = interaction.guild
        channel = channel or interaction.channel

        author = interaction.author
        if not user:
            user = author
        
        await interaction.response.send_message(user.id, ephemeral=False)

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