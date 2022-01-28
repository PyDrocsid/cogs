import re

from aiohttp import ClientError
from discord import Embed
from discord.ext import commands
from discord.ext.commands import CommandError, UserInputError, Context
from sentry_sdk import capture_exception

from PyDrocsid.cog import Cog
from PyDrocsid.command import docs
from PyDrocsid.embeds import send_long_embed
from PyDrocsid.logger import get_logger
from PyDrocsid.material_colors import MaterialColors
from PyDrocsid.translations import t
from .api import PistonAPI, PistonException
from ...contributor import Contributor

logger = get_logger(__name__)

tg = t.g
t = t.run_code

N_CHARS = 1000


class RunCodeCog(Cog, name="Run Code"):
    CONTRIBUTORS = [Contributor.Florian, Contributor.Defelo]

    def __init__(self):
        self.api = PistonAPI()

    async def on_ready(self):
        logger.info("Loading piston environments")
        try:
            await self.api.load_environments()
        except PistonException:
            logger.error("Could not load piston environments!")
            return

        self.run.help = (
            t.commands.run + "\n\n" + t.supported_languages(", ".join(f"`{lang}`" for lang in self.api.environments))
        )

    async def execute(self, ctx: Context, language: str, source: str, stdin: str = ""):
        if not (language := self.api.get_language(language)):
            raise CommandError(t.error_unsupported_language(language))

        await ctx.trigger_typing()

        try:
            result: dict = await self.api.run_code(language, source, stdin)
        except PistonException as e:
            capture_exception()
            raise CommandError(f"{t.error_run_code}: {e.error}")
        except ClientError:
            capture_exception()
            raise CommandError(t.error_run_code)

        output: str = result["run"]["output"]
        if len(output) > N_CHARS:
            newline = output.find("\n", N_CHARS, N_CHARS + 20)
            if newline == -1:
                newline = N_CHARS
            output = output[:newline] + "\n..."

        description = "```\n" + output.replace("`", "`\u200b") + "\n```"

        lang = result["language"]
        version = result["version"]
        embed = Embed(title=t.run_output(lang, version), color=MaterialColors.green, description=description)
        if result["run"]["code"] != 0:
            embed.colour = MaterialColors.error

        embed.set_footer(text=tg.requested_by(ctx.author, ctx.author.id), icon_url=ctx.author.display_avatar.url)

        await send_long_embed(ctx, embed)

    @commands.command(usage=t.run_usage)
    @docs(t.commands.run)
    async def run(self, ctx: Context, *, code: str):
        if not (match := re.fullmatch(r"(```)([a-zA-Z\d]+)\n(.+?)\1(\n(.+?))?", code, re.DOTALL)):
            raise UserInputError

        _, lang, source, _, stdin = match.groups()
        await self.execute(ctx, lang, source, stdin)

    @commands.command(aliases=["="])
    @docs(t.commands.eval)
    async def eval(self, ctx: Context, *, expr: str):
        if not (match := re.fullmatch(r"(`*)([a-zA-Z\d]*\n)?(.+?)\1", expr, re.DOTALL)):
            raise UserInputError

        code = (
            "from functools import reduce\n"
            "from itertools import *\n"
            "from operator import *\n"
            "from random import *\n"
            "from string import *\n"
            "from math import *\n"
            "print(eval(open(0).read()))"
        )

        *_, expr = match.groups()
        await self.execute(ctx, "python", code, expr.strip())
