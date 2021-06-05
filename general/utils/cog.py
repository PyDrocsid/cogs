import itertools
from random import random
from typing import Optional

from discord import Embed
from discord.ext import commands
from discord.ext.commands import Context, CommandError, max_concurrency, guild_only
from discord.utils import snowflake_time

from PyDrocsid.async_thread import run_in_thread
from PyDrocsid.cog import Cog
from PyDrocsid.command import reply
from PyDrocsid.converter import Color
from PyDrocsid.translations import t
from PyDrocsid.util import measure_latency
from .colors import Colors
from .permissions import UtilsPermission
from ...contributor import Contributor

tg = t.g
t = t.utils


def generate_color(colors: list[tuple[float, float, float]], n: int, a: float) -> Optional[tuple[float, float, float]]:
    for _ in range(10):
        guess = [random() for _ in range(3)]  # noqa: S311
        last = None
        for _ in range(n):
            if tuple(guess) in colors:
                break

            new_guess = guess.copy()
            for c in colors:
                for i in range(3):
                    new_guess[i] += 2 * (guess[i] - c[i]) * (sum((p - q) ** 2 for p, q in zip(guess, c)) ** -2) * a
            guess = [min(max(x, 0), 1) for x in new_guess]

            if last == guess:
                return guess[0], guess[1], guess[2]
            last = guess.copy()

        else:
            return guess[0], guess[1], guess[2]

    return None


class UtilsCog(Cog, name="Utils"):
    CONTRIBUTORS = [Contributor.Defelo]

    @commands.command()
    async def ping(self, ctx: Context):
        """
        display bot latency
        """

        latency: Optional[float] = measure_latency()
        embed = Embed(title=t.pong, colour=Colors.ping)
        if latency is not None:
            embed.description = t.pong_latency(latency * 1000)
        await reply(ctx, embed=embed)

    @commands.command(aliases=["sf", "time"])
    async def snowflake(self, ctx: Context, arg: int):
        """
        display snowflake timestamp
        """

        if arg < 0:
            raise CommandError(t.invalid_snowflake)

        try:
            await reply(ctx, snowflake_time(arg).strftime("%d.%m.%Y %H:%M:%S"))
        except (OverflowError, ValueError, OSError):
            raise CommandError(t.invalid_snowflake)

    @commands.command(aliases=["rc"])
    @UtilsPermission.suggest_role_color.check
    @max_concurrency(1)
    @guild_only()
    async def suggest_role_color(self, ctx: Context, *avoid: Color):
        """Suggest a new role color based on the colors of all existing roles"""

        avoid: tuple[int]

        colors = [hex(color)[2:].zfill(6) for role in ctx.guild.roles if (color := role.color.value)]
        colors += [hex(c)[2:].zfill(6) for c in avoid]
        colors = [[int(x, 16) / 255 for x in [c[:2], c[2:4], c[4:]]] for c in colors]
        colors += itertools.product(range(2), repeat=3)

        color = await run_in_thread(generate_color, colors, 1000, 0.005)
        if color is None:
            raise CommandError(t.could_not_generate_color)

        color = "%02X" * 3 % tuple([round(float(c) * 255) for c in color])

        embed = Embed(title="#" + color, color=int(color, 16))
        embed.set_image(url=f"https://singlecolorimage.com/get/{color}/400x100")
        await reply(ctx, embed=embed)
