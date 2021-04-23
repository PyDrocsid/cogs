from PyDrocsid.emojis import name_to_emoji
from discord import Member, Embed

from PyDrocsid.database import db, filter_by

from PyDrocsid.config import Contributor
from discord.ext import commands
from discord.ext.commands import Context, UserInputError

from PyDrocsid.cog import Cog
from cogs.library.moderation.mod.permissions import ModPermission
from cogs.library.moderation.user_notes.models import UserNote
from PyDrocsid.translations import t
from cogs.library.moderation.user_notes.permissions import UserNotePermissions

t = t.user_notes


class UserNoteCog(Cog, name="User notes"):
    CONTRIBUTORS = [Contributor.Florian]

    @commands.group()
    async def user_note(self, ctx: Context):
        """
        mange notes for users
        """

        if ctx.invoked_subcommand is None:
            raise UserInputError

    @user_note.command(name="add")
    @UserNotePermissions.mange_user_notes.check
    async def add_user_note(self, ctx: Context, member: Member, *, message: str):
        await UserNote.create(
            member=member.id,
            applicant=member.mention,
            message=message,
        )
        await ctx.message.add_reaction(name_to_emoji["white_check_mark"])

    @user_note.command(name="remove")
    @UserNotePermissions.mange_user_notes.check
    async def remove_user_note(self, ctx: Context, message_id: str):
        user_notes = await db.get(UserNote, message_id=message_id)
        if user_notes:
            await db.delete(user_notes)
            await ctx.message.add_reaction(name_to_emoji["white_check_mark"])

    @user_note.command(name="show")
    @UserNotePermissions.mange_user_notes.check
    async def show_user_note(self, ctx: Context, member: Member):
        user_notes = await db.all(filter_by(UserNote, member=member.id))
        embed = Embed(title=t.user_info)
        for note in user_notes:
            embed.add_field(name=t.id, value=note.message_id, inline=True)
            embed.add_field(name=t.message, value=note.message, inline=True)
            embed.add_field(name=t.timestamp, value=note.timestamp.strftime("%d.%m.%Y %H:%M:%S"), inline=True)
            embed.add_field(name=t.applicant, value=note.applicant, inline=True)
        await ctx.send(embed=embed)
