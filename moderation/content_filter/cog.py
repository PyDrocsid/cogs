import re

from discord import Message, Embed
from discord.ext import commands
from discord.ext.commands import guild_only, Context, CommandError, UserInputError

from PyDrocsid.cog import Cog
from PyDrocsid.command import reply, docs
from PyDrocsid.database import db, filter_by
from PyDrocsid.embeds import send_long_embed
from PyDrocsid.emojis import name_to_emoji
from PyDrocsid.events import StopEventHandling
from PyDrocsid.translations import t
from .colors import Colors
from .models import BadWordList, BadWordPost
from .permissions import ContentFilterPermission
from ...contributor import Contributor
from ...pubsub import send_to_changelog, send_alert, get_userlog_entries

tg = t.g
t = t.content_filter


async def contains_bad_word(message: Message) -> bool:
    author = message.author
    bad_list = await BadWordList.stream()

    if not bad_list:
        return False

    forbidden = []

    for bad_word in bad_list:

        check: re.Match = re.search(bad_word, message.content)

        if check:
            forbidden.append(bad_word)

    if forbidden:
        can_delete = message.channel.permissions_for(message.guild.me).manage_messages
        delete = False
        d = False

        for post in set(forbidden):
            call = await db.get(BadWordList, regex=post)

            if call.delete:
                delete = True
                if can_delete:
                    await message.delete()
                    break

        if delete and can_delete:
            d = True
            await send_alert(
                message.guild,
                t.log_forbidden_posted_deleted(
                    f"{author.mention} (`@{author}`, {author.id})",
                    message.channel.mention,
                    ", ".join(forbidden),
                ),
            )
        elif delete and not can_delete:
            d = False
            await send_alert(
                message.guild,
                t.log_forbidden_posted_not_deleted(
                    f"{author.mention} (`@{author}`, {author.id})",
                    message.channel.mention,
                    ", ".join(forbidden),
                ),
            )
        elif not delete:
            d = False
            await send_alert(
                message.guild,
                t.log_forbidden_posted(
                    f"{author.mention} (`@{author}`, {author.id})",
                    message.channel.mention,
                    ", ".join(forbidden),
                ),
            )

        if not d:
            await message.add_reaction(name_to_emoji["x"])

        for post in set(forbidden):
            await BadWordPost().create(author.id, author.name, message.channel.id, post, d)

        return True


async def check_message(message: Message):
    if message.guild is None or message.author.bot:
        return
    if await ContentFilterPermission.bypass.check_permissions(message.author):
        return
    if not await contains_bad_word(message):
        return

    raise StopEventHandling


