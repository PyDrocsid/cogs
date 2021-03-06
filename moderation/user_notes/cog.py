from typing import Optional, Union

from discord import Embed, User, Member
from discord.ext import commands
from discord.ext.commands import Context, UserInputError, guild_only, CommandError

from PyDrocsid.cog import Cog
from PyDrocsid.command import confirm, docs
from PyDrocsid.converter import UserMemberConverter
from PyDrocsid.database import db, select
from PyDrocsid.embeds import send_long_embed
from PyDrocsid.emojis import name_to_emoji
from PyDrocsid.translations import t
from .colors import Colors
from .models import UserNote
from .permissions import UserNotePermission
from ...contributor import Contributor
from ...pubsub import send_to_changelog

tg = t.g
t = t.user_notes


class UserNoteCog(Cog, name="User Notes"):
    CONTRIBUTORS = [Contributor.Florian, Contributor.Defelo]

    @commands.group(aliases=["un"])
    @UserNotePermission.read.check
    @guild_only()
    @docs(t.commands.user_notes)
    async def user_notes(self, ctx: Context):
        if ctx.invoked_subcommand is None:
            raise UserInputError

    @user_notes.command(name="show", aliases=["s", "list", "l"])
    @docs(t.commands.user_notes_show)
    async def user_notes_show(self, ctx: Context, *, member: UserMemberConverter):
        member: Union[User, Member]

        embed = Embed(title=t.user_notes, colour=Colors.user_notes)
        note: UserNote
        async for note in await db.stream(select(UserNote).filter_by(member_id=member.id)):
            embed.add_field(
                name=note.timestamp.strftime("%d.%m.%Y %H:%M:%S"),
                value=t.user_note_entry(id=note.id, author=f"<@{note.author_id}>", content=note.content),
                inline=False,
            )

        if not embed.fields:
            embed.colour = Colors.error
            embed.description = t.no_notes

        await send_long_embed(ctx, embed, paginate=True)

    @user_notes.command(name="add", aliases=["a", "+"])
    @UserNotePermission.write.check
    @docs(t.commands.user_notes_add)
    async def user_notes_add(self, ctx: Context, member: UserMemberConverter, *, content: str):
        member: Union[User, Member]

        if len(content) > 1000:
            raise CommandError(t.too_long)

        await UserNote.create(member.id, ctx.author.id, content)
        await send_to_changelog(ctx.guild, t.new_note(ctx.author.mention, member.mention, content))
        await ctx.message.add_reaction(name_to_emoji["white_check_mark"])

    @user_notes.command(name="remove", aliases=["r", "delete", "d", "-"])
    @UserNotePermission.write.check
    @docs(t.commands.user_notes_remove)
    async def user_notes_remove(self, ctx: Context, note_id: int):
        user_note: Optional[UserNote] = await db.get(UserNote, id=note_id)
        if not user_note:
            raise CommandError(t.note_not_found)

        conf_embed = Embed(
            title=t.confirmation,
            description=t.confirm(
                f"<@{user_note.member_id}>",
                user_note.content,
            ),
        )
        async with confirm(ctx, conf_embed) as (result, _):
            if not result:
                conf_embed.description += "\n\n" + t.canceled
                return
            conf_embed.description += "\n\n" + t.confirmed

        await db.delete(user_note)
        await send_to_changelog(
            ctx.guild,
            t.removed_note(ctx.author.mention, f"<@{user_note.member_id}>", user_note.content),
        )
