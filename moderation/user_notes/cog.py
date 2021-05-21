from discord import Member, Embed
from discord.ext import commands
from discord.ext.commands import Context, UserInputError, guild_only

from PyDrocsid.cog import Cog
from PyDrocsid.config import Contributor
from PyDrocsid.database import db, filter_by
from PyDrocsid.emojis import name_to_emoji
from PyDrocsid.translations import t
from cogs.library.moderation.user_notes.models import UserNote
from cogs.library.moderation.user_notes.permissions import UserNotePermissions

t = t.user_notes


class UserNoteCog(Cog, name="User notes"):
    CONTRIBUTORS = [Contributor.Florian]

    @commands.group()
    @docs(t.user_notes)
    async def user_note(self, ctx: Context):

        if ctx.invoked_subcommand is None:
            raise UserInputError

    @user_note.command(name="add")
    @UserNotePermissions.write.check
    async def add_user_note(self, ctx: Context, member: Member, *, message: str):
        await UserNote.create(
            member=member.id,
            author=ctx.author.mention,
            message=message,
        )
        await ctx.message.add_reaction(name_to_emoji["white_check_mark"])

    @user_note.command(name="remove")
    @UserNotePermissions.write.check
    async def remove_user_note(self, ctx: Context, message_id: str):
        user_notes = await db.get(UserNote, message_id=message_id)
        if user_notes:
            await db.delete(user_notes)
            await ctx.message.add_reaction(name_to_emoji["white_check_mark"])

    @user_note.command(name="show")
    async def show_user_note(self, ctx: Context, member: Member):
        user_notes = await db.all(filter_by(UserNote, member=member.id))
        embed = Embed(title=t.user_info)
        for note in user_notes:
            embed.add_field(name=t.id, value=note.message_id, inline=True)
            embed.add_field(name=t.message, value=note.message, inline=True)
            embed.add_field(name=t.timestamp, value=note.timestamp.strftime("%d.%m.%Y %H:%M:%S"), inline=True)
            embed.add_field(name=t.author, value=note.author, inline=True)
        await ctx.send(embed=embed)
