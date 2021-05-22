from discord import Member, Embed
from discord.ext import commands
from discord.ext.commands import Context, UserInputError, guild_only

from PyDrocsid.cog import Cog
from PyDrocsid.command import UserCommandError
from PyDrocsid.config import Contributor
from PyDrocsid.converter import UserMemberConverter
from PyDrocsid.database import db, filter_by
from PyDrocsid.embeds import send_long_embed
from PyDrocsid.emojis import name_to_emoji
from PyDrocsid.translations import t
from cogs.library.moderation.user_notes.models import UserNote
from cogs.library.moderation.user_notes.permissions import UserNotePermission
from library.PyDrocsid.command import docs

t = t.user_notes


class UserNoteCog(Cog, name="User notes"):
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
            author=ctx.author.mention,
            message=message,
        )
        await ctx.message.add_reaction(name_to_emoji["white_check_mark"])

    @user_note.command(name="remove")
    @UserNotePermission.write.check
    async def remove_user_note(self, ctx: Context, message_id: str):
        user_notes = await db.get(UserNote, message_id=message_id)
        if not user_notes:
            raise UserCommandError(t.message_not_found)
        await db.delete(user_notes)
        await ctx.message.add_reaction(name_to_emoji["white_check_mark"])

    @user_note.command(name="show")
    async def show_user_note(self, ctx: Context, member: UserMemberConverter):
        user_notes = await db.all(filter_by(UserNote, member=member.id))
        embed = Embed(title=t.user_notes)
        for note in user_notes:
            embed.add_field(name=t.id, value=note.message_id, inline=True)
            embed.add_field(name=t.message, value=note.message, inline=True)
            embed.add_field(name=t.timestamp, value=note.timestamp.strftime("%d.%m.%Y %H:%M:%S"), inline=True)
            embed.add_field(name=t.author, value=note.author, inline=True)
        await send_long_embed(ctx, embed)
