import discord
import re # Import regex module
from discord.ext import commands
import asyncio
from redbot.core.bot import Red
from redbot.core import Config


# Regex to find a channel ID within a mention format like <#123456789012345678>
# Redbot's converters handle this automatically, but we are manually parsing here
# to handle the case where the channel doesn't exist and the converter fails.
CHANNEL_MENTION_REGEX = re.compile(r"<#(\d+)>")


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

    @commands.Cog.listener()
    async def on_ready(self):
        print(f'Logged in as {self.bot.user} (ID: {self.bot.user.id})')
        print('------')
        # Consider adding a startup task here later if needed, e.g., to clean up deleted channels from config

    @commands.command()
    @commands.has_permissions(manage_channels=True)
    async def addvc(self, ctx: commands.Context, channel: discord.VoiceChannel = None, majority: float = 0.5):
        """Adds a voice channel to the watchlist.
        Optionally provide a channel ID/mention. Defaults to your current VC.
        Optional: add a number between 0 and 1 for amount of people needed to play the game.
        """
        target_channel = channel

        if target_channel is None:
            if ctx.author.voice and ctx.author.voice.channel:
                target_channel = ctx.author.voice.channel
            else:
                await ctx.send("You must be in a voice channel or provide a channel ID/mention.")
                return

        if not isinstance(target_channel, discord.VoiceChannel):
            # This shouldn't happen if the converter works, but is a safeguard
            await ctx.send("The provided ID/mention does not point to a valid voice channel in this guild.")
            return

        # Ensure the bot has permission to manage this channel
        if not target_channel.guild.me.guild_permissions.manage_channels:
             await ctx.send(f"I do not have the `Manage Channels` permission in this guild to rename `{target_channel.name}`.")
             return
        if not target_channel.permissions_for(target_channel.guild.me).manage_channels:
             await ctx.send(f"I do not have the `Manage Channels` permission for the channel `{target_channel.name}`.")
             return


        if not 0 <= majority <= 1:
            await ctx.send("You must enter a number between 0 and 1 for the majority threshold.")
            return

        channel_id_str = str(target_channel.id) # Use string ID consistently

        existing_channels = await self.config.guild(ctx.guild).channels()

        # Store the original name if adding for the first time, or keep existing name if updating
        original_name = existing_channels.get(channel_id_str, {}).get("name", target_channel.name)


        if channel_id_str in existing_channels:
             await ctx.send(f"`{target_channel.name}` is already being watched. Updating settings.")

        existing_channels[channel_id_str] = {
            "name": original_name,
            "majority": majority,
            "template": existing_channels.get(channel_id_str, {}).get("template", "X - Y")
        }

        await self.config.guild(ctx.guild).channels.set(existing_channels)
        await ctx.send(f"Successfully added `{target_channel.name}` to my list with majority threshold {majority:.0%}.")


    @commands.command()
    @commands.has_permissions(manage_channels=True)
    async def removevc(self, ctx: commands.Context, *, channel_input: str = None): # Use *, to capture potentially multi-word input if needed, though ID/mention is expected
        """Removes a voice channel from the watchlist.
        Provide channel ID or mention. Defaults to your current VC.
        Allows removing channels even if they have been deleted.
        """
        target_id_str = None
        channel_display_name = None # Name to show in feedback messages

        # --- Determine target_id_str from input or current VC ---
        if channel_input:
            # Try parsing as a raw ID (string of digits)
            if channel_input.isdigit():
                target_id_str = channel_input
                channel_display_name = f"ID `{target_id_str}`" # Start with ID for feedback

            # Try parsing as a channel mention <#ID>
            if target_id_str is None: # Only try mention if raw ID didn't match
                match = CHANNEL_MENTION_REGEX.match(channel_input)
                if match:
                    target_id_str = match.group(1) # Extract ID string
                    channel_display_name = f"Mention `{channel_input}` (ID `{target_id_str}`)" # Use mention for feedback

            # If an ID string was found from input (either digit or mention)
            if target_id_str:
                 # Try to get the channel object just for getting its *current* name if it exists
                 channel_obj = ctx.guild.get_channel(int(target_id_str))
                 if channel_obj:
                      channel_display_name = f"`{channel_obj.name}` (ID `{target_id_str}`)" # Use actual name + ID if found
                 # else: keep the initial display name (ID or mention format)
            else:
                 # Input was provided but didn't look like an ID or mention
                 await ctx.send("Invalid input format. Please provide a channel ID (e.g., `123456789012345678`) or mention (e.g., `#voice-chat`).")
                 return

        # If no input was provided, try author's current VC
        if target_id_str is None:
            if ctx.author.voice and ctx.author.voice.channel:
                target_channel = ctx.author.voice.channel
                target_id_str = str(target_channel.id)
                channel_display_name = f"`{target_channel.name}` (your current VC)" # Use current channel's name for display
            else:
                # If no input and not in VC
                await ctx.send("You must be in a voice channel or provide a channel ID/mention to remove.")
                return
        # --- End Determine target_id_str ---


        # Now we have a target_id_str and a channel_display_name for feedback

        # Get existing channel data using the determined string ID
        existing_channels = await self.config.guild(ctx.guild).channels()

        if target_id_str in existing_channels:
            # Use the stored name if available for better feedback, fallback to display name if stored name missing
            stored_name = existing_channels.get(target_id_str, {}).get("name")
            feedback_name = f"`{stored_name}`" if stored_name else channel_display_name

            del existing_channels[target_id_str] # Remove the channel using string ID
            await self.config.guild(ctx.guild).channels.set(existing_channels) # Save changes
            await ctx.send(f"Successfully removed voice channel {feedback_name} from my watchlist.") # Use feedback name

        else:
            # If not found in config, use the display name determined earlier
            await ctx.send(f"Voice channel {channel_display_name} was not found in my watchlist.")


    # --- Unimplemented Commands (Placeholders) ---

    @commands.command()
    @commands.has_permissions(manage_channels=True)
    async def setmajority(self, ctx: commands.Context, majority: float, channel: discord.VoiceChannel = None):
        """Set the percentage needed for a game to show (default=0.5) for a channel (WIP).
        Optionally provide a channel ID/mention. Defaults to your current VC.
        """
        # Use the converter approach as this requires a *live* channel object
        target_channel = channel
        if target_channel is None:
             if ctx.author.voice and ctx.author.voice.channel:
                  target_channel = ctx.author.voice.channel
             else:
                  await ctx.send("You must be in a voice channel or provide a channel ID/mention.")
                  return

        if not isinstance(target_channel, discord.VoiceChannel):
             await ctx.send("The provided ID/mention does not point to a valid voice channel in this guild.")
             return
        
        if not 0 <= majority <= 1:
            await ctx.send("You must enter a number between 0 and 1 for the majority threshold.")
            return

        channel_id_str = str(target_channel.id)
        existing_channels = await self.config.guild(ctx.guild).channels()

        if channel_id_str in existing_channels:
            existing_channels[channel_id_str]["majority"] = majority
            await self.config.guild(ctx.guild).channels.set(existing_channels)
            await ctx.send(f"Set the majority threshold for `{target_channel.name}` to {majority:.0%}.")
        else:
            await ctx.send(f"`{target_channel.name}` is not currently being watched. Use `{ctx.clean_prefix}addvc` first.")


    @commands.command()
    @commands.has_permissions(manage_channels=True)
    async def settemplate(self, ctx: commands.Context, template: str, channel: discord.VoiceChannel = None):
        """Set the template for changing voice channels (X=original name, Y=game) (WIP).
        The template is required as the first argument.
        Optionally provide a channel ID/mention as the last argument. Defaults to your current VC.
        """
        # Use the converter approach as this requires a *live* channel object
        target_channel = channel

        if target_channel is None:
             if ctx.author.voice and ctx.author.voice.channel:
                  target_channel = ctx.author.voice.channel
             else:
                  await ctx.send("You must be in a voice channel or provide a channel ID/mention.")
                  return

        if not isinstance(target_channel, discord.VoiceChannel):
             await ctx.send("The provided ID/mention does not point to a valid voice channel in this guild.")
             return

        channel_id_str = str(target_channel.id)
        existing_channels = await self.config.guild(ctx.guild).channels()

        if channel_id_str in existing_channels:
            existing_channels[channel_id_str]["template"] = template
            await self.config.guild(ctx.guild).channels.set(existing_channels)
            await ctx.send(f"Set the name template for `{target_channel.name}` to `{template}`.")
        else:
            await ctx.send(f"`{target_channel.name}` is not currently being watched. Use `{ctx.clean_prefix}addvc` first.")


    # --- Command to View Watched Channels ---

    @commands.command()
    @commands.has_permissions(manage_channels=True)
    async def changingchannels(self, ctx: commands.Context):
        """See all channels that change based on activity."""
        channel_configs = await self.config.guild(