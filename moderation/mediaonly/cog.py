import re
from datetime import datetime
from typing import Optional

from aiohttp import ClientSession, ClientError
from discord import Guild, TextChannel, Message, Embed, Forbidden
from discord.ext import commands
from discord.ext.commands import guild_only, Context, CommandError, UserInputError

from PyDrocsid.cog import Cog
from PyDrocsid.command import reply, docs
from PyDrocsid.database import db, filter_by
from PyDrocsid.embeds import send_long_embed
from PyDrocsid.events import StopEventHandling
from PyDrocsid.translations import t
from .colors import Colors
from .models import MediaOnlyChannel, MediaOnlyDeletion
from .permissions import MediaOnlyPermission
from ...contributor import Contributor
from ...pubsub import send_to_changelog, can_respond_on_reaction, send_alert, get_userlog_entries

tg = t.g
t = t.mediaonly


async def contains_image(message: Message) -> bool:
    urls = [(att.url,) for att in message.attachments]
    urls += re.findall(r"(https?://([a-zA-Z0-9\-_~]+\.)+[a-zA-Z0-9\-_~]+(/\S*)?)", message.content)
    for url, *_ in urls:
        try:
            async with ClientSession() as session, session.head(url, allow_redirects=True) as response:
                content_length = int(response.headers["Content-length"])
                mime = response.headers["Content-type"]
        except (KeyError, AttributeError, UnicodeError, ConnectionError, ClientError):
            break

        if mime.startswith("image/") and content_length >= 256:
            return True

    return False


async def delete_message(message: Message):
    try:
        await message.delete()
    except Forbidden:
        deleted = False
    else:
        deleted = True

    await MediaOnlyDeletion.create(message.author.id, str(message.author), message.channel.id)

    embed = Embed(title=t.mediaonly, description=t.deleted_nomedia, colour=Colors.error)
    await message.channel.send(content=message.author.mention, embed=embed, delete_after=30)

    if deleted:
        await send_alert(message.guild, t.log_deleted_nomedia(message.author.mention, message.channel.mention))
    else:
        await send_alert(message.guild, t.log_nomedia_not_deleted(message.author.mention, message.channel.mention))


async def check_message(message: Message):
    if message.guild is None or message.author.bot:
        return
    if await MediaOnlyPermission.bypass.check_permissions(message.author):
        return
    if not await MediaOnlyChannel.exists(message.channel.id):
        return
    if await contains_image(message):
        return

    await delete_message(message)
    raise StopEventHandling


class MediaOnlyCog(Cog, name="MediaOnly"):
    CONTRIBUTORS = [Contributor.Defelo, Contributor.wolflu]

    @can_respond_on_reaction.subscribe
    async def handle_can_respond_on_reaction(self, channel: TextChannel) -> bool:
        return not await db.exists(filter_by(MediaOnlyChannel, channel=channel.id))

    @get_userlog_entries.subscribe
    async def handle_get_userlog_entries(self, user_id: int) -> list[tuple[datetime, str]]:
        out: list[tuple[datetime, str]] = []

        deletion: MediaOnlyDeletion
        async for deletion in await db.stream(filter_by(MediaOnlyDeletion, member=user_id)):
            out.append((deletion.timestamp, t.ulog_deletion(f"<#{deletion.channel}>")))

        return out

    async def on_message(self, message: Message):
        await check_message(message)

    async def on_message_edit(self, _, after: Message):
        await check_message(after)

    @commands.group(aliases=["mo"])
    @MediaOnlyPermission.read.check
    @guild_only()
    @docs(t.commands.mediaonly)
    async def mediaonly(self, ctx: Context):
        if ctx.subcommand_passed is not None:
            if ctx.invoked_subcommand is None:
                raise UserInputError
            return

        guild: Guild = ctx.guild
        out = []
        async for channel in MediaOnlyChannel.stream():
            text_channel: Optional[TextChannel] = guild.get_channel(channel)
            if not text_channel:
                await MediaOnlyChannel.remove(channel)
                continue

            out.append(f":small_orange_diamond: {text_channel.mention}")

        embed = Embed(title=t.media_only_channels_header, colour=Colors.error)
        if out:
            embed.colour = Colors.MediaOnly
            embed.description = "\n".join(out)
            await send_long_embed(ctx, embed)
        else:
            embed.description = t.no_media_only_channels
            await reply(ctx, embed=embed)

    @mediaonly.command(name="add", aliases=["a", "+"])
    @MediaOnlyPermission.write.check
    @docs(t.commands.add)
    async def mediaonly_add(self, ctx: Context, channel: TextChannel):
        if await MediaOnlyChannel.exists(channel.id):
            raise CommandError(t.channel_already_media_only)
        if not channel.permissions_for(channel.guild.me).manage_messages:
            raise CommandError(t.media_only_not_changed_no_permissions)

        await MediaOnlyChannel.add(channel.id)
        embed = Embed(
            title=t.media_only_channels_header,
            description=t.channel_now_media_only,
            colour=Colors.MediaOnly,
        )
        await reply(ctx, embed=embed)
        await send_to_changelog(ctx.guild, t.log_channel_now_media_only(channel.mention))

    @mediaonly.command(name="remove", aliases=["del", "r", "d", "-"])
    @MediaOnlyPermission.write.check
    @docs(t.commands.remove)
    async def mediaonly_remove(self, ctx: Context, channel: TextChannel):
        if not await MediaOnlyChannel.exists(channel.id):
            raise CommandError(t.channel_not_media_only)

        await MediaOnlyChannel.remove(channel.id)
        embed = Embed(
            title=t.media_only_channels_header,
            description=t.channel_not_media_only_anymore,
            colour=Colors.MediaOnly,
        )
        await reply(ctx, embed=embed)
        await send_to_changelog(ctx.guild, t.log_channel_not_media_only_anymore(channel.mention))
