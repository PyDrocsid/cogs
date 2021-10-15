import re
from urllib.request import urlopen

from discord import Embed
from discord.ext import commands
from discord.ext.commands import CommandError, Context, guild_only, UserInputError

from PyDrocsid.cog import Cog
from PyDrocsid.command import docs
from PyDrocsid.embeds import send_long_embed
from PyDrocsid.translations import t
from .colors import Colors
from .permissions import YouTubePermission
from .settings import YouTubeSettings
from ...contributor import Contributor
from ...pubsub import send_to_changelog

tg = t.g
t = t.youtube_search


async def get_ids(search: str):
    param = search.replace(" ", "+")
    html = urlopen(f"https://www.youtube.com/results?search_query={param}")
    video_ids = re.findall(r"watch\?v=(\S{11})", html.read().decode())
    ids = [video_ids[i] for i in range(await YouTubeSettings.amount_results.get())]

    return ids


class YouTubeSearchCog(Cog, name="YouTubeSearch"):
    CONTRIBUTORS = [Contributor.NekoFanatic]

    @commands.group(aliases=["yts"])
    @YouTubePermission.read.check
    @guild_only()
    @docs(t.commands.youtube_settings)
    async def youtube_settings(self, ctx: Context):

        if ctx.subcommand_passed is not None:
            if ctx.invoked_subcommand is None:
                raise UserInputError
            return

        embed = Embed(title=t.youtube, color=Colors.YouTube)

        amount_results = await YouTubeSettings.amount_results.get()
        embed.add_field(name=t.amount, value=t.x_pages(cnt=amount_results))

        await send_long_embed(ctx, embed, paginate=False)

    @youtube_settings.command()
    @YouTubePermission.write.check
    @guild_only()
    async def amount(self, ctx: Context, amount: int):

        if not 0 < amount < (1 << 20):
            raise CommandError(t.invalid_amount)

        await YouTubeSettings.amount_results.set(amount)
        embed = Embed(title=t.youtube, colour=Colors.YouTube, description=t.youtube_amount_set(cnt=amount))
        await send_long_embed(ctx, embed, paginate=False)
        await send_to_changelog(ctx.guild, t.log_youtube_amount_set(amount))

    @commands.command(aliases=["yt"])
    @docs(t.commands.youtube)
    @guild_only()
    async def youtube(self, ctx: Context, *, search: str):
        ids = await get_ids(search)
        print(ids)
