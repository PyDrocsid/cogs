from discord import TextChannel
from discord.ext import commands
from discord.ext.commands import Context

from PyDrocsid.cog import Cog
from cogs.library.contributor import Contributor


class DeleteOldMessagesCog(Cog):
    CONTRIBUTORS = [Contributor.Florian]

    @commands.command(name="delete_old_messages")
    async def delete_old_messages(self, ctx: Context, channel: TextChannel, days: int):
        """
        Delete old messages every hour in a channel that have reached a certain age of days
        """
