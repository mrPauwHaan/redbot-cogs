from redbot.core import commands  # isort:skip
import discord  # isort:skip

import asyncio


class GuildStatsView(discord.ui.View):
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
        self._ready: asyncio.Event = asyncio.Event()

    async def start(self, ctx: commands.Context) -> discord.Message:
        self.ctx: commands.Context = ctx
        file: discord.File = await self.cog.generate_image(
            self._object,
            to_file=True,
        )
        if file:
            self._message: discord.Message = await self.ctx.send(file=file, view=self)
        else:
            self._message: discord.Message = await self.ctx.send('Persoon niet in database gevonden')
        self.cog.views[self._message] = self
        await self._ready.wait()
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
            child: discord.ui.Item
            if hasattr(child, "disabled") and not (
                isinstance(child, discord.ui.Button) and child.style == discord.ButtonStyle.url
            ):
                child.disabled = True
        try:
            await self._message.edit(view=self)
        except discord.HTTPException:
            pass
        self._ready.set()

    @discord.ui.button(emoji="🔄", custom_id="reload_page", style=discord.ButtonStyle.secondary)
    async def reload_page(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.defer(thinking=False)  # thinking=True
        file: discord.File = await self.cog.generate_image(
            self._object,
            to_file=True,
        )
        # try:
        #     await interaction.delete_original_response()
        # except discord.HTTPException:
        #     pass
        await self._message.edit(attachments=[file])

    @discord.ui.button(style=discord.ButtonStyle.danger, emoji="✖️", custom_id="close_page")
    async def close_page(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        try:
            await interaction.response.defer()
        except discord.errors.NotFound:
            pass
        self.stop()
        if self._message is None:
            return None
        try:
            await self._message.delete()
            self._ready.set()
        except discord.NotFound:  # Already deleted.
            return True
        except discord.HTTPException:
            return False
        else:
            return True