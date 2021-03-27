from datetime import datetime, timedelta
from typing import Optional, Set, Union

from discord import TextChannel, Message, Embed, RawMessageDeleteEvent, Guild
from discord.ext import commands, tasks
from discord.ext.commands import guild_only, Context, CommandError, UserInputError

from PyDrocsid.cog import Cog
from PyDrocsid.database import db_wrapper
from PyDrocsid.translations import t
from PyDrocsid.util import calculate_edit_distance, send_long_embed, reply
from cogs.library.contributor import Contributor
from cogs.library.pubsub import send_to_changelog, send_alert, can_respond_on_reaction
from .colors import Colors
from .models import LogExclude
from .permissions import LoggingPermission
from .settings import LoggingSettings

tg = t.g
t = t.logging

ignored_messages: Set[int] = set()


def ignore(message: Message):
    ignored_messages.add(message.id)


async def delete_nolog(message: Message, delay: Optional[int] = None):
    ignore(message)
    await message.delete(delay=delay)


def add_field(embed: Embed, name: str, text: str):
    first = True
    while text:
        embed.add_field(name=["\ufeff", name][first], value=text[:1024], inline=False)
        text = text[1024:]
        first = False


async def send_to_channel(guild: Guild, setting: LoggingSettings, message: Union[str, Embed]):
    channel: Optional[TextChannel] = guild.get_channel(await setting.get())
    if not channel:
        return

    if isinstance(message, str):
        embed = Embed(colour=Colors.changelog, description=message)
    else:
        embed = message
    await channel.send(embed=embed)


async def is_logging_channel(channel: TextChannel) -> bool:
    for setting in [LoggingSettings.edit_channel, LoggingSettings.delete_channel]:
        if channel.id == await setting.get():
            return True

    return False


