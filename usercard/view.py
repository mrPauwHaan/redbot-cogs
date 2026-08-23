from redbot.core import commands
import discord


class usercardView(discord.ui.View):
    def __init__(
        self,
        cog: commands.Cog,
        _object: discord.Member,
    ) -> None:
        super().__init__(timeout=60 * 60)
        self.cog: commands.Cog = cog
        self.ctx: commands.Context = None
        self._object: discord.Member = _object
        self._message: discord.Message = None

        # Link knop om direct lid te worden
        self.add_item(
            discord.ui.Button(
                label="Word Lid",
                url="https://www.shadowzone.nl/shadowzoner-worden",
                style=discord.ButtonStyle.link,
                emoji="🌐",
            )
        )

    async def start(
        self,
        ctx: commands.Context,
        command: str,
    ) -> discord.Message:
        self.ctx = ctx

        if command == "card":
            file = await self.cog.generate_image(self._object, to_file=True)
            if file:
                self._message = await self.ctx.send(file=file, view=self)
            else:
                self._message = await self.ctx.send("Kon profiel niet laden.")
        elif command == "wrapped":
            file = await self.cog.generate_wrapped_image(self._object, to_file=True)
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
        file: discord.File = await self.cog.generate_wrapped_image(self._object, to_file=True)
        await self._message.edit(content="", attachments=[file])

    @discord.ui.button(emoji="🆔", custom_id="id_page", style=discord.ButtonStyle.secondary)
    async def id_page(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.defer(thinking=False)
        await self._message.edit(content=str(self._object.id), attachments=[])