from PyDrocsid.cog import Cog
from PyDrocsid.converter import UserMemberConverter
from PyDrocsid.database import db, filter_by, select
from PyDrocsid.embeds import send_long_embed
from PyDrocsid.emojis import name_to_emoji
from PyDrocsid.translations import t
from cogs.library.moderation.user_notes.models import UserNote
from cogs.library.moderation.user_notes.permissions import UserNotePermission
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

    @commands.group()
    @guild_only()
    @UserNotePermission.read.check
    @docs(t.description)
    async def user_note(self, ctx: Context):

        if ctx.invoked_subcommand is None:
            raise UserInputError

    @user_note.command(name="add")
    @UserNotePermission.write.check
    async def add_user_note(self, ctx: Context, member: UserMemberConverter, *, message: str):
        await UserNote.create(
            member=member.id,
            author=ctx.author.id,
            message=message,
        )
        await ctx.message.add_reaction(name_to_emoji["white_check_mark"])
        await send_to_changelog(ctx.guild, t.new_note(member.mention, f"<@{ctx.author.id}>", message))

    @user_note.command(name="remove")
    @UserNotePermission.write.check
    async def remove_user_note(self, ctx: Context, message_id: int):
        user_note: UserNote = await db.get(UserNote, message_id=message_id)
        if not user_note:
            raise CommandError(t.note_not_found)
        await db.delete(user_note)
        await ctx.message.add_reaction(name_to_emoji["white_check_mark"])
        await send_to_changelog(
            ctx.guild,
            t.removed_note(f"<@{user_note.member}>", f"<@{user_note.author}>", user_note.message),
        )

    @user_note.command(name="show")
    async def show_user_note(self, ctx: Context, member: UserMemberConverter):
        embed = Embed(title=t.user_notes, colour=Colors.user_notes)
        async for note in await db.stream(select(UserNote).filter_by(member=member.id)):
            embed.add_field(name=t.id, value=note.message_id, inline=True)
            embed.add_field(name=t.message, value=note.message, inline=True)
            embed.add_field(name=t.timestamp, value=note.timestamp.strftime("%d.%m.%Y %H:%M:%S"), inline=True)
            embed.add_field(name=t.author, value=f"<@{note.author}>", inline=True)
        await send_long_embed(ctx, embed)
