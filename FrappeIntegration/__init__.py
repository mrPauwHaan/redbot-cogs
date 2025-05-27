from .frappe import Frappe
from redbot.core.bot import Red

async def setup(bot: Red) -> None:
	await bot.add_cog(Frappe(bot))