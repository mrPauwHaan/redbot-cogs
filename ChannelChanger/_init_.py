from .channelchanger import ChannelChanger


def setup(bot):
    bot.add_cog(ChannelChanger())
