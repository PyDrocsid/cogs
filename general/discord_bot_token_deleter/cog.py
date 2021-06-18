import re

from discord import Message, Embed, Forbidden, NotFound, HTTPException

from PyDrocsid.cog import Cog
from PyDrocsid.logger import get_logger
from PyDrocsid.material_colors import MaterialColors
from PyDrocsid.translations import t
from ...contributor import Contributor

tg = t.g
t = t.discord_bot_token_deleter
logger = get_logger(__name__)


class DiscordBotTokenDeleter(Cog, name="DiscordBotTokenDeleter"):
    CONTRIBUTORS = [Contributor.Tert0]
    RE_DC_TOKEN = re.compile(r"[A-Za-z\d]{24}\.[A-Za-z\d]{6}\.[A-Za-z\d\-\_]{27}")

    async def on_message(self, message: Message):
        """
        deletes a message if it contains a discord bot token
        """
        if message.author.id == self.bot.user.id:
            return
        if not self.RE_DC_TOKEN.findall(message.content):
            return
        embed = Embed(title=t.title, colour=MaterialColors.bluegrey)
        embed.description = t.description
        embed.set_footer(text=tg.requested_by(message.author, message.author.id), icon_url=message.author.avatar_url)
        await message.channel.send(embed=embed)
        try:
            await message.delete()
        except (Forbidden, NotFound, HTTPException) as error:
            logger.error(error)
