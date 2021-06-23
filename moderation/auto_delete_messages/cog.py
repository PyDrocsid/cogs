import datetime

from PyDrocsid.cog import Cog
from PyDrocsid.database import db, select
from PyDrocsid.translations import t
from discord import TextChannel
from discord.ext import commands, tasks
from discord.ext.commands import Context, UserInputError, guild_only, CommandError

from .models import AutoDeleteMessage
from ...contributor import Contributor

t = t.auto_delete_messages


class AutoDeleteMessages(Cog, name="Auto Delete Messages"):
    CONTRIBUTORS = [Contributor.Florian, Contributor.Defelo]

    @tasks.loop()
    async def delete_old_messages_loop(self):
        async for auto_delete in await db.stream(select(AutoDeleteMessage)):
            channel = self.bot.get_channel(auto_delete.channel)
            minutes = auto_delete.minutes
            async for message in channel.history(limit=None):
                time_diff = (datetime.datetime.now() - message.created_at).total_seconds() // 60
                if time_diff >= minutes:
                    await message.delete()

    async def on_ready(self):
        await self.start_loop(1)

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

    async def start_loop(self, interval):
        self.delete_old_messages_loop.cancel()
        self.delete_old_messages_loop.change_interval(seconds=interval)
        try:
            self.delete_old_messages_loop.start()
        except RuntimeError:
            self.delete_old_messages_loop.restart()
