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
        """Adds a voice channel to the watchlist. Optional: add a number between 0 and 1 for amount of people needed to play the game"""
        if not ctx.author.voice or not ctx.author.voice.channel:
            await ctx.send("You must be in a voice channel to use this command.")
            return
        
        if majority < 0 or majority > 1:
            await ctx.send("You must enter a number between 0 and 1")
            return
        
        channel_id = ctx.author.voice.channel.id
        # Get existing channel data
        existing_channels = await self.config.guild(ctx.guild).channels()

        # Add the new channel data
        existing_channels[channel_id] = {
            "name": ctx.author.voice.channel.name,
            "majority": majority, 
            "template": "X - Y"
        }

        # Save updated channel data
        await self.config.guild(ctx.guild).channels.set(existing_channels)
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
    async def changingchannels(self, ctx):
        """See all channels that change based on activity"""
        channelConfig = await self.config.guild(ctx.guild).channels()
        await ctx.send(channelConfig)

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
                    game_name = str(member.activity.name) 
                    games[game_name] = games.get(game_name, 0) + 1  # Tally the game

                    if games[game_name] > majority_number:
                        majority_name = game_name
                        majority_number = games[game_name]

        if majority_number / user_count > majority_percent:
            return majority_name
        else:
            return None  # Or you could return an empty string ""

    async def scan_one(self, ctx, channel, channels):

        channelConfig = channels[str(channel.id)]
        if channel:
            newTitle = channelConfig.get("name")
            members_amount = len(channel.members)
            if members_amount > 0:
                ignoredStatus = await self.config.guild(ctx.guild).ignoredStatus()

                gameTitle = await self.majority(channel, channelConfig.get("majority"))

                if gameTitle not in ignoredStatus:
                    newTitle = channelConfig.get("template").replace("X", channelConfig.get("name")).replace("Y", gameTitle)
                    
            if channel.name != newTitle:
                await channel.edit(name=newTitle)

    @commands.Cog.listener(name='on_voice_state_update')
    async def on_voice_state_update(self, member, before, after):
        ctx = member
        channels = await self.config.guild(member.guild).channels()
        if not before.channel:
            if after.channel.id:
                if str(after.channel.id) in channels:
                    await self.scan_one(ctx, after.channel, channels)
        elif not after.channel:
            if before.channel.id:
                if str(before.channel.id) in channels:
                    await self.scan_one(ctx, before.channel, channels)
        else:
            if before.channel.id != after.channel.id:
                if before.channel.id:
                    if str(before.channel.id) in channels:
                        await self.scan_one(ctx, before.channel, channels)

                if after.channel.id:
                    if str(after.channel.id) in channels:
                        await self.scan_one(ctx, after.channel, channels)


    @commands.Cog.listener(name='on_presence_update')
    async def on_presence_update(self, before, after):
        ctx = after
        if after and after.voice and after.voice.channel:  
            channels = await self.config.guild(after.guild).channels()
            if str(after.channel.id) in channels:
                await self.scan_one(ctx, after.voice.channel, channels) 
