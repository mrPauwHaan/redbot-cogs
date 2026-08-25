from redbot.core.bot import Red
from .szg_statbot import SZGStatbot


async def setup(bot: Red) -> None:
    await bot.add_cog(SZGStatbot(bot))