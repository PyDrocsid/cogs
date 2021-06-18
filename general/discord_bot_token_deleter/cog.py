import re

from discord import Message, Embed, Forbidden, NotFound, HTTPException

from PyDrocsid.cog import Cog
from PyDrocsid.material_colors import MaterialColors
from PyDrocsid.translations import t
from ...contributor import Contributor
from ...pubsub import send_alert

tg = t.g
t = t.discord_bot_token_deleter


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
        await message.channel.send(message.author.mention, embed=embed)
        try:
            await message.delete()
        except (Forbidden, NotFound, HTTPException) as error:
            await send_alert(message.guild, f"Discord Bot Token deletion Error: {error}")
