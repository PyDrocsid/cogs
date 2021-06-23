from PyDrocsid.cog import Cog
from discord import TextChannel
from discord.ext import commands
from discord.ext.commands import Context, UserInputError, guild_only

from .models import AutoDeleteMessage
from ...contributor import Contributor


class AutoDeleteMessages(Cog, name="Auto Delete Messages"):
    CONTRIBUTORS = [Contributor.Florian, Contributor.Defelo]

    @guild_only()
    @commands.group(aliases=["adm"])
    async def auto_delete_messages(self, ctx: Context):
        if ctx.invoked_subcommand is None:
            raise UserInputError

    @auto_delete_messages.command(aliases=["add"])
    async def add_channel(self, ctx: Context, channel: TextChannel, minutes: int):
        await AutoDeleteMessage.create(channel.id, minutes)
