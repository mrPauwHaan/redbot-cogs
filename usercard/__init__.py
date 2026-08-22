from .usercard import UserCard

async def setup(bot):
    await bot.add_cog(UserCard(bot))