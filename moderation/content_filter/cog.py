import re

from discord import Message, Embed
from discord.ext import commands
from discord.ext.commands import guild_only, Context, CommandError, UserInputError

from PyDrocsid.cog import Cog
from PyDrocsid.command import docs
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


async def check_message(message: Message):
    author = message.author

    if message.guild is None:
        return
    if await ContentFilterPermission.bypass.check_permissions(author):
        return

    bad_word_list = await BadWord.get_all()

    if not bad_word_list:
        return

    forbidden = []

    for bad_word in bad_word_list:

        if re.search(bad_word, message.content):
            forbidden.append(bad_word)

    if forbidden:
        can_delete = message.channel.permissions_for(message.guild.me).manage_messages
        has_to_be_deleted = False
        was_deleted = False

        for post in set(forbidden):
            call = await db.get(BadWord, regex=post)

            if call.delete:
                has_to_be_deleted = True
                if can_delete:
                    await message.delete()
                    break

        log_text = None

        if has_to_be_deleted and can_delete:
            was_deleted = True
            log_text = t.log_forbidden_posted_deleted

        elif has_to_be_deleted and not can_delete:
            log_text = t.log_forbidden_posted_not_deleted

        elif not has_to_be_deleted:
            log_text = t.log_forbidden_posted

        await send_alert(
            message.guild,
            log_text(
                f"{author.mention} (`@{author}`, {author.id})",
                message.jump_url,
                message.channel.mention,
                ", ".join(forbidden),
            ),
        )

        if not was_deleted:
            await message.add_reaction(name_to_emoji["warning"])

        for post in set(forbidden):
            await BadWordPost.create(author.id, author.name, message.channel.id, post, was_deleted)

        raise StopEventHandling


class ContentFilterCog(Cog, name="Content Filter"):
    CONTRIBUTORS = [Contributor.NekoFanatic]

    @get_userlog_entries.subscribe
    async def handle_get_ulog_entries(self, user_id: int, _):
        out = []

        log: BadWordPost
        async for log in await db.stream(filter_by(BadWordPost, member=user_id)):
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
    @ContentFilterPermission.read.check
    @guild_only()
    @docs(t.commands.content_filter)
    async def content_filter(self, ctx: Context):

        if ctx.invoked_subcommand is None:
            raise UserInputError

    @content_filter.command(name="list", aliases=["l"])
    @docs(t.commands.list)
    async def list(self, ctx: Context):
        regex_list: list = await BadWord.get_all()

        out = False

        embed = Embed(
            title=t.bad_word_list_header,
            colour=Colors.ContentFilter,
        )

        reg: BadWord
        for reg in regex_list:

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
    @ContentFilterPermission.write.check
    @docs(t.commands.add)
    async def add(self, ctx: Context, regex: str, delete: bool, *, description: str):

        if await db.exists(filter_by(BadWord, regex=regex)):
            raise CommandError(t.already_blacklisted)

        if len(description) > 500:
            raise CommandError(t.description_length)

        await BadWord.create(ctx.author.id, regex, delete, description)

        await ctx.message.add_reaction(name_to_emoji["white_check_mark"])

        await send_to_changelog(ctx.guild, t.log_content_filter_added(regex, ctx.author.mention))

    @content_filter.command(name="remove", aliases=["-"])
    @ContentFilterPermission.write.check
    @docs(t.commands.remove)
    async def remove(self, ctx: Context, pattern_id: int):

        if not await db.exists(filter_by(BadWord, id=pattern_id)):
            raise CommandError(t.not_blacklisted)

        regex = await BadWord.remove(pattern_id)

        await ctx.message.add_reaction(name_to_emoji["white_check_mark"])

        await send_to_changelog(ctx.guild, t.log_content_filter_removed(regex.regex, ctx.author.mention))

    @content_filter.group(name="update", aliases=["u"])
    @ContentFilterPermission.write.check
    @docs(t.commands.update)
    async def update(self, ctx: Context):

        if ctx.invoked_subcommand is None:
            raise UserInputError

    @update.command(name="description", aliases=["d"])
    @docs(t.commands.update_description)
    async def description(self, ctx: Context, pattern_id: int, *, new_description: str):

        if len(new_description) > 500:
            raise CommandError(t.description_length)

        if not await db.exists(filter_by(BadWord, id=pattern_id)):
            raise CommandError(t.not_blacklisted)

        regex = await db.get(BadWord, id=pattern_id)

        old = regex.description
        regex.description = new_description

        await ctx.message.add_reaction(name_to_emoji["white_check_mark"])

        await send_to_changelog(
            ctx.guild,
            t.log_description_updated(regex.regex, old, new_description),
        )

    @update.command(name="regex", aliases=["r"])
    @docs(t.commands.update_regex)
    async def regex(self, ctx: Context, pattern_id: int, new_regex):

        if not await db.exists(filter_by(BadWord, id=pattern_id)):
            raise CommandError(t.not_blacklisted)

        regex = await db.get(BadWord, id=pattern_id)

        old = regex.regex
        regex.regex = new_regex

        await ctx.message.add_reaction(name_to_emoji["white_check_mark"])

        await send_to_changelog(
            ctx.guild,
            t.log_regex_updated(regex.regex, old, new_regex),
        )

    @update.command(name="toggle_delete", aliases=["td"])
    @docs(t.commands.toggle_delete)
    async def toggle_delete(self, ctx: Context, pattern_id: int):

        if not await db.exists(filter_by(BadWord, id=pattern_id)):
            raise CommandError(t.not_blacklisted)

        regex = await db.get(BadWord, id=pattern_id)

        regex.delete = not regex.delete

        await ctx.message.add_reaction(name_to_emoji["white_check_mark"])

        await send_to_changelog(
            ctx.guild,
            t.log_delete_updated(regex.delete, regex.regex),
        )
