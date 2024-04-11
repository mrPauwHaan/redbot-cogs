from .channelchanger import ChannelChanger

async def setup(bot):
	await bot.add_cog(ChannelChanger())
