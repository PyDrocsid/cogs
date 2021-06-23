from PyDrocsid.cog import Cog
from discord import TextChannel
from discord.ext import commands
from discord.ext.commands import Context, UserInputError, guild_only, CommandError

from .models import AutoDeleteMessage
from ...contributor import Contributor
from PyDrocsid.translations import t

t = t.auto_delete_messages


class AutoDeleteMessages(Cog, name="Auto Delete Messages"):
    CONTRIBUTORS = [Contributor.Florian, Contributor.Defelo]

    @guild_only()
    @commands.group(aliases=["adm"])
    async def auto_delete_messages(self, ctx: Context):
        if ctx.invoked_subcommand is None:
            raise UserInputError

    @auto_delete_messages.command(aliases=["add"])
    async def add_channel(self, ctx: Context, channel: TextChannel, minutes: int):
        if not minutes > 0:
            raise CommandError(t.negative_value)
        await AutoDeleteMessage.create(channel.id, minutes)
