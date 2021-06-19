import json
from datetime import datetime, timedelta
from typing import Optional, Union

from PyDrocsid.logger import get_logger
from discord import TextChannel, Message, Embed, RawMessageDeleteEvent, Guild, Member, Forbidden
from discord.ext import commands, tasks
from discord.ext.commands import guild_only, Context, CommandError, UserInputError, Group, Command

from PyDrocsid.cog import Cog
from PyDrocsid.command import reply, docs
from PyDrocsid.database import db_wrapper
from PyDrocsid.embeds import send_long_embed
from PyDrocsid.environment import CACHE_TTL
from PyDrocsid.redis import redis
from PyDrocsid.translations import t
from PyDrocsid.util import calculate_edit_distance, check_message_send_permissions
from .colors import Colors
from .models import LogExclude
from .permissions import LoggingPermission
from .settings import LoggingSettings
from ...contributor import Contributor
from ...pubsub import send_to_changelog, send_alert, can_respond_on_reaction, ignore_message_edit


logger = get_logger(__name__)

tg = t.g
t = t.logging


def add_field(embed: Embed, name: str, text: str):
    first = True
    while text:
        embed.add_field(name=["\ufeff", name][first], value=text[:1024], inline=False)
        text = text[1024:]
        first = False


async def send_to_channel(guild: Guild, setting: LoggingSettings, message: Union[str, Embed]):
    msg = json.dumps(message.to_dict()) if isinstance(message, Embed) else message
    channel: Optional[TextChannel] = guild.get_channel(await setting.get())
    if not channel:
        logger.warning(f"Could not send message to {setting.name}: {msg}")
        return

    if isinstance(message, str):
        embed = Embed(colour=Colors.changelog, description=message)
    else:
        embed = message

    try:
        await channel.send(embed=embed)
    except Forbidden:
        logger.warning(f"Could not send message to {setting.name}: {msg}")
    else:
        logger.info(f"{setting.name}: {msg}")


async def is_logging_channel(channel: TextChannel) -> bool:
    for setting in [LoggingSettings.edit_channel, LoggingSettings.delete_channel]:
        if channel.id == await setting.get():
            return True

    return False


channels: list[str] = []


def add_channel(group: Group, name: str, *aliases: str) -> tuple[Group, Command, Command]:
    channels.append(name)

    @group.group(name=name, aliases=list(aliases))
    @LoggingPermission.write.check
    @docs(getattr(t.channels, name).manage_description)
    async def logging_channel(_, ctx: Context):
        if ctx.invoked_subcommand is None:
            raise UserInputError

    @logging_channel.command(name="channel", aliases=["ch", "c"])
    @docs(getattr(t.channels, name).set_description)
    async def set_channel(ctx: Context, *, channel: TextChannel):
        check_message_send_permissions(channel, check_embed=True)

        await getattr(LoggingSettings, f"{name}_channel").set(channel.id)
        embed = Embed(
            title=t.logging,
            description=(text := getattr(t.channels, name).updated(channel.mention)),
            color=Colors.Logging,
        )
        await reply(ctx, embed=embed)
        await send_to_changelog(ctx.guild, text)

    @logging_channel.command(name="disable", aliases=["d"])
    @docs(getattr(t.channels, name).disable_description)
    async def disable_channel(ctx: Context):
        await getattr(LoggingSettings, f"{name}_channel").reset()
        embed = Embed(
            title=t.logging,
            description=(text := getattr(t.channels, name).disabled),
            color=Colors.Logging,
        )
        await reply(ctx, embed=embed)
        await send_to_changelog(ctx.guild, text)

    return logging_channel, set_channel, disable_channel


