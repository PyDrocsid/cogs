from discord import Member, Embed

from PyDrocsid.database import db, filter_by

from PyDrocsid.config import Contributor
from discord.ext import commands
from discord.ext.commands import Context, UserInputError

from PyDrocsid.cog import Cog
from cogs.library.moderation.user_notes.models import UserNote
from PyDrocsid.translations import t

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
    async def add_user_note(self, ctx: Context, member: Member, *, message: str):
        await UserNote.create(
            member=member.id,
            message=message
        )

    @user_note.command(name="remove")
    async def remove_user_note(self, ctx: Context, id: int):
        user_notes = await db.get(UserNote, id=id)
        if user_notes:
            await db.delete(user_notes)

    @user_note.command(name="show")
    async def show_user_note(self, ctx: Context, member: Member):
        user_notes = await db.all(filter_by(UserNote, member=member.id))
        embed = Embed(title=t.user_info)
        for note in user_notes:
            embed.add_field(name=t.id, value=note.id, inline=True)
            embed.add_field(name=t.message, value=note.message, inline=True)
            embed.add_field(name=t.timestamp, value=note.timestamp.strftime("%d.%m.%Y %H:%M:%S"), inline=True)
        await ctx.send(embed=embed)
