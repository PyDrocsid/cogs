import re

from discord import Embed, Forbidden, Message
from discord.ext import commands
from discord.ext.commands import guild_only, Context, Converter, CommandError, UserInputError

from PyDrocsid.cog import Cog
from PyDrocsid.command import confirm, docs
from PyDrocsid.database import db, filter_by
from PyDrocsid.embeds import send_long_embed
from PyDrocsid.emojis import name_to_emoji
from PyDrocsid.events import StopEventHandling
from PyDrocsid.translations import t
from .colors import Colors
from .models import BadWord, BadWordPost
from .permissions import ContentFilterPermission
from ...contributor import Contributor
from ...pubsub import send_to_changelog, send_alert, get_userlog_entries

tg = t.g
t = t.content_filter


class ContentFilterConverter(Converter):
    async def convert(self, ctx: Context, argument: str) -> BadWord:
        if argument.isnumeric():
            row = await db.get(BadWord, id=int(argument))
        else:
            row = await db.get(BadWord, regex=argument)

        if row is not None:
            return row

        raise CommandError(t.not_blacklisted)


async def check_message(message: Message):
    author = message.author

    if message.guild is None:
        return
    if await ContentFilterPermission.bypass.check_permissions(author):
        return

    bad_word_list = await BadWord.get_all_redis()
    violations = set()
    blacklisted: set[str] = set()
    for bad_word in bad_word_list:
        if matches := re.findall(bad_word, message.content):
            violations.add(bad_word)
            for match in matches:
                blacklisted.add(match)

    if not violations:
        return

    has_to_be_deleted = False
    for post in violations:
        called_object = await db.get(BadWord, regex=post)

        if called_object.delete:
            has_to_be_deleted = True
            break

    was_deleted = False
    if has_to_be_deleted:
        try:
            await message.delete()
            was_deleted = True
            log_text = t.log_forbidden_posted_deleted
        except Forbidden:
            log_text = t.log_forbidden_posted_not_deleted

    else:
        log_text = t.log_forbidden_posted

    await send_alert(
        message.guild,
        log_text(
            f"{author.mention} (`@{author}`, {author.id})",
            message.jump_url,
            message.channel.mention,
            ", ".join(blacklisted),
        ),
    )

    for post in blacklisted:
        await BadWordPost.create(author.id, author.name, message.channel.id, post, was_deleted)

    if not was_deleted:
        await message.add_reaction(name_to_emoji["warning"])
    else:
        raise StopEventHandling


class ContentFilterCog(Cog, name="Content Filter"):
    CONTRIBUTORS = [Contributor.NekoFanatic]

    @get_userlog_entries.subscribe
    async def handle_get_ulog_entries(self, user_id: int, _):
        out = []

        log: BadWordPost
        async for log in await db.stream(filter_by(BadWordPost, member=user_id)):
            if log.deleted_message:
                out.append((log.timestamp, t.ulog_message_deleted(log.content, log.channel)))
            else:
                out.append((log.timestamp, t.ulog_message(log.content, log.channel)))

        return out

    async def on_message(self, message: Message):
        await check_message(message)

    async def on_message_edit(self, _, after: Message):
        await check_message(after)

    @commands.group(name="content_filter", aliases=["cf"], invoke_without_command=True)
    @ContentFilterPermission.read.check
    @guild_only()
    @docs(t.commands.content_filter)
    async def content_filter(self, ctx: Context):
        out = False

        embed = Embed(
            title=t.bad_word_list_header,
            colour=Colors.ContentFilter,
        )

        reg: BadWord
        async for reg in await db.stream(filter_by(BadWord)):
            embed.add_field(
                name=t.embed_field_name(reg.id, reg.description),
                value=t.embed_field_value(reg.regex, t.delete if reg.delete else t.not_delete),
                inline=False,
            )

            out = True

        if not out:
            embed.colour = Colors.error
            embed.description = t.no_pattern_listed

        await send_long_embed(ctx, embed, paginate=True, max_fields=6)

    @content_filter.command(name="add", aliases=["a", "+"])
    @ContentFilterPermission.write.check
    @docs(t.commands.add)
    async def add(self, ctx: Context, regex: str, delete: bool, *, description: str):
        if await db.exists(filter_by(BadWord, regex=regex)):
            raise CommandError(t.already_blacklisted)

        if len(description) > 500:
            raise CommandError(t.description_length)

        await BadWord.create(regex, delete, description)
        await ctx.message.add_reaction(name_to_emoji["white_check_mark"])
        await send_to_changelog(ctx.guild, t.log_content_filter_added(regex, ctx.author.mention))

    @content_filter.command(name="remove", aliases=["del", "r", "d", "-"])
    @ContentFilterPermission.write.check
    @docs(t.commands.remove)
    async def remove(self, ctx: Context, pattern: ContentFilterConverter):
        pattern: BadWord

        conf_embed = Embed(title=t.confirm, description=t.confirm_text)
        async with confirm(ctx, conf_embed, danger=True) as (result, _):
            if not result:
                return

        await pattern.remove()
        await ctx.message.add_reaction(name_to_emoji["white_check_mark"])
        await send_to_changelog(ctx.guild, t.log_content_filter_removed(pattern.regex, ctx.author.mention))

    @content_filter.group(name="update", aliases=["u"])
    @ContentFilterPermission.write.check
    @docs(t.commands.update)
    async def update(self, ctx: Context):
        if ctx.invoked_subcommand is None:
            raise UserInputError

    @update.command(name="description", aliases=["d"])
    @docs(t.commands.update_description)
    async def description(self, ctx: Context, pattern: ContentFilterConverter, *, new_description: str):
        pattern: BadWord
        if len(new_description) > 500:
            raise CommandError(t.description_length)

        old = pattern.description
        pattern.description = new_description

        await ctx.message.add_reaction(name_to_emoji["white_check_mark"])
        await send_to_changelog(
            ctx.guild,
            t.log_description_updated(pattern.regex, old, new_description),
        )

    @update.command(name="regex", aliases=["r"])
    @docs(t.commands.update_regex)
    async def regex(self, ctx: Context, pattern: ContentFilterConverter, *, new_regex: str):
        pattern: BadWord

        old = pattern.regex
        pattern.regex = new_regex

        await ctx.message.add_reaction(name_to_emoji["white_check_mark"])
        await send_to_changelog(
            ctx.guild,
            t.log_regex_updated(pattern.regex, old, new_regex),
        )

    @update.command(name="delete_message", aliases=["del", "del_message", "dm"])
    @docs(t.commands.delete_message)
    async def delete_message(self, ctx: Context, pattern: ContentFilterConverter, delete: bool):
        pattern: BadWord
        pattern.delete = delete

        await ctx.message.add_reaction(name_to_emoji["white_check_mark"])
        await send_to_changelog(
            ctx.guild,
            t.log_delete_updated(pattern.delete, pattern.regex),
        )
