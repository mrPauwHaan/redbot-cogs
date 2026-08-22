from .usercard import usercard

async def setup(bot):
    await bot.add_cog(usercard(bot))