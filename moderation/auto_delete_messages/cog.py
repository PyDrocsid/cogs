import datetime

from PyDrocsid.cog import Cog
from PyDrocsid.command import docs
from PyDrocsid.database import db, select
from PyDrocsid.translations import t
from discord import TextChannel, Forbidden
from discord.ext import commands, tasks
from discord.ext.commands import Context, UserInputError, guild_only, CommandError

from .models import AutoDeleteMessage
from .permissions import AutoDeleteMessagesPermission
from ...contributor import Contributor
from ...pubsub import send_alert

t = t.auto_delete_messages


class AutoDeleteMessages(Cog, name="Auto Delete Messages"):
    CONTRIBUTORS = [Contributor.Florian, Contributor.Defelo]

    @guild_only()
    @commands.group(aliases=["adm"])
    @docs(t.commands.auto_delete_messages)
    async def auto_delete_messages(self, ctx: Context):
        if ctx.invoked_subcommand is None:
            raise UserInputError

    @tasks.loop()
    async def delete_old_messages_loop(self):
        async for auto_delete in await db.stream(select(AutoDeleteMessage)):
            channel = self.bot.get_channel(auto_delete.channel)
            minutes = auto_delete.minutes
            async for message in channel.history(limit=None):
                time_diff = (datetime.datetime.now() - message.created_at).total_seconds() // 60
                if time_diff >= minutes:
                    try:
                        await message.delete()
                    except Forbidden:
                        await send_alert(message.guild, t.not_deleted(channel.name))

    async def on_ready(self):
        await self.start_loop(1)

    @auto_delete_messages.command(aliases=["add"])
    @docs(t.commands.add_channel)
    @AutoDeleteMessagesPermission.add.check
    async def add_channel(self, ctx: Context, channel: TextChannel, minutes: int):
        if not minutes > 0:
            raise CommandError(t.negative_value)
        row = await db.get(AutoDeleteMessage, channel=channel.id)
        if not row:
            await AutoDeleteMessage.create(channel.id, minutes)
        await AutoDeleteMessage.update(channel.id, minutes)

    @auto_delete_messages.command(aliases=["rm"])
    @docs(t.commands.remove_channel)
    @AutoDeleteMessagesPermission.remove.check
    async def remove_channel(self, ctx: Context, channel: TextChannel):
        row = await db.get(AutoDeleteMessage, channel=channel.id)
        if row:
            await db.delete(row)

    async def start_loop(self, interval):
        self.delete_old_messages_loop.cancel()
        self.delete_old_messages_loop.change_interval(hours=interval)
        try:
            self.delete_old_messages_loop.start()
        except RuntimeError:
            self.delete_old_messages_loop.restart()
