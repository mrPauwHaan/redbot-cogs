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
            "ignoredStatus": ["Spotify", "Custom Status", "Medal"]
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
    async def removevc(self, ctx: commands.Context, channelid: str = None):
        """Removes a voice channel from the watchlist based on provided ID.
        """

        # If no channel argument was provided, try using the author's current VC
        if channelid is None:
            if ctx.author.voice and ctx.author.voice.channel:
                channelid = str(ctx.author.voice.channel.id)
            else:
                await ctx.send("You must be in a voice channel or provide a channel ID/mention.")
                return

        # Get existing channel data
        existing_channels = await self.config.guild(ctx.guild).channels()


        if channelid in existing_channels:
            del existing_channels[channelid] # Remove the channel
            await self.config.guild(ctx.guild).channels.set(existing_channels) # Save changes
            await ctx.send(f"Successfully removed `{channelid}` from my list.")
        else:
            await ctx.send(f"`{channelid}` is not currently being watched.")

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
        if majority_number / user_count > majority_percent:
            return majority_name
        else:
            return None # No game reached the required majority


   # --- Helper function to scan and update a single channel ---
    # Reverted docstring as we are changing the name
    async def scan_one(self, channel: discord.VoiceChannel, channel_configs: dict):
        """Scans a single voice channel and updates its name if needed."""

        # Get guild config using the channel object
        guild_config = await self.config.guild(channel.guild).get_raw()
        # Use .get() with default, simplified as discussed
        ignored_statuses = guild_config.get("ignoredStatus", ["Spotify", "Custom Status", "Medal"])


        # Get specific channel config using string ID
        channel_id_str = str(channel.id)
        channel_config = channel_configs.get(channel_id_str)

        if not channel_config:
             print(f"Scan requested for channel {channel.id} but not found in config.")
             return


        # Use stored name (needed for template X) or current if missing
        original_name = channel_config.get("name", channel.name)
        majority_threshold = channel_config.get("majority", 0.5)
        template = channel_config.get("template", "X - Y")


        members_amount = len(channel.members)

        # Determine the new name string
        # Default title is the original name
        new_title = original_name # Reverted variable name and default


        if members_amount > 0:
            # Get the majority game, filtering ignored statuses
            game_title = await self.get_majority_game(channel, majority_threshold, ignored_statuses)

            if game_title: # If a game met the majority threshold and was not ignored
                 # Construct the new title string using the template
                 template_to_use = channel_config.get("template", "X - Y")
                 # Replace X with original name, Y with game title
                 new_title = template_to_use.replace("X", original_name).replace("Y", game_title)
            # If no majority game is found, new_title remains the original_name, which is the desired fallback.


        # Check against Discord's channel name limit (usually 100 characters)
        if len(new_title) > 100:
            new_title = new_title[:97] + "..." # Truncate and add ellipsis


        # Update the channel name only if it's different and bot has permission
        # Check against channel.name
        if channel.name != new_title:
            # Check bot's permissions for this specific channel
            bot_member = channel.guild.me
            # Changing name requires manage_channels permission
            if not channel.permissions_for(bot_member).manage_channels:
                print(f"Bot lacks manage_channels permission for channel {channel.name} in guild {channel.guild.name}. Cannot change name.")
                # Consider adding a way to inform the guild owner about this missing permission.
                return # Exit scan_one if no permission

            try:
                # Discord has a rate limit for name changes (usually 2 changes per 10 minutes per channel)
                # Rapid changes might hit this. Consider adding cooldowns if needed.
                # (Not implemented here, but be aware)
                # await channel.edit(name=new_title) # *** CHANGE IS HERE ***
                await channel.edit(status=game_title)
                print(f"Changed channel `{channel.name}` (ID: {channel.id}) name to `{new_title}`")
            except discord.Forbidden:
                # This should ideally be caught by the permission check above, but included as a fallback
                print(f"Bot lacks permissions to change name for channel {channel.name} in guild {channel.guild.name}.")
            except discord.HTTPException as e:
                # This might catch rate limits or other API errors
                print(f"Failed to change channel name for {channel.name} (ID: {channel.id}): {e}")
            except Exception as e:
                # Catch any other unexpected errors
                print(f"An unexpected error occurred changing name for channel {channel.name} (ID: {channel.id}): {e}")

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