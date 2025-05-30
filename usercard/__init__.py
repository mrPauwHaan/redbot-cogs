from redbot.core import errors  # isort:skip
import importlib
import sys

try:
    import AAA3A_utils
except ModuleNotFoundError:
    raise errors.CogLoadError(
        "The needed utils to run the cog were not found."
    )
modules = sorted(
    [module for module in sys.modules if module.split(".")[0] == "AAA3A_utils"], reverse=True
)
for module in modules:
    try:
        importlib.reload(sys.modules[module])
    except ModuleNotFoundError:
        pass
del AAA3A_utils

from redbot.core.bot import Red  # isort:skip
from redbot.core.utils import get_end_user_data_statement

from .usercard import usercard

__red_end_user_data_statement__ = get_end_user_data_statement(file=__file__)


async def setup(bot: Red) -> None:
    cog = usercard(bot)
    await bot.add_cog(cog)