class ContentFilterCog(Cog, name="Content Filter"):
    CONTRIBUTORS = [Contributor.NekoFanatic]

    @get_userlog_entries.subscribe
    async def handle_get_ulog_entries(self, user_id: int, _):
        out = []

        async for log in await db.stream(filter_by(BadWordPost, member=user_id)):  # type: BadWordPost
            if log.deleted:
                out.append((log.timestamp, t.ulog_message_deleted(log.content, log.channel)))
            else:
                out.append((log.timestamp, t.ulog_message(log.content, log.channel)))

        return out

    async def on_message(self, message: Message):
        await check_message(message)

    async def on_message_edit(self, _, after: Message):
        await check_message(after)

    @commands.group(name="content_filter", aliases=["cf"])
    @guild_only()
    @docs(t.commands.content_filter)
    @ContentFilterPermission.read.check
    async def content_filter(self, ctx: Context):

        if ctx.invoked_subcommand is None:
            raise UserInputError

    @content_filter.command(name="list", aliases=["l"])
    @docs(t.commands.list)
    @ContentFilterPermission.read.check
    async def list(self, ctx: Context):
        regex_list: list = await BadWordList.stream()

        out = False

        embed = Embed(
            title=t.bad_word_list_header,
            colour=Colors.ContentFilter,
        )

        for regex in regex_list:

            reg: BadWordList
            reg = await db.get(BadWordList, regex=regex)

            embed.add_field(
                name=t.embed_field_name(reg.id, reg.description),
                value=t.embed_field_value(reg.regex, "True" if reg.delete else "False"),
                inline=False,
            )

            out = True

        if not out:
            raise CommandError(t.no_pattern_listed)

        await send_long_embed(ctx, embed, paginate=True, max_fields=6)

    @content_filter.command(name="add", aliases=["+"])
    @docs(t.commands.add)
    @ContentFilterPermission.write.check
    async def add(self, ctx: Context, regex: str, delete: bool, *, description: str):

        if await db.get(BadWordList, regex=regex):
            raise CommandError(t.already_blacklisted)

        if len(description) > 500:
            raise CommandError(t.description_lengh)

        await BadWordList.add(ctx.author.id, regex, delete, description)

        embed = Embed(
            title=t.content_filter_added_header,
            description=t.content_filter_added(regex),
            colour=Colors.ContentFilter,
        )
        await reply(ctx, embed=embed)
        await send_to_changelog(ctx.guild, t.log_content_filter_added(regex, ctx.author.mention))

    @content_filter.command(name="remove", aliases=["-"])
    @docs(t.commands.remove)
    @ContentFilterPermission.write.check
    async def remove(self, ctx: Context, pattern_id: int):

        if not await BadWordList.exists(pattern_id):
            raise CommandError(t.not_blacklisted)

        regex = await BadWordList.remove(pattern_id)

        embed = Embed(
            title=t.content_filter_removed_header,
            description=t.content_filter_removed(regex.regex),
            colour=Colors.ContentFilter,
        )
        await reply(ctx, embed=embed)
        await send_to_changelog(ctx.guild, t.log_content_filter_removed(regex.regex, ctx.author.mention))

    @content_filter.group(name="update", aliases=["u"])
    @docs(t.commands.update)
    @ContentFilterPermission.write.check
    async def update(self, ctx: Context):

        if ctx.invoked_subcommand is None:
            raise UserInputError

    @update.command(name="description", aliases=["d"])
    @docs(t.commands.update_description)
    async def description(self, ctx: Context, pattern_id: int, *, new_description: str):

        if len(new_description) > 500:
            raise CommandError(t.description_lengh)

        if not await BadWordList.exists(pattern_id):
            raise CommandError(t.not_blacklisted)

        regex = await db.get(BadWordList, id=pattern_id)

        old = regex.description
        regex.description = new_description

        await reply(
            ctx,
            embed=Embed(
                title=t.pattern_updated,
                description=t.description_updated(new_description),
                color=Colors.ContentFilter,
            ),
        )
        await send_to_changelog(
            ctx.guild,
            t.log_description_updated(regex.regex, old, new_description),
        )

    @update.command(name="regex", aliases=["r"])
    @docs(t.commands.update_regex)
    async def regex(self, ctx: Context, pattern_id: int, new_regex):

        if not await BadWordList.exists(pattern_id):
            raise CommandError(t.not_blacklisted)

        regex = await db.get(BadWordList, id=pattern_id)

        old = regex.regex
        regex.regex = new_regex

        await reply(
            ctx,
            embed=Embed(
                title=t.pattern_updated,
                description=t.regex_updated(new_regex),
                color=Colors.ContentFilter,
            ),
        )
        await send_to_changelog(
            ctx.guild,
            t.log_regex_updated(regex.regex, old, new_regex),
        )

    @update.command(name="toggle_delete", aliases=["td"])
    @docs(t.commands.toggle_delete)
    async def toggle_delete(self, ctx: Context, pattern_id: int):

        if not await BadWordList.exists(pattern_id):
            raise CommandError(t.not_blacklisted)

        regex = await db.get(BadWordList, id=pattern_id)

        old: bool = regex.regex
        new = False if old else True

        regex.delete = new

        await reply(
            ctx,
            embed=Embed(
                title=t.pattern_updated,
                description=t.delete_updated(new),
                color=Colors.ContentFilter,
            ),
        )
        await send_to_changelog(
            ctx.guild,
            t.log_delete_updated(new, regex.regex),
        )