class LoggingCog(Cog, name="Logging"):
    CONTRIBUTORS = [Contributor.Defelo, Contributor.wolflu, Contributor.Tert0]

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
            LoggingSettings.member_join_channel,
            LoggingSettings.member_leave_channel,
        ]:
            if await setting.get() == channel.id:
                return False
        return True

    @ignore_message_edit.subscribe
    async def handle_ignore_message_edit(self, message: Message):
        await redis.setex(f"ignore_message_edit:{message.channel.id}:{message.id}", CACHE_TTL, 1)

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
        if await redis.delete(f"ignore_message_edit:{before.channel.id}:{before.id}"):
            return
        mindiff: int = await LoggingSettings.edit_mindiff.get()
        old_message = await redis.get(key := f"little_diff_message_edit:{before.id}") or before.content
        if calculate_edit_distance(old_message, after.content) < mindiff:
            if not await redis.exists(key):
                await redis.setex(key, 60 * 60 * 24, before.content)
            return
        if (edit_channel := await self.get_logging_channel(LoggingSettings.edit_channel)) is None:
            return
        if await LogExclude.exists(after.channel.id):
            return
        await redis.delete(key)
        embed = Embed(title=t.message_edited, color=Colors.edit, timestamp=datetime.utcnow())
        embed.add_field(name=t.channel, value=before.channel.mention)
        embed.add_field(name=t.author, value=before.author.mention)
        embed.add_field(name=t.url, value=before.jump_url, inline=False)
        add_field(embed, t.old_content, old_message)
        add_field(embed, t.new_content, after.content)
        await edit_channel.send(embed=embed)

    async def on_raw_message_edit(self, channel: TextChannel, message: Message):
        if message.guild is None:
            return
        if await redis.delete(f"ignore_message_edit:{channel.id}:{message.id}"):
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
        if (delete_channel := await self.get_logging_channel(LoggingSettings.delete_channel)) is None:
            return
        await redis.delete(f"little_diff_message_edit:{message.id}")
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
                out.append(f"[{attachment.filename}]({attachment.url}) ({size:.1f} {_unit})")
            embed.add_field(name=t.attachments, value="\n".join(out), inline=False)
        await delete_channel.send(embed=embed)

    async def on_raw_message_delete(self, event: RawMessageDeleteEvent):
        if event.guild_id is None:
            return
        if (delete_channel := await self.get_logging_channel(LoggingSettings.delete_channel)) is None:
            return
        await redis.delete(f"little_diff_message_edit:{event.message_id}")
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

    async def on_member_join(self, member: Member):
        if (log_channel := await self.get_logging_channel(LoggingSettings.member_join_channel)) is None:
            return

        await log_channel.send(t.member_joined_server(member.mention, member))

    async def on_member_remove(self, member: Member):
        if (log_channel := await self.get_logging_channel(LoggingSettings.member_leave_channel)) is None:
            return

        await log_channel.send(t.member_left_server(member))

    @commands.group(aliases=["log"])
    @LoggingPermission.read.check
    @guild_only()
    @docs(t.commands.logging)
    async def logging(self, ctx: Context):
        if ctx.subcommand_passed is not None:
            if ctx.invoked_subcommand is None:
                raise UserInputError
            return

        embed = Embed(title=t.logging, color=Colors.Logging)

        maxage: int = await LoggingSettings.maxage.get()
        if maxage != -1:
            embed.add_field(name=t.maxage, value=tg.x_days(cnt=maxage), inline=False)
        else:
            embed.add_field(name=t.maxage, value=tg.disabled, inline=False)

        for name in channels:
            channel: Optional[TextChannel] = await self.get_logging_channel(getattr(LoggingSettings, f"{name}_channel"))
            embed.add_field(
                name=getattr(t.channels, name).name,
                value=channel.mention if channel else tg.disabled,
                inline=name == "edit",
            )

            if name == "edit" and channel is not None:
                mindist: int = await LoggingSettings.edit_mindiff.get()
                embed.add_field(name=t.channels.edit.mindist.name, value=str(mindist), inline=True)

        await reply(ctx, embed=embed)

    @logging.command(name="maxage", aliases=["ma"])
    @LoggingPermission.write.check
    @docs(t.commands.maxage)
    async def logging_maxage(self, ctx: Context, days: int):
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

    logging_edit, *_ = add_channel(logging, "edit", "e")
    logging_delete, *_ = add_channel(logging, "delete", "d")
    logging_alert, *_ = add_channel(logging, "alert", "al", "a")
    logging_changelog, *_ = add_channel(logging, "changelog", "change", "cl", "c")
    logging_member_join, *_ = add_channel(logging, "member_join", "memberjoin", "join", "mj")
    logging_member_leave, *_ = add_channel(logging, "member_leave", "memberleave", "leave", "ml")

    @logging_edit.command(name="mindist", aliases=["md"])
    @docs(t.channels.edit.mindist.set_description)
    async def logging_edit_mindist(self, ctx: Context, mindist: int):
        if mindist <= 0:
            raise CommandError(t.channels.edit.mindist.gt_zero)

        await LoggingSettings.edit_mindiff.set(mindist)
        embed = Embed(title=t.logging, description=t.channels.edit.mindist.updated(mindist), color=Colors.Logging)
        await reply(ctx, embed=embed)
        await send_to_changelog(ctx.guild, t.channels.edit.mindist.log_updated(mindist))

    @logging.group(name="exclude", aliases=["x", "ignore", "i"])
    @docs(t.commands.exclude)
    async def logging_exclude(self, ctx: Context):
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
    @docs(t.commands.exclude_add)
    async def logging_exclude_add(self, ctx: Context, channel: TextChannel):
        if await LogExclude.exists(channel.id):
            raise CommandError(t.already_excluded)

        await LogExclude.add(channel.id)
        embed = Embed(title=t.excluded_channels, description=t.excluded, colour=Colors.Logging)
        await reply(ctx, embed=embed)
        await send_to_changelog(ctx.guild, t.log_excluded(channel.mention))

    @logging_exclude.command(name="remove", aliases=["r", "del", "d", "-"])
    @LoggingPermission.write.check
    @docs(t.commands.exclude_remove)
    async def logging_exclude_remove(self, ctx: Context, channel: TextChannel):
        if not await LogExclude.exists(channel.id):
            raise CommandError(t.not_excluded)

        await LogExclude.remove(channel.id)
        embed = Embed(title=t.excluded_channels, description=t.unexcluded, colour=Colors.Logging)
        await reply(ctx, embed=embed)
        await send_to_changelog(ctx.guild, t.log_unexcluded(channel.mention))
