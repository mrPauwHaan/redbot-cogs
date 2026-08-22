import io
import discord
from .statbot_api import StatbotClient


class UserCardView(discord.ui.View):
    def __init__(
        self, cog, member: discord.Member, author: discord.Member, initial_lid_bytes: bytes
    ):
        super().__init__(timeout=120)
        self.cog = cog
        self.member = member
        self.author = author
        self.cached_files: dict[str, bytes] = {"lid": initial_lid_bytes}

    @discord.ui.button(label="Lid", style=discord.ButtonStyle.primary, custom_id="btn_lid")
    async def lid_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        if "lid" not in self.cached_files:
            buf = await self.cog.render_lid_card(self.member)
            self.cached_files["lid"] = buf.getvalue()

        file = discord.File(io.BytesIO(self.cached_files["lid"]), filename="lid_card.png")
        await interaction.edit_original_response(attachments=[file], view=self)

    @discord.ui.button(label="ID", style=discord.ButtonStyle.secondary, custom_id="btn_id")
    async def id_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        if "id" not in self.cached_files:
            buf = await self.cog.render_id_card(self.member)
            self.cached_files["id"] = buf.getvalue()

        file = discord.File(io.BytesIO(self.cached_files["id"]), filename="id_card.png")
        await interaction.edit_original_response(attachments=[file], view=self)

    @discord.ui.button(label="Stats", style=discord.ButtonStyle.secondary, custom_id="btn_stats")
    async def stats_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        if "stats" not in self.cached_files:
            api_tokens = await self.cog.bot.get_shared_api_tokens("statbot")
            api_key = api_tokens.get("api_key", "")

            client = StatbotClient(api_key=api_key)
            stats = await client.get_user_voice_stats(
                interaction.guild_id, self.member.id, days=30
            )
            await client.close()

            buf = await self.cog.render_stats_card(self.member, stats)
            self.cached_files["stats"] = buf.getvalue()

        file = discord.File(io.BytesIO(self.cached_files["stats"]), filename="stats_card.png")
        await interaction.edit_original_response(attachments=[file], view=self)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(
                "Alleen degene die het commando heeft aangeroepen kan van weergave wisselen.",
                ephemeral=True,
            )
            return False
        return True