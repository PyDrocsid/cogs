import datetime
from typing import Optional

import discord
from PyDrocsid.cog import Cog
from PyDrocsid.command import docs
from PyDrocsid.database import db, select, db_wrapper
from PyDrocsid.emojis import name_to_emoji
from PyDrocsid.translations import t
from discord import TextChannel, Forbidden, Embed
from discord.ext import commands, tasks
from discord.ext.commands import Context, UserInputError, guild_only, CommandError

from .models import AutoDeleteMessage
from .permissions import AutoDeleteMessagesPermission
from ...contributor import Contributor
from ...pubsub import send_alert, send_to_changelog
from .colors import Colors

tg = t.g
t = t.auto_delete_messages


class AutoDeleteMessagesCog(Cog, name="Auto Delete Messages"):
    CONTRIBUTORS = [Contributor.Florian, Contributor.Defelo]

    @commands.group(aliases=["adm"])
    @guild_only()
    @AutoDeleteMessagesPermission.read.check
    @docs(t.commands.auto_delete_messages)
    async def auto_delete_messages(self, ctx: Context):
        if ctx.subcommand_passed is not None:
            if ctx.invoked_subcommand is None:
                raise UserInputError
            return

        embed = Embed(title=t.auto_delete_messages, colour=Colors.AutoDeleteMessages)
        out = []
        async for auto_delete in await db.stream(select(AutoDeleteMessage)):
            channel: Optional[TextChannel] = self.bot.get_channel(auto_delete.channel)
            if not channel:
                continue
            out.append(f"<#{auto_delete.channel}>: {auto_delete.minutes}")
        if not out:
            embed.description = t.no_auto_delete_message
            embed.colour = Colors.error
        else:
            embed.description = "\n".join(out)
        await ctx.send(embed=embed)

    @tasks.loop(minutes=60)
    @db_wrapper
    async def delete_old_messages_loop(self):
        async for auto_delete in await db.stream(select(AutoDeleteMessage)):
            channel = self.bot.get_channel(auto_delete.channel)
            if not channel:
                await db.delete(auto_delete)
                continue
            minutes = auto_delete.minutes
            async for message in channel.history(limit=None, oldest_first=True):
                time_diff = (datetime.datetime.now() - message.created_at).total_seconds() // 60
                if time_diff >= minutes:
                    try:
                        await message.delete()
                    except Forbidden:
                        await send_alert(message.guild, t.not_deleted(channel.name))

    async def on_ready(self):
        await self.start_loop(1)

    @AutoDeleteMessagesPermission.write.check
    @docs(t.commands.add_channel)
    @auto_delete_messages.command(aliases=["add"])
    async def set_channel_ttl(self, ctx: Context, channel: TextChannel, minutes: int):
        if minutes <= 0:
            raise CommandError(t.negative_value)
        row = await db.get(AutoDeleteMessage, channel=channel.id)
        if not row:
            await AutoDeleteMessage.create(channel.id, minutes)
        else:
            row.minutes = minutes
        await send_to_changelog(ctx.guild, t.channel_added(channel.name))
        await ctx.message.add_reaction(name_to_emoji["white_check_mark"])

    @auto_delete_messages.command(aliases=["rm"])
    @docs(t.commands.remove_channel)
    @AutoDeleteMessagesPermission.read.check
    async def disable(self, ctx: Context, channel: TextChannel):
        row = await db.get(AutoDeleteMessage, channel=channel.id)
        if not row:
            raise CommandError(t.no_rule)
        await db.delete(row)
        await send_to_changelog(ctx.guild, t.channel_removed(channel.name))
        await ctx.message.add_reaction(name_to_emoji["white_check_mark"])

    async def start_loop(self, interval):
        self.delete_old_messages_loop.cancel()
        self.delete_old_messages_loop.change_interval(minutes=interval)
        try:
            self.delete_old_messages_loop.start()
        except RuntimeError:
            self.delete_old_messages_loop.restart()