class LoggingCog(Cog, name="Logging"):
    CONTRIBUTORS = [Contributor.Defelo, Contributor.wolflu]
    PERMISSIONS = LoggingPermission

    async def get_logging_channel(self, setting: LoggingSettings) -> Optional[TextChannel]:
        return self.bot.get_channel(await setting.get())

    @send_to_changelog.subscribe
    async def handle_send_to_changelog(self, guild: Guild, message: Union[str, Embed]):
        await send_to_channel(guild, LoggingSettings.changelog_channel, message)

    @send_alert.subscribe
    async def handle_send_alert(self, guild: Guild, message: Union[str, Embed]):
        await send_to_channel(guild, LoggingSettings.alert_channel, message)

    @can_respond_on_reaction.subscribe
    async def handle_can_respond_on_reaction(self, channel: TextChannel) -> bool:
        for setting in [
            LoggingSettings.edit_channel,
            LoggingSettings.delete_channel,
            LoggingSettings.alert_channel,
            LoggingSettings.changelog_channel,
        ]:
            if await setting.get() == channel.id:
                return False
        return True

    async def on_ready(self):
        try:
            self.cleanup_loop.start()
        except RuntimeError:
            self.cleanup_loop.restart()

    @tasks.loop(minutes=30)
    @db_wrapper
    async def cleanup_loop(self):
        days: int = await LoggingSettings.maxage.get()
        if days == -1:
            return

        timestamp = datetime.utcnow() - timedelta(days=days)
        for setting in [LoggingSettings.edit_channel, LoggingSettings.delete_channel]:
            channel: Optional[TextChannel] = await self.get_logging_channel(setting)
            if channel is None:
                continue

            async for message in channel.history(limit=None, oldest_first=True):  # type: Message
                if message.created_at > timestamp:
                    break

                await message.delete()

    async def on_message_edit(self, before: Message, after: Message):
        if before.guild is None:
            return
        if before.id in ignored_messages:
            ignored_messages.remove(before.id)
            return
        mindiff: int = await LoggingSettings.edit_mindiff.get()
        if calculate_edit_distance(before.content, after.content) < mindiff:
            return
        if (edit_channel := await self.get_logging_channel(LoggingSettings.edit_channel)) is None:
            return
        if await LogExclude.exists(after.channel.id):
            return

        embed = Embed(title=t.message_edited, color=Colors.edit, timestamp=datetime.utcnow())
        embed.add_field(name=t.channel, value=before.channel.mention)
        embed.add_field(name=t.author, value=before.author.mention)
        embed.add_field(name=t.url, value=before.jump_url, inline=False)
        add_field(embed, t.old_content, before.content)
        add_field(embed, t.new_content, after.content)
        await edit_channel.send(embed=embed)

    async def on_raw_message_edit(self, channel: TextChannel, message: Message):
        if message.guild is None:
            return
        if message.id in ignored_messages:
            ignored_messages.remove(message.id)
            return
        if (edit_channel := await self.get_logging_channel(LoggingSettings.edit_channel)) is None:
            return
        if await LogExclude.exists(message.channel.id):
            return

        embed = Embed(title=t.message_edited, color=Colors.edit, timestamp=datetime.utcnow())
        embed.add_field(name=t.channel, value=channel.mention)
        if message is not None:
            embed.add_field(name=t.author, value=message.author.mention)
            embed.add_field(name=t.url, value=message.jump_url, inline=False)
            add_field(embed, t.new_content, message.content)
        await edit_channel.send(embed=embed)

    async def on_message_delete(self, message: Message):
        if message.guild is None:
            return
        if message.id in ignored_messages:
            ignored_messages.remove(message.id)
            return
        if (delete_channel := await self.get_logging_channel(LoggingSettings.delete_channel)) is None:
            return
        if await is_logging_channel(message.channel):
            return
        if await LogExclude.exists(message.channel.id):
            return

        embed = Embed(title=t.message_deleted, color=Colors.delete, timestamp=datetime.utcnow())
        embed.add_field(name=t.channel, value=message.channel.mention)
        embed.add_field(name=t.author, value=message.author.mention)
        add_field(embed, t.old_content, message.content)
        if message.attachments:
            out = []
            for attachment in message.attachments:
                size = attachment.size
                for _unit in "BKMG":
                    if size < 1000:
                        break
                    size /= 1000
                out.append(f"{attachment.filename} ({size:.1f} {_unit})")
            embed.add_field(name=t.attachments, value="\n".join(out), inline=False)
        await delete_channel.send(embed=embed)

    async def on_raw_message_delete(self, event: RawMessageDeleteEvent):
        if event.guild_id is None:
            return
        if event.message_id in ignored_messages:
            ignored_messages.remove(event.message_id)
            return
        if (delete_channel := await self.get_logging_channel(LoggingSettings.delete_channel)) is None:
            return
        if await LogExclude.exists(event.channel_id):
            return

        embed = Embed(title=t.message_deleted, color=Colors.delete, timestamp=datetime.utcnow())
        channel: Optional[TextChannel] = self.bot.get_channel(event.channel_id)
        if channel is not None:
            if await is_logging_channel(channel):
                return

            embed.add_field(name=t.channel, value=channel.mention)
            embed.add_field(name=t.message_id, value=event.message_id, inline=False)
        await delete_channel.send(embed=embed)

    @commands.group(aliases=["log"])
    @LoggingPermission.read.check
    @guild_only()
    async def logging(self, ctx: Context):
        """
        view and change logging settings
        """

        if ctx.subcommand_passed is not None:
            if ctx.invoked_subcommand is None:
                raise UserInputError
            return

        edit_channel: Optional[TextChannel] = await self.get_logging_channel(LoggingSettings.edit_channel)
        delete_channel: Optional[TextChannel] = await self.get_logging_channel(LoggingSettings.delete_channel)
        alert_channel: Optional[TextChannel] = await self.get_logging_channel(LoggingSettings.alert_channel)
        changelog_channel: Optional[TextChannel] = await self.get_logging_channel(LoggingSettings.changelog_channel)
        maxage: int = await LoggingSettings.maxage.get()

        embed = Embed(title=t.logging, color=Colors.Logging)

        if maxage != -1:
            embed.add_field(name=t.maxage, value=tg.x_days(cnt=maxage), inline=False)
        else:
            embed.add_field(name=t.maxage, value=tg.disabled, inline=False)

        if edit_channel is not None:
            mindiff: int = await LoggingSettings.edit_mindiff.get()
            embed.add_field(name=t.msg_edit, value=edit_channel.mention, inline=True)
            embed.add_field(name=t.mindiff, value=str(mindiff), inline=True)
        else:
            embed.add_field(name=t.msg_edit, value=t.logging_disabled, inline=False)

        if delete_channel is not None:
            embed.add_field(name=t.msg_delete, value=delete_channel.mention, inline=False)
        else:
            embed.add_field(name=t.msg_delete, value=t.logging_disabled, inline=False)

        if alert_channel is not None:
            embed.add_field(name=t.alert_channel, value=alert_channel.mention, inline=False)
        else:
            embed.add_field(name=t.alert_channel, value=tg.disabled, inline=False)

        if changelog_channel is not None:
            embed.add_field(name=t.changelog, value=changelog_channel.mention, inline=False)
        else:
            embed.add_field(name=t.changelog, value=tg.disabled, inline=False)

        await reply(ctx, embed=embed)

    @logging.command(name="maxage", aliases=["ma"])
    @LoggingPermission.write.check
    async def logging_maxage(self, ctx: Context, days: int):
        """
        configure period after which old log entries should be deleted
        set to -1 to disable
        """

        if days != -1 and not 0 < days < (1 << 31):
            raise CommandError(tg.invalid_duration)

        await LoggingSettings.maxage.set(days)
        embed = Embed(title=t.logging, color=Colors.Logging)
        if days == -1:
            embed.description = t.maxage_set_disabled
            await send_to_changelog(ctx.guild, t.maxage_set_disabled)
        else:
            embed.description = t.maxage_set(cnt=days)
            await send_to_changelog(ctx.guild, t.maxage_set(cnt=days))

        await reply(ctx, embed=embed)

    @logging.group(name="edit", aliases=["e"])
    @LoggingPermission.write.check
    async def logging_edit(self, ctx: Context):
        """
        change settings for edit event logging
        """

        if ctx.invoked_subcommand is None:
            raise UserInputError

    @logging_edit.command(name="mindist", aliases=["md"])
    async def logging_edit_mindist(self, ctx: Context, mindist: int):
        """
        change the minimum edit distance between the old and new content of the message to be logged
        """

        if mindist <= 0:
            raise CommandError(t.min_diff_gt_zero)

        await LoggingSettings.edit_mindiff.set(mindist)
        embed = Embed(title=t.logging, description=t.edit_mindiff_updated(mindist), color=Colors.Logging)
        await reply(ctx, embed=embed)
        await send_to_changelog(ctx.guild, t.log_mindiff_updated(mindist))

    @logging_edit.command(name="channel", aliases=["ch", "c"])
    async def logging_edit_channel(self, ctx: Context, channel: TextChannel):
        """
        change logging channel for edit events
        """

        if not channel.permissions_for(channel.guild.me).send_messages:
            raise CommandError(t.log_not_changed_no_permissions)

        await LoggingSettings.edit_channel.set(channel.id)
        embed = Embed(
            title=t.logging,
            description=t.log_edit_updated(channel.mention),
            color=Colors.Logging,
        )
        await reply(ctx, embed=embed)
        await send_to_changelog(ctx.guild, t.log_edit_updated(channel.mention))

    @logging_edit.command(name="disable", aliases=["d"])
    async def logging_edit_disable(self, ctx: Context):
        """
        disable edit event logging
        """

        await LoggingSettings.edit_channel.reset()
        embed = Embed(title=t.logging, description=t.log_edit_disabled, color=Colors.Logging)
        await reply(ctx, embed=embed)
        await send_to_changelog(ctx.guild, t.log_edit_disabled)

    @logging.group(name="delete", aliases=["d"])
    @LoggingPermission.write.check
    async def logging_delete(self, ctx: Context):
        """
        change settings for delete event logging
        """

        if ctx.invoked_subcommand is None:
            raise UserInputError

    @logging_delete.command(name="channel", aliases=["ch", "c"])
    async def logging_delete_channel(self, ctx: Context, channel: TextChannel):
        """
        change logging channel for delete events
        """

        if not channel.permissions_for(channel.guild.me).send_messages:
            raise CommandError(t.log_not_changed_no_permissions)

        await LoggingSettings.delete_channel.set(channel.id)
        embed = Embed(
            title=t.logging,
            description=t.log_delete_updated(channel.mention),
            color=Colors.Logging,
        )
        await reply(ctx, embed=embed)
        await send_to_changelog(ctx.guild, t.log_delete_updated(channel.mention))

    @logging_delete.command(name="disable", aliases=["d"])
    async def logging_delete_disable(self, ctx: Context):
        """
        disable delete event logging
        """

        await LoggingSettings.delete_channel.reset()
        embed = Embed(title=t.logging, description=t.log_delete_disabled, color=Colors.Logging)
        await reply(ctx, embed=embed)
        await send_to_changelog(ctx.guild, t.log_delete_disabled)

    @logging.group(name="alert", aliases=["al", "a"])
    @LoggingPermission.write.check
    async def logging_alert(self, ctx: Context):
        """
        change settings for internal alert channel
        """

        if ctx.invoked_subcommand is None:
            raise UserInputError

    @logging_alert.command(name="channel", aliases=["ch", "c"])
    async def logging_alert_channel(self, ctx: Context, channel: TextChannel):
        """
        change alert channel
        """

        if not channel.permissions_for(channel.guild.me).send_messages:
            raise CommandError(t.log_not_changed_no_permissions)

        await LoggingSettings.alert_channel.set(channel.id)
        embed = Embed(
            title=t.logging,
            description=t.log_alert_updated(channel.mention),
            color=Colors.Logging,
        )
        await reply(ctx, embed=embed)
        await send_to_changelog(ctx.guild, t.log_alert_updated(channel.mention))

    @logging_alert.command(name="disable", aliases=["d"])
    async def logging_alert_disable(self, ctx: Context):
        """
        disable alert channel
        """

        await send_to_changelog(ctx.guild, t.log_alert_disabled)
        await LoggingSettings.alert_channel.reset()
        embed = Embed(title=t.logging, description=t.log_alert_disabled, color=Colors.Logging)
        await reply(ctx, embed=embed)

    @logging.group(name="changelog", aliases=["cl", "c", "change"])
    @LoggingPermission.write.check
    async def logging_changelog(self, ctx: Context):
        """
        change settings for internal changelog
        """

        if ctx.invoked_subcommand is None:
            raise UserInputError

    @logging_changelog.command(name="channel", aliases=["ch", "c"])
    async def logging_changelog_channel(self, ctx: Context, channel: TextChannel):
        """
        change changelog channel
        """

        if not channel.permissions_for(channel.guild.me).send_messages:
            raise CommandError(t.log_not_changed_no_permissions)

        await LoggingSettings.changelog_channel.set(channel.id)
        embed = Embed(
            title=t.logging,
            description=t.log_changelog_updated(channel.mention),
            color=Colors.Logging,
        )
        await reply(ctx, embed=embed)
        await send_to_changelog(ctx.guild, t.log_changelog_updated(channel.mention))

    @logging_changelog.command(name="disable", aliases=["d"])
    async def logging_changelog_disable(self, ctx: Context):
        """
        disable changelog
        """

        await send_to_changelog(ctx.guild, t.log_changelog_disabled)
        await LoggingSettings.changelog_channel.reset()
        embed = Embed(title=t.logging, description=t.log_changelog_disabled, color=Colors.Logging)
        await reply(ctx, embed=embed)

    @logging.group(name="exclude", aliases=["x", "ignore", "i"])
    async def logging_exclude(self, ctx: Context):
        """
        manage excluded channels
        """

        if len(ctx.message.content.lstrip(ctx.prefix).split()) > 2:
            if ctx.invoked_subcommand is None:
                raise UserInputError
            return

        embed = Embed(title=t.excluded_channels, colour=Colors.Logging)
        out = []
        for channel_id in await LogExclude.all():
            channel: Optional[TextChannel] = self.bot.get_channel(channel_id)
            if channel is None:
                await LogExclude.remove(channel_id)
            else:
                out.append(f":small_blue_diamond: {channel.mention}")
        if not out:
            embed.description = t.no_channels_excluded
            embed.colour = Colors.error
        else:
            embed.description = "\n".join(out)
        await send_long_embed(ctx, embed)

    @logging_exclude.command(name="add", aliases=["a", "+"])
    @LoggingPermission.write.check
    async def logging_exclude_add(self, ctx: Context, channel: TextChannel):
        """
        exclude a channel from logging
        """

        if await LogExclude.exists(channel.id):
            raise CommandError(t.already_excluded)

        await LogExclude.add(channel.id)
        embed = Embed(title=t.excluded_channels, description=t.excluded, colour=Colors.Logging)
        await reply(ctx, embed=embed)
        await send_to_changelog(ctx.guild, t.log_excluded(channel.mention))

    @logging_exclude.command(name="remove", aliases=["r", "del", "d", "-"])
    @LoggingPermission.write.check
    async def logging_exclude_remove(self, ctx: Context, channel: TextChannel):
        """
        remove a channel from exclude list
        """

        if not await LogExclude.exists(channel.id):
            raise CommandError(t.not_excluded)

        await LogExclude.remove(channel.id)
        embed = Embed(title=t.excluded_channels, description=t.unexcluded, colour=Colors.Logging)
        await reply(ctx, embed=embed)
        await send_to_changelog(ctx.guild, t.log_unexcluded(channel.mention))
