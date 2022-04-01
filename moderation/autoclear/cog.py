import asyncio
from datetime import timedelta
from typing import Optional

from discord import Embed, Forbidden, Message, NotFound, TextChannel
from discord.ext import commands, tasks
from discord.ext.commands import CommandError, Context, UserInputError, guild_only
from discord.utils import utcnow

from PyDrocsid.cog import Cog
from PyDrocsid.command import docs
from PyDrocsid.database import db, db_wrapper, select
from PyDrocsid.embeds import send_long_embed
from PyDrocsid.emojis import name_to_emoji
from PyDrocsid.translations import t

from .colors import Colors
from .models import AutoClearChannel
from .permissions import AutoClearPermission
from ...contributor import Contributor
from ...pubsub import send_alert, send_to_changelog

tg = t.g
t = t.autoclear


async def clear_channel(channel: TextChannel, minutes: int, limit: Optional[int] = None):
    if not channel.permissions_for(channel.guild.me).read_message_history:
        await send_alert(channel.guild, t.cannot_read(channel.mention))
        return

    message: Message
    async for message in channel.history(before=utcnow() - timedelta(minutes=minutes), limit=limit, oldest_first=True):
        if message.pinned:
            continue

        try:
            await message.delete()
        except Forbidden:
            await send_alert(message.guild, t.not_deleted(channel.mention))
            break
        except NotFound:
            pass


class AutoClearCog(Cog, name="AutoClear"):
    CONTRIBUTORS = [Contributor.Florian, Contributor.Defelo]

    async def on_ready(self):
        try:
            self.loop.start()
        except RuntimeError:
            self.loop.restart()

    @tasks.loop(minutes=5)
    @db_wrapper
    async def loop(self):
        autoclear: AutoClearChannel
        async for autoclear in await db.stream(select(AutoClearChannel)):
            channel = self.bot.get_channel(autoclear.channel)
            if not channel:
                await db.delete(autoclear)
                continue

            asyncio.create_task(clear_channel(channel, autoclear.minutes, limit=200))

    @commands.group(aliases=["ac"])
    @AutoClearPermission.read.check
    @guild_only()
    @docs(t.commands.autoclear)
    async def autoclear(self, ctx: Context):
        if ctx.subcommand_passed is not None:
            if ctx.invoked_subcommand is None:
                raise UserInputError
            return

        embed = Embed(title=t.autoclear, colour=Colors.AutoClear)
        out = []
        async for autoclear in await db.stream(select(AutoClearChannel)):
            channel: Optional[TextChannel] = self.bot.get_channel(autoclear.channel)
            if not channel:
                await db.delete(autoclear)
                continue

            out.append(f":small_orange_diamond: {channel.mention} ({t.minutes(cnt=autoclear.minutes)})")

        if not out:
            embed.description = t.no_autoclear_channels
            embed.colour = Colors.error
        else:
            embed.description = "\n".join(out)

        await send_long_embed(ctx, embed=embed)

    @autoclear.command(aliases=["s", "add", "a", "+", "="])
    @AutoClearPermission.write.check
    @docs(t.commands.set)
    async def set(self, ctx: Context, channel: TextChannel, minutes: int):
        if not 0 < minutes < (1 << 31):
            raise CommandError(tg.invalid_duration)

        if not channel.permissions_for(channel.guild.me).manage_messages:
            raise CommandError(t.cannot_add)

        row = await db.get(AutoClearChannel, channel=channel.id)
        if not row:
            await AutoClearChannel.create(channel.id, minutes)
        else:
            row.minutes = minutes

        await send_to_changelog(ctx.guild, t.set(channel.mention, cnt=minutes))
        await ctx.message.add_reaction(name_to_emoji["white_check_mark"])

    @autoclear.command(aliases=["d", "delete", "del", "remove", "r", "-"])
    @AutoClearPermission.write.check
    @docs(t.commands.disable)
    async def disable(self, ctx: Context, channel: TextChannel):
        row = await db.get(AutoClearChannel, channel=channel.id)
        if not row:
            raise CommandError(t.not_configured)

        await db.delete(row)
        await send_to_changelog(ctx.guild, t.disabled(channel.mention))
        await ctx.message.add_reaction(name_to_emoji["white_check_mark"])
