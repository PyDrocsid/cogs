from typing import Optional

from PyDrocsid.cog import Cog
from PyDrocsid.converter import UserMemberConverter
from PyDrocsid.database import db, filter_by, select
from PyDrocsid.embeds import send_long_embed
from PyDrocsid.emojis import name_to_emoji
from PyDrocsid.translations import t

from PyDrocsid.command import confirm
from .models import UserNote
from .permissions import UserNotePermission
from discord import Embed
from discord.ext import commands
from discord.ext.commands import Context, UserInputError, guild_only, CommandError
from PyDrocsid.command import docs

from .colors import Colors
from ...contributor import Contributor
from ...pubsub import send_to_changelog

t = t.user_notes


class UserNoteCog(Cog, name="User Notes"):
    CONTRIBUTORS = [Contributor.Florian]

    @commands.group(aliases=["un"])
    @UserNotePermission.read.check
    @guild_only()
    @docs(t.command.description)
    async def user_notes(self, ctx: Context):

        if ctx.invoked_subcommand is None:
            raise UserInputError

    @user_notes.command(name="add", aliases=["a"])
    @UserNotePermission.write.check
    @docs(t.add_user_note)
    async def add_user_note(self, ctx: Context, member: UserMemberConverter, *, message: str):
        await UserNote.create(
            member=member.id,
            author=ctx.author.id,
            message=message,
        )
        await ctx.message.add_reaction(name_to_emoji["white_check_mark"])
        await send_to_changelog(ctx.guild, t.new_note(member.mention, f"<@{ctx.author.id}>", message))

    @user_notes.command(name="remove", aliases=["r"])
    @UserNotePermission.write.check
    @docs(t.remove_user_note)
    async def remove_user_note(self, ctx: Context, message_id: int):
        user_note: Optional[UserNote] = await db.get(UserNote, message_id=message_id)
        if not user_note:
            raise CommandError(t.note_not_found)
        conf_embed = Embed(title=t.confirmation, description=t.confirm(user_note.message, f"<@{user_note.member}>"))
        async with confirm(ctx, conf_embed) as (result, msg):
            if not result:
                conf_embed.description += "\n\n" + t.canceled
                return

            conf_embed.description += "\n\n" + t.confirmed
            if msg:
                await db.delete(user_note)

    @user_notes.command(name="show", aliases=["s"])
    @docs(t.show_user_note)
    async def show_user_note(self, ctx: Context, member: UserMemberConverter):
        embed = Embed(title=t.user_notes, colour=Colors.user_notes)
        async for note in await db.stream(select(UserNote).filter_by(member=member.id)):
            embed.add_field(name=t.id, value=note.message_id, inline=True)
            embed.add_field(name=t.message, value=note.message, inline=True)
            embed.add_field(name=t.timestamp, value=note.timestamp.strftime("%d.%m.%Y %H:%M:%S"), inline=True)
            embed.add_field(name=t.author, value=f"<@{note.author}>", inline=True)
        await send_long_embed(ctx, embed, paginate=True)
