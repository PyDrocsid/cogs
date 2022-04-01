import sys

from discord import Message, TextChannel
from discord.ext import commands
from discord.ext.commands import CheckFailure, Context, check

from PyDrocsid.cog import Cog
from PyDrocsid.config import Config
from PyDrocsid.emojis import name_to_emoji
from PyDrocsid.environment import OWNER_ID
from PyDrocsid.events import call_event_handlers
from PyDrocsid.permission import permission_override
from PyDrocsid.redis import redis
from PyDrocsid.translations import t

from .permissions import SudoPermission
from ...contributor import Contributor

tg = t.g
t = t.sudo


@check
def is_sudoer(ctx: Context) -> bool:
    if ctx.author.id != OWNER_ID:
        raise CheckFailure(t.not_in_sudoers_file(ctx.author.mention))

    return True


class SudoCog(Cog, name="Sudo"):
    CONTRIBUTORS = [Contributor.Defelo, Contributor.TNT2k]

    def __init__(self):
        super().__init__()

        self.sudo_cache: dict[TextChannel, Message] = {}

    @staticmethod
    def prepare():
        return bool(OWNER_ID)

    async def on_command_error(self, ctx: Context, _):
        if ctx.author.id == OWNER_ID:
            self.sudo_cache[ctx.channel] = ctx.message

    @commands.command(hidden=True)
    @is_sudoer
    async def sudo(self, ctx: Context, *, cmd: str):
        message: Message = ctx.message
        message.content = ctx.prefix + cmd

        if cmd == "!!" and ctx.channel in self.sudo_cache:
            message.content = self.sudo_cache.pop(ctx.channel).content

        permission_override.set(Config.PERMISSION_LEVELS.max())
        await self.bot.process_commands(message)

    @commands.command()
    @SudoPermission.clear_cache.check
    async def clear_cache(self, ctx: Context):
        await redis.flushdb()
        await ctx.message.add_reaction(name_to_emoji["white_check_mark"])

    @commands.command()
    @SudoPermission.reload.check
    async def reload(self, ctx: Context):
        await call_event_handlers("ready")
        await ctx.message.add_reaction(name_to_emoji["white_check_mark"])

    @commands.command()
    @SudoPermission.stop.check
    async def stop(self, ctx: Context):
        await ctx.message.add_reaction(name_to_emoji["white_check_mark"])
        await self.bot.close()

    @commands.command()
    @SudoPermission.kill.check
    async def kill(self, ctx: Context):
        await ctx.message.add_reaction(name_to_emoji["white_check_mark"])
        sys.exit(1)
