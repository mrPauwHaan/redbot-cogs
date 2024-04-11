import discord
from discord.ext import commands
import asyncio
from redbot.core.bot import Red
from redbot.core import commands
from redbot.core import Config


class ChannelChanger(commands.Cog):
    def __init__(self, bot: Red) -> None:
        self.bot = bot
        self.config: Config = Config.get_conf(
            self,
            identifier=52642414967411483012286513444316154540,
            force_registration=True,
        )
        default_guild = {
            "channels": {},
            "ignoredStatus": ["Spotify", "Custom Status"]
        }
        self.config.register_guild(**default_guild)

    @commands.Cog.listener()
    async def on_ready(self):
        print(f'Logged in as {self.bot.user} (ID: {self.bot.user.id})')
        print('------')

    @commands.command()
    @commands.has_permissions(manage_channels=True)
    async def addvc(self, ctx: commands.Context, majority: float = 0.5):
        """Adds a voice channel to the watchlist."""
        if not ctx.author.voice or not ctx.author.voice.channel:
            await ctx.send("You must be in a voice channel to use this command.")
            return
        
        if majority < 0 or majority > 1:
            await ctx.send("You must enter a number between 0 and 1")
            return
        
        channel_id = ctx.author.voice.channel.id
        self.channels[channel_id] = {
            "name": ctx.author.voice.channel.name,
            "majority": majority, 
            "template": "X - Y"
        }
        await self.config.guild(ctx.guild).channels.set(self.channels)
        await ctx.send(f"Successfully added `{ctx.author.voice.channel.name}` to my list.")

    @commands.command()
    @commands.has_permissions(manage_channels=True)
    async def removevc(self, ctx):
        """Removes a voice channel from the watchlist."""
        await ctx.send("Command not possible yet")
    
    @commands.command()
    @commands.has_permissions(manage_channels=True)
    async def majority(self, ctx):
        """Set the percentage of people that have to play the game before the status changes (default = 0.5)"""
        await ctx.send("Command not possible yet")

    @commands.command()
    @commands.has_permissions(manage_channels=True)
    async def template(self, ctx):
        """Set the template for changing the voice channels (default= X - Y)"""
        await ctx.send("Command not possible yet")
    
    async def majority(self, channel, majority_percent):
        games = {}
        majority_name = ""
        majority_number = 0
        user_count = 0

        for member in channel.members:
            if not member.bot:  # Ignore bots
                user_count += 1
                if member.activities:  # Check if the member has any active games
                    # Prioritize the last activity (avoids custom statuses)
                    game_name = str(member.activities[-1]) 
                    games[game_name] = games.get(game_name, 0) + 1  # Tally the game

                    if games[game_name] > majority_number:
                        majority_name = game_name
                        majority_number = games[game_name]

        if majority_number / user_count > majority_percent:
            return majority_name
        else:
            return None  # Or you could return an empty string ""

    async def scan_one(self, ctx, channel):
        channelConfig = await self.config.guild(ctx.guild).channels[channel.id]
        if channel:
            if channel.manageble:
                newTitle = channelConfig[0]
                if channel.members.size > 0:
                    ignoredStatus = await self.config.guild(ctx.guild).ignoredStatus()

                    gameTitle = majority(channel, channelConfig[1])

                    if gameTitle not in ignoredStatus:
                        newTitle = channelConfig[2].replace("X", channelConfig[0]).replace("Y", gameTitle)
                    
            if channel.name != newTitle:
                await channel.edit(name=newTitle)

    @commands.Cog.listener(name='on_voice_state_update')
    async def on_voice_state_update(self, ctx, member, before, after):
        if before.channel_id != after.channel_id:
            if before.channel_id:
                channels = await self.config.guild(ctx.guild).channels()
                if channels.get(before.channel_id):
                    scan_one(before.channel)

            if after.channel_id:
                if channels.get(after.channel_id):
                    scan_one(after.channel)


    @commands.Cog.listener(name='on_presence_update')
    async def on_presence_update(self, ctx, before, after):
        if after.member and after.member.voice and after.member.voice.channel_id:
            channels = await self.config.guild(ctx.guild).channels()
            if channels.get(after.member.voice.channel_id):
                scan_one(after.member.voice.channel)
