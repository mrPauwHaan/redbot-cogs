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
            "channels": {}, # Channel ID (str) -> {"name": str, "majority": float, "template": str}
            "ignoredStatus": ["Spotify", "Custom Status", "Medal"],
            "global_mode": False,   # Nieuw: Schakelaar om alles te scannen
            "blacklist": []         # Nieuw: Lijst met genegeerde Channel ID's
        }
        self.config.register_guild(**default_guild)

    # --- Commands ---

    @commands.group()
    @commands.has_permissions(manage_channels=True)
    async def ccset(self, ctx: commands.Context):
        """Beheer instellingen voor ChannelChanger."""
        pass

    @ccset.command(name="global")
    async def ccset_global(self, ctx: commands.Context):
        """Wissel tussen alleen specifieke kanalen of ALLE kanalen scannen."""
        current_mode = await self.config.guild(ctx.guild).global_mode()
        new_mode = not current_mode
        await self.config.guild(ctx.guild).global_mode.set(new_mode)
        
        status = "AAN (Scan alle kanalen)" if new_mode else "UIT (Scan alleen toegevoegde kanalen)"
        await ctx.send(f"Global Mode staat nu **{status}**.")

    @ccset.command(name="ignore")
    async def ccset_ignore(self, ctx: commands.Context, channel: discord.VoiceChannel):
        """Voeg een kanaal toe aan de uitzonderingen (wordt niet aangepast)."""
        async with self.config.guild(ctx.guild).blacklist() as blacklist:
            if channel.id in blacklist:
                await ctx.send(f"`{channel.name}` staat al op de negeerlijst.")
            else:
                blacklist.append(channel.id)
                await ctx.send(f"`{channel.name}` wordt nu genegeerd.")

    @ccset.command(name="unignore")
    async def ccset_unignore(self, ctx: commands.Context, channel: discord.VoiceChannel):
        """Verwijder een kanaal van de uitzonderingen."""
        async with self.config.guild(ctx.guild).blacklist() as blacklist:
            if channel.id in blacklist:
                blacklist.remove(channel.id)
                await ctx.send(f"`{channel.name}` wordt weer meegenomen in de scans.")
            else:
                await ctx.send(f"`{channel.name}` stond niet op de negeerlijst.")

    @commands.command()
    @commands.has_permissions(manage_channels=True)
    async def addvc(self, ctx: commands.Context, channel: discord.VoiceChannel = None, majority: float = 0.5):
        """Voeg specifieke instellingen toe voor een kanaal (overschrijft global defaults)."""
        target_channel = channel or ctx.author.voice.channel if ctx.author.voice else None
        
        if not target_channel or not isinstance(target_channel, discord.VoiceChannel):
            await ctx.send("Geef een geldig spraakkanaal op of ga in een kanaal zitten.")
            return
            
        if target_channel.guild != ctx.guild:
             await ctx.send("Dat kanaal is niet in deze server.")
             return

        if not 0 <= majority <= 1:
            await ctx.send("Kies een nummer tussen 0 en 1.")
            return

        existing_channels = await self.config.guild(ctx.guild).channels()
        existing_channels[str(target_channel.id)] = {
            "name": target_channel.name,
            "majority": majority,
            "template": "X - Y"
        }
        
        await self.config.guild(ctx.guild).channels.set(existing_channels)
        await ctx.send(f"`{target_channel.name}` succesvol ingesteld met drempelwaarde {majority:.0%}.")

    @commands.command()
    @commands.has_permissions(manage_channels=True)
    async def removevc(self, ctx: commands.Context, channelid: str = None):
        """Verwijder specifieke instellingen voor een kanaal."""
        if channelid is None and ctx.author.voice:
             channelid = str(ctx.author.voice.channel.id)

        existing_channels = await self.config.guild(ctx.guild).channels()

        if channelid in existing_channels:
            del existing_channels[channelid]
            await self.config.guild(ctx.guild).channels.set(existing_channels)
            await ctx.send(f"Specifieke instellingen voor `{channelid}` verwijderd.")
        else:
            await ctx.send(f"`{channelid}` had geen specifieke instellingen.")

    # --- Logic ---

    async def get_majority_game(self, channel: discord.VoiceChannel, majority_percent: float, ignored_statuses: list):
        """Bepaalt de meerderheidsgame."""
        games = {}
        active_members = [m for m in channel.members if not m.bot]
        user_count = len(active_members)

        if user_count == 0:
            return None

        for member in active_members:
            for activity in member.activities:
                if isinstance(activity, discord.Activity) and activity.type == discord.ActivityType.playing and activity.name not in ignored_statuses:
                    games[activity.name] = games.get(activity.name, 0) + 1
                    break 

        if not games:
             return None

        majority_name = max(games, key=games.get)
        count = games[majority_name]

        if count / user_count > majority_percent:
            return majority_name
        return None

    async def scan_one(self, channel: discord.VoiceChannel):
        """Scant één kanaal en update de status."""
        guild_config = await self.config.guild(channel.guild).get_raw()
        
        # 1. Check Configuraties
        global_mode = guild_config.get("global_mode", False)
        blacklist = guild_config.get("blacklist", [])
        specific_channels = guild_config.get("channels", {})
        ignored_statuses = guild_config.get("ignoredStatus", ["Spotify", "Custom Status", "Medal"])

        channel_id_str = str(channel.id)
        
        # Bepaal of we dit kanaal moeten scannen
        channel_config = specific_channels.get(channel_id_str)
        
        should_scan = False
        if channel_config:
            should_scan = True # Altijd scannen als hij specifiek is toegevoegd
        elif global_mode:
            if channel.id not in blacklist:
                should_scan = True # Scannen als global aanstaat en niet op blacklist
        
        if not should_scan:
            return

        # 2. Bepaal instellingen (Specifiek of Default)
        if channel_config:
            majority_threshold = channel_config.get("majority", 0.5)
        else:
            majority_threshold = 0.5 # Default voor global mode

        # 3. Logica uitvoeren
        game_title = await self.get_majority_game(channel, majority_threshold, ignored_statuses)

        # LET OP: Jouw originele code gebruikte channel.edit(status=...)
        # Dit werkt alleen als je Discord library/versie dit ondersteunt (Voice Status)
        
        try:
            # Check permissions
            if not channel.permissions_for(channel.guild.me).manage_channels:
                return

            # Als er een game is, zet status. Zo niet, clear status (of doe niets)
            if game_title:
                await channel.edit(status=game_title)
                # print(f"Changed status for {channel.name} to {game_title}")
            else:
                # Optioneel: Status verwijderen als er geen game meer is?
                # await channel.edit(status="") 
                pass 

        except discord.Forbidden:
            print(f"Bot lacks permissions for {channel.name}")
        except Exception as e:
            # Vang fouten af, bijv. als channel.edit(status) niet bestaat
            print(f"Error updating channel {channel.id}: {e}")

    # --- Listeners ---

    @commands.Cog.listener(name='on_voice_state_update')
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if not member.guild: return
        
        # Als iemand een kanaal joint of verlaat, scan dat kanaal
        if after.channel:
            await self.scan_one(after.channel)
        if before.channel and before.channel != after.channel:
            await self.scan_one(before.channel)

    @commands.Cog.listener(name='on_presence_update')
    async def on_presence_update(self, before: discord.Member, after: discord.Member):
        if not after.guild or not after.voice or not after.voice.channel:
            return
        await self.scan_one(after.voice.channel)