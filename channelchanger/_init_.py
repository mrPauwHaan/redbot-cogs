from .channelchanger import ChannelChanger

async def setup(bot: Red) -> None:
	await bot.add_cog(ChannelChanger())
