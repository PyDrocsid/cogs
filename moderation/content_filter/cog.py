import re

from discord import Embed, Forbidden, Message
from discord.ext import commands
from discord.ext.commands import guild_only, Context, Converter, CommandError, UserInputError

from PyDrocsid.cog import Cog
from PyDrocsid.command import confirm, docs, add_reactions
from PyDrocsid.database import db, filter_by, select
from PyDrocsid.embeds import send_long_embed
from PyDrocsid.emojis import name_to_emoji
from PyDrocsid.events import StopEventHandling
from PyDrocsid.translations import t
from .colors import Colors
from .models import BadWord, BadWordPost, sync_redis
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

        if not row:
            raise CommandError(t.not_blacklisted)

        return row


class RegexConverter(Converter):
    async def convert(self, ctx: Context, argument: str) -> str:
        try:
            re.compile(argument)
        except re.error:
            raise CommandError(t.invalid_regex)

        return argument


def findall(regex: str, text: str) -> list[str]:
    return [match[0] for match in re.finditer(regex, text)]


async def check_message(message: Message) -> None:
    author = message.author

    if message.guild is None:
        return
    if await ContentFilterPermission.bypass.check_permissions(author):
        return

    violation_regexs: set[str] = set()
    violation_matches: set[str] = set()
    for regex in await BadWord.get_all_redis():
        if not (matches := findall(regex, message.content)):
            continue

        violation_regexs.add(regex)
        violation_matches.update(matches)

    if not violation_regexs:
        return

    delete_message = False
    bad_word_ids: set = set()
    for regex in violation_regexs:
        if bad_word := await db.get(BadWord, regex=regex):
            if bad_word.delete:
                delete_message = True
            bad_word_ids.add(str(bad_word.id))

    was_deleted = False
    if delete_message:
        try:
            await message.delete()
        except Forbidden:
            log_text = t.log_forbidden_posted_not_deleted
        else:
            was_deleted = True
            log_text = t.log_forbidden_posted_deleted
    else:
        log_text = t.log_forbidden_posted

    last_posted = await BadWordPost.last_posted(message.id, violation_matches)
    if last_posted[1] and not last_posted[0]:
        await send_alert(
            message.guild,
            log_text(
                f"{author.mention} (`@{author}`, {author.id})",
                message.jump_url,
                message.channel.mention,
                ", ".join(last_posted[1]),
                ", ".join(sorted(bad_word_ids)),
            ),
        )

        for post in violation_matches:
            await BadWordPost.create(author.id, author.name, message.channel.id, post, was_deleted)

        if was_deleted:
            raise StopEventHandling

        await message.add_reaction(name_to_emoji["warning"])


class ContentFilterCog(Cog, name="Content Filter"):
    CONTRIBUTORS = [Contributor.NekoFanatic, Contributor.Defelo]

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

    @commands.group(name="content_filter", aliases=["cf"])
    @ContentFilterPermission.read.check
    @guild_only()
    @docs(t.commands.content_filter)
    async def content_filter(self, ctx: Context):
        if ctx.subcommand_passed is not None:
            if ctx.invoked_subcommand is None:
                raise UserInputError
            return

        embed = Embed(title=t.bad_word_list_header, colour=Colors.ContentFilter)

        reg: BadWord
        async for reg in await db.stream(select(BadWord)):
            embed.add_field(
                name=t.embed_field_name(reg.id, reg.description),
                value=t.embed_field_value(reg.regex, t.delete if reg.delete else t.not_delete),
                inline=False,
            )

        if not embed.fields:
            embed.colour = Colors.error
            embed.description = t.no_pattern_listed

        await send_long_embed(ctx, embed, paginate=True, max_fields=6)

    @content_filter.command(name="add", aliases=["a", "+"])
    @ContentFilterPermission.write.check
    @docs(t.commands.add)
    async def add(self, ctx: Context, regex: RegexConverter, delete: bool, *, description: str):
        regex: str

        if await db.exists(filter_by(BadWord, regex=regex)):
            raise CommandError(t.already_blacklisted)

        if len(description) > 500:
            raise CommandError(t.description_length)

        await BadWord.create(regex, description, delete)
        await add_reactions(ctx.message, "white_check_mark")
        await send_to_changelog(ctx.guild, t.log_content_filter_added(regex, ctx.author.mention))

    @content_filter.command(name="remove", aliases=["del", "r", "d", "-"])
    @ContentFilterPermission.write.check
    @docs(t.commands.remove)
    async def remove(self, ctx: Context, pattern: ContentFilterConverter):
        pattern: BadWord

        conf_embed = Embed(title=t.confirm, description=t.confirm_text(pattern.regex, pattern.description))
        async with confirm(ctx, conf_embed, danger=True) as (result, msg):
            if not result:
                return
            if msg:
                await msg.delete(delay=5)

        await pattern.remove()
        await add_reactions(ctx.message, "white_check_mark")
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

        await add_reactions(ctx.message, "white_check_mark")
        await send_to_changelog(ctx.guild, t.log_description_updated(pattern.regex, old, new_description))

    @update.command(name="regex", aliases=["r"])
    @docs(t.commands.update_regex)
    async def regex(self, ctx: Context, pattern: ContentFilterConverter, *, new_regex: RegexConverter):
        pattern: BadWord
        new_regex: str

        if await db.exists(filter_by(BadWord, regex=new_regex)):
            raise CommandError(t.already_blacklisted)

        old = pattern.regex
        pattern.regex = new_regex
        await sync_redis()

        await add_reactions(ctx.message, "white_check_mark")
        await send_to_changelog(ctx.guild, t.log_regex_updated(old, pattern.regex))

    @update.command(name="delete_message", aliases=["del", "del_message", "dm"])
    @docs(t.commands.delete_message)
    async def delete_message(self, ctx: Context, pattern: ContentFilterConverter, delete: bool):
        pattern: BadWord
        pattern.delete = delete

        await add_reactions(ctx.message, "white_check_mark")
        await send_to_changelog(ctx.guild, t.log_delete_updated(pattern.delete, pattern.regex))

    @content_filter.command(name="check", aliases=["c"])
    @ContentFilterPermission.read.check
    @docs(t.commands.check)
    async def check(self, ctx: Context, pattern: ContentFilterConverter | int | RegexConverter, *, test_string: str):
        filters: list[BadWord | str]
        if isinstance(pattern, (BadWord, str)):
            filters = [pattern]
        elif pattern == -1:
            filters = await db.all(select(BadWord))
        else:
            raise CommandError(t.invalid_pattern)

        out = []
        for rule in filters:
            regex = rule.regex if isinstance(rule, BadWord) else rule
            if not (matches := findall(regex, test_string)):
                continue

            line = f"{rule.id}: " if isinstance(rule, BadWord) else ""
            line += f'`{regex}` -> {", ".join(f"`{m}`" for m in sorted(set(matches)))}'
            out.append(line)

        embed = Embed(title=t.checked_expressions, description=f"**{test_string}**", color=Colors.ContentFilter)
        embed.add_field(name=t.matches, value="\n".join(out) or t.no_matches)

        await send_long_embed(ctx, embed, paginate=True)
