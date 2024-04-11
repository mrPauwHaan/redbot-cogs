from .channelchanger import ChannelChanger
from redbot.core.bot import Red

async def setup(bot: Red) -> None:
	await bot.add_cog(ChannelChanger(bot))
