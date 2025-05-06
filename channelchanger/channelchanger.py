import discord
from discord.ext import commands
import asyncio
from redbot.core.bot import Red
from redbot.core import commands # Redundant import, already imported above
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
            "channels": {}, # Channel ID (str) -> {"name": str, "majority": float, "template": str}
            "ignoredStatus": ["Spotify", "Custom Status"]
        }
        self.config.register_guild(**default_guild)

    @commands.command()
    @commands.has_permissions(manage_channels=True)
    async def addvc(self, ctx: commands.Context, channel: discord.VoiceChannel = None, majority: float = 0.5):
        """Adds a voice channel to the watchlist.
        Optionally provide a channel ID/mention. Defaults to your current VC.
        Optional: add a number between 0 and 1 for amount of people needed to play the game (only if providing channel ID/mention).
        """
        target_channel = channel # Start with the provided channel

        # If no channel argument was provided, try using the author's current VC
        if target_channel is None:
            if ctx.author.voice and ctx.author.voice.channel:
                target_channel = ctx.author.voice.channel
            else:
                await ctx.send("You must be in a voice channel or provide a channel ID/mention.")
                return

        # Ensure the resolved target is actually a voice channel
        if not isinstance(target_channel, discord.VoiceChannel):
            await ctx.send("The provided ID/mention does not point to a valid voice channel in this guild.")
            return
            
        # Ensure the bot can see the channel (discord.py converter usually handles this, but double check)
        if target_channel.guild != ctx.guild:
             await ctx.send("That channel is not in this guild.")
             return

        if not 0 <= majority <= 1:
            await ctx.send("You must enter a number between 0 and 1 for the majority threshold.")
            return

        channel_id_str = str(target_channel.id) # Use string ID

        # Get existing channel data
        existing_channels = await self.config.guild(ctx.guild).channels()

        if channel_id_str in existing_channels:
             await ctx.send(f"`{target_channel.name}` is already being watched. Updating settings.")

        # Add/Update the channel data with string ID
        existing_channels[channel_id_str] = {
            "name": target_channel.name, # Store original name
            "majority": majority,
            "template": "X - Y" # Default template
        }

        # Save updated channel data
        await self.config.guild(ctx.guild).channels.set(existing_channels)
        await ctx.send(f"Successfully added `{target_channel.name}` to my list with majority threshold {majority:.0%}.")

    @commands.command()
    @commands.has_permissions(manage_channels=True)
    async def removevc(self, ctx: commands.Context, channel: discord.VoiceChannel = None):
        """Removes a voice channel from the watchlist.
        Optionally provide a channel ID/mention. Defaults to your current VC.
        """
        target_channel = channel # Start with the provided channel

        # If no channel argument was provided, try using the author's current VC
        if target_channel is None:
            if ctx.author.voice and ctx.author.voice.channel:
                target_channel = ctx.author.voice.channel
            else:
                await ctx.send("You must be in a voice channel or provide a channel ID/mention.")
                return

        # Ensure the resolved target is actually a voice channel
        if not isinstance(target_channel, discord.VoiceChannel):
            await ctx.send("The provided ID/mention does not point to a valid voice channel in this guild.")
            return
            
        # Ensure the bot can see the channel
        if target_channel.guild != ctx.guild:
             await ctx.send("That channel is not in this guild.")
             return


        channel_id_str = str(target_channel.id) # Use string ID for lookup

        # Get existing channel data
        existing_channels = await self.config.guild(ctx.guild).channels()

        if channel_id_str in existing_channels:
            del existing_channels[channel_id_str] # Remove the channel
            await self.config.guild(ctx.guild).channels.set(existing_channels) # Save changes
            await ctx.send(f"Successfully removed `{target_channel.name}` from my list.")
        else:
            await ctx.send(f"`{target_channel.name}` is not currently being watched.")

    # --- Unimplemented Commands (Placeholders) ---

    @commands.command()
    @commands.has_permissions(manage_channels=True)
    async def setmajority(self, ctx, majority: float): # Renamed command
        """Set the percentage needed for a game to show (default=0.5) (WIP)."""
        # Implementation needed: Get channel (from author VC or argument), check majority value, update config, save config
        await ctx.send("Command not possible yet")

    @commands.command()
    @commands.has_permissions(manage_channels=True)
    async def settemplate(self, ctx, *, template: str): # Use * to capture rest of line
        """Set the template for changing voice channels (X=original name, Y=game) (WIP)."""
        # Implementation needed: Get channel (from author VC or argument), update config, save config
        await ctx.send("Command not possible yet")

    # --- Command to View Watched Channels ---

    @commands.command()
    @commands.has_permissions(manage_channels=True)
    async def changingchannels(self, ctx: commands.Context):
        """See all channels that change based on activity."""
        channel_configs = await self.config.guild(ctx.guild).channels()
        if not channel_configs:
            await ctx.send("No voice channels are currently being watched in this guild.")
            return

        message = "Watching the following voice channels:\n"
        for channel_id, config in channel_configs.items():
            # Attempt to fetch the channel by ID in case it was deleted
            channel = ctx.guild.get_channel(int(channel_id))
            channel_name = channel.name if channel else f"Unknown Channel (ID: {channel_id})"
            message += f"- `{channel_name}` (Majority: {config.get('majority', 0.5):.0%}, Template: `{config.get('template', 'X - Y')}`)\n"

        # Split message if too long
        if len(message) > 2000:
            await ctx.send("Too many channels to list. Check console or ask bot owner.") # Or paginate
        else:
            await ctx.send(message)


    # --- Helper function to determine majority game ---
    async def get_majority_game(self, channel: discord.VoiceChannel, majority_percent: float, ignored_statuses: list): # Renamed function
        """Determines the majority game being played in a voice channel."""
        games = {}
        user_count = 0
        
        # Filter members who are not bots and might have activities
        active_members = [m for m in channel.members if not m.bot]
        user_count = len(active_members)

        if user_count == 0:
            return None # No users, no game

        for member in active_members:
            # Iterate through all activities
            for activity in member.activities:
                # Check if it's a game activity and not in the ignored list
                if isinstance(activity, discord.Activity) and activity.type == discord.ActivityType.playing and activity.name not in ignored_statuses:
                    game_name = activity.name
                    games[game_name] = games.get(game_name, 0) + 1 # Tally the game
                    # Once a valid game is found for this member, move to the next member
                    break # Stop checking activities for this member once one game is found

        if not games:
             return None # No games being played by anyone

        # Find the game with the highest count
        majority_name = ""
        majority_number = 0
        for game, count in games.items():
            if count > majority_number:
                majority_number = count
                majority_name = game
            # If counts are equal, the first one encountered keeps the majority (arbitrary but consistent)


        # Check if the most played game meets the majority threshold
        if majority_number / user_count >= majority_percent: # Use >= for threshold
            return majority_name
        else:
            return None # No game reached the required majority


    # --- Helper function to scan and update a single channel ---
    async def scan_one(self, channel: discord.VoiceChannel, channel_configs: dict): # Removed ctx, takes channel object
        """Scans a single voice channel and updates its name if needed."""

        # Get guild config using the channel object
        guild_config = await self.config.guild(channel.guild).get_raw()
        ignored_statuses = guild_config.get("ignoredStatus", ["Spotify", "Custom Status"])

        # Get specific channel config using string ID
        channel_id_str = str(channel.id)
        channel_config = channel_configs.get(channel_id_str)

        if not channel_config:
             # This channel might have been removed from config but listener fired
             # Or it was never added. Should not happen if called correctly from listeners
             # but defensive check is good.
             print(f"Scan requested for channel {channel.id} but not found in config.")
             return


        original_name = channel_config.get("name", channel.name) # Use stored name or current if missing
        majority_threshold = channel_config.get("majority", 0.5)
        template = channel_config.get("template", "X - Y")


        members_amount = len(channel.members)

        # Default title is the original name
        new_title = original_name

        if members_amount > 0:
            # Get the majority game, filtering ignored statuses within the function
            game_title = await self.get_majority_game(channel, majority_threshold, ignored_statuses)

            if game_title: # If a game met the majority threshold and was not ignored
                # Construct the new title using the template
                # Ensure template variables are handled even if missing (though defaults are set)
                template_to_use = channel_config.get("template", "X - Y")
                new_title = template_to_use.replace("X", original_name).replace("Y", game_title)


        # Update the channel name only if it's different
        if channel.name != new_title:
            try:
                # Discord has a rate limit of 2 name changes per 10 minutes per channel
                # Rapid changes (e.g., users joining/leaving quickly, or changing games rapidly)
                # might hit this. Redbot handles some rate limits internally, but heavy use
                # might still cause issues. Consider adding a small delay or cooldown per channel
                # if rate limits become a problem.
                await channel.edit(name=new_title)
                print(f"Changed channel {channel.name} name to {new_title}")
            except discord.Forbidden:
                print(f"Bot lacks permissions to rename channel {channel.name} in guild {channel.guild.name}.")
            except discord.HTTPException as e:
                print(f"Failed to change channel name for {channel.name}: {e}")


    # --- Listeners ---

    @commands.Cog.listener(name='on_voice_state_update')
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        """Handles users joining, leaving, or moving voice channels."""
        guild = member.guild
        if not guild: # Should not happen but good practice
             return

        channel_configs = await self.config.guild(guild).channels()

        # User joined a channel or moved to a channel
        if after.channel and str(after.channel.id) in channel_configs:
            # Trigger scan for the channel they joined/moved to
            await self.scan_one(after.channel, channel_configs)

        # User left a channel or moved from a channel
        if before.channel and str(before.channel.id) in channel_configs and before.channel != after.channel:
            # Trigger scan for the channel they left
            await self.scan_one(before.channel, channel_configs)


    @commands.Cog.listener(name='on_presence_update')
    async def on_presence_update(self, before: discord.Member, after: discord.Member):
        """Handles users changing their activity (playing a game)."""
        guild = after.guild
        if not guild or not after.voice or not after.voice.channel:
            # Member is not in a voice channel we care about
            return

        channel = after.voice.channel
        channel_configs = await self.config.guild(guild).channels()

        if str(channel.id) in channel_configs:
            # Trigger scan for the channel the member is in
            await self.scan_one(channel, channel_configs)