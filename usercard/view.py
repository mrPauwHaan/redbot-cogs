from redbot.core import commands
import discord
import typing
from datetime import datetime


class usercardView(discord.ui.View):
    def __init__(
        self,
        cog: commands.Cog,
        _object: discord.Member,
        year: typing.Optional[int] = None,
    ) -> None:
        super().__init__(timeout=60 * 60)
        self.cog: commands.Cog = cog
        self.ctx: commands.Context = None
        self._object: discord.Member = _object
        self._message: discord.Message = None
        # Standaard het vorige, volledig afgeronde kalenderjaar
        self.year: int = year or (datetime.now().year - 1)

    async def start(
        self,
        ctx: commands.Context,
        command: str,
        year: typing.Optional[int] = None,
    ) -> discord.Message:
        self.ctx = ctx
        if year:
            self.year = year

        if command == "card":
            file = await self.cog.generate_image(self._object, to_file=True)
            if file:
                self._message = await self.ctx.send(file=file, view=self)
            else:
                self._message = await self.ctx.send("Gebruiker niet gevonden in database")
        elif command == "wrapped":
            file = await self.cog.generate_wrapped_image(self._object, year=self.year, to_file=True)
            self._message = await self.ctx.send(file=file, view=self)
        elif command == "id":
            file = await self.cog.generate_image(self._object, to_file=True)
            if file:
                self._message = await self.ctx.send(str(self._object.id), view=self)
            else:
                self._message = await self.ctx.send(str(self._object.id))

        return self._message

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id not in [self.ctx.author.id] + list(self.ctx.bot.owner_ids):
            await interaction.response.send_message(
                "Je kunt deze interactie niet uitvoeren", ephemeral=True
            )
            return False
        return True

    async def on_timeout(self) -> None:
        for child in self.children:
            if hasattr(child, "disabled") and not (
                isinstance(child, discord.ui.Button) and child.style == discord.ButtonStyle.url
            ):
                child.disabled = True
        try:
            await self._message.edit(view=self)
        except discord.HTTPException:
            pass

    @discord.ui.button(emoji="👤", custom_id="reload_page", style=discord.ButtonStyle.secondary)
    async def reload_page(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.defer(thinking=False)
        file = await self.cog.generate_image(self._object, to_file=True)
        if file:
            await self._message.edit(content="", attachments=[file])
        else:
            await self._message.edit(content="Gebruiker niet gevonden in database", attachments=[])

    @discord.ui.button(emoji="📊", custom_id="stats_page", style=discord.ButtonStyle.secondary)
    async def stats_page(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.defer(thinking=False)
        file: discord.File = await self.cog.generate_stats_image(self._object, to_file=True)
        await self._message.edit(content="", attachments=[file])

    @discord.ui.button(emoji="🎁", custom_id="wrapped_page", style=discord.ButtonStyle.secondary)
    async def wrapped_page(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.defer(thinking=False)
        file: discord.File = await self.cog.generate_wrapped_image(self._object, year=self.year, to_file=True)
        await self._message.edit(content="", attachments=[file])

    @discord.ui.button(emoji="🆔", custom_id="id_page", style=discord.ButtonStyle.secondary)
    async def id_page(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.defer(thinking=False)
        await self._message.edit(content=str(self._object.id), attachments=[])