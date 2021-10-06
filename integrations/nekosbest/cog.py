from discord import Embed
from discord.ext import commands
from discord.ext.commands import Context, guild_only

from PyDrocsid.cog import Cog
from PyDrocsid.command import docs
from PyDrocsid.embeds import send_long_embed
from PyDrocsid.translations import t
from .colors import Colors
from ...contributor import Contributor

from nekosbest import Client

tg = t.g
t = t.nekosbest


class NekosBestCog(Cog, name="NekosBest"):
    CONTRIBUTORS = [Contributor.NekoFanatic]

    @commands.command(name="nekos")
    @docs(t.commands.neko)
    async def neko(self, ctx: Context):
        nekos = await Client().get_image("nekos")

        embed = Embed(title="Sauce", url=nekos.source_url, color=Colors.NekosBest)
        embed.set_image(url=nekos.url)
        embed.set_author(name=nekos.artist_name, url=nekos.artist_href)

        await send_long_embed(ctx, embed, paginate=False)
