import itertools
from random import random
from typing import Optional, Union

from discord import Embed, User, Member
from discord.ext import commands
from discord.ext.commands import Context, CommandError, max_concurrency, guild_only
from discord.utils import snowflake_time

from PyDrocsid.async_thread import run_in_thread
from PyDrocsid.cog import Cog
from PyDrocsid.command import reply, docs
from PyDrocsid.converter import Color, UserMemberConverter
from PyDrocsid.translations import t
from PyDrocsid.util import measure_latency
from .colors import Colors
from .permissions import UtilsPermission
from ...contributor import Contributor

tg = t.g
t = t.utils


def generate_color(colors: list[tuple[float, float, float]], n: int, a: float) -> tuple[float, float, float]:
    guess = [random() for _ in range(3)]  # noqa: S311
    last = None
    for _ in range(n):
        new_guess = guess.copy()
        for i in range(3):
            mx = 0
            for c in colors:
                b = 10 ** (-3 - sum(x in (0, 1) for x in c))
                error = 1 / (b + sum((p - q) ** 2 for p, q in zip(guess, c)))
                if error > mx:
                    mx = error
                    new_guess[i] = guess[i] + (
                        2 * (guess[i] - c[i]) * ((b + sum((p - q) ** 2 for p, q in zip(guess, c))) ** -2) * a
                    )
        guess = [min(max(x, 0), 1) for x in new_guess]

        if last == guess:
            return guess[0], guess[1], guess[2]
        last = guess.copy()

    return guess[0], guess[1], guess[2]


class UtilsCog(Cog, name="Utils"):
    CONTRIBUTORS = [Contributor.Defelo]

    @commands.command()
    @docs(t.commands.ping)
    async def ping(self, ctx: Context):
        latency: Optional[float] = measure_latency()
        embed = Embed(title=t.pong, colour=Colors.Utils)
        if latency is not None:
            embed.description = t.pong_latency(latency * 1000)
        await reply(ctx, embed=embed)

    @commands.command(aliases=["sf", "time"])
    @docs(t.commands.snowflake)
    async def snowflake(self, ctx: Context, arg: int):
        if arg < 0:
            raise CommandError(t.invalid_snowflake)

        try:
            await reply(ctx, snowflake_time(arg).strftime("%d.%m.%Y %H:%M:%S"))
        except (OverflowError, ValueError, OSError):
            raise CommandError(t.invalid_snowflake)

    @commands.command(aliases=["enc"])
    @docs(t.commands.encode)
    async def encode(self, ctx: Context, *, user: UserMemberConverter):
        user: Union[User, Member]

        embed = Embed(color=Colors.Utils)
        embed.set_author(name=str(user), icon_url=user.avatar_url)
        embed.add_field(name=t.username, value=str(user.name.encode())[2:-1], inline=False)
        if isinstance(user, Member) and user.nick:
            embed.add_field(name=t.nickname, value=str(user.nick.encode())[2:-1], inline=False)

        await reply(ctx, embed=embed)

    @commands.command(aliases=["rc"])
    @UtilsPermission.suggest_role_color.check
    @max_concurrency(1)
    @guild_only()
    @docs(t.commands.suggest_role_color)
    async def suggest_role_color(self, ctx: Context, *avoid: Color):
        avoid: tuple[int]

        colors = [hex(color)[2:].zfill(6) for role in ctx.guild.roles if (color := role.color.value)]
        colors += [hex(c)[2:].zfill(6) for c in avoid]
        colors = [[int(x, 16) / 255 for x in [c[:2], c[2:4], c[4:]]] for c in colors]
        colors += itertools.product(range(2), repeat=3)

        color = await run_in_thread(generate_color, colors, 2000, 5e-5)
        color = "%02X" * 3 % tuple([round(float(c) * 255) for c in color])

        embed = Embed(title="#" + color, color=int(color, 16))
        embed.set_image(url=f"https://singlecolorimage.com/get/{color}/400x100")
        await reply(ctx, embed=embed)
