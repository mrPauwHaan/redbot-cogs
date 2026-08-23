import importlib
from redbot.core.bot import Red
from . import statbot_api, usercard, view

# Forceer reload van alle onderliggende modules bij [p]reload
importlib.reload(statbot_api)
importlib.reload(view)
importlib.reload(usercard)

from .usercard import usercard as UsercardCog


async def setup(bot: Red) -> None:
    await bot.add_cog(UsercardCog(bot))