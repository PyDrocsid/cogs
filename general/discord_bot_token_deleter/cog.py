import base64
import binascii
import re

from aiohttp import ClientSession
from discord import Embed, Forbidden, Message

from PyDrocsid.cog import Cog
from PyDrocsid.material_colors import MaterialColors
from PyDrocsid.translations import t

from ...contributor import Contributor
from ...pubsub import send_alert

tg = t.g
t = t.discord_bot_token_deleter


class DiscordBotTokenDeleterCog(Cog, name="Discord Bot Token Deleter"):
    CONTRIBUTORS = [Contributor.Tert0, Contributor.Defelo]
    RE_DC_TOKEN = re.compile(r"([A-Za-z\d\-_]+)\.[A-Za-z\d\-_]+\.[A-Za-z\d\-_]+")

    async def on_message(self, message: Message):
        """Delete a message if it contains a Discord bot token"""

        if message.author.id == self.bot.user.id or not message.guild:
            return

        for match in self.RE_DC_TOKEN.finditer(message.content):
            try:
                if not base64.urlsafe_b64decode(match.group(1)).isdigit():
                    continue
            except binascii.Error:
                continue

            async with ClientSession() as session, session.get(
                "https://discord.com/api/users/@me", headers={"Authorization": f"Bot {match.group(0)}"}
            ) as response:
                if response.ok:
                    break
        else:
            return

        embed = Embed(title=t.title, colour=MaterialColors.bluegrey, description=t.description)
        await message.channel.send(message.author.mention, embed=embed)
        try:
            await message.delete()
        except Forbidden:
            await send_alert(message.guild, t.not_deleted(message.jump_url, message.channel.mention))
