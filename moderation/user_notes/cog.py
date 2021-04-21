from PyDrocsid.config import Contributor
from discord.ext import commands
from discord.ext.commands import Context, UserInputError

from PyDrocsid.cog import Cog


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
    async def add_user_note(self, ctx: Context):
        pass

    @user_note.command(name="remove")
    async def remove_user_note(self):
        pass

    @user_note.command(name="show")
    async def show_user_note(self):
        pass
