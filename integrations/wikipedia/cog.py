from discord import Member
from discord.embeds import Embed
from discord.ext import commands
from PyDrocsid.cog import Cog
from discord.ext.commands.context import Context
from PyDrocsid.async_thread import run_in_thread
from PyDrocsid.util import send_long_embed
from wikipedia.exceptions import WikipediaException, DisambiguationError, PageError  # skipcq: PYL-E501
from wikipedia import summary
from .colors import Colors


def make_embed(title: str, content: str, color, requested_by: Member) -> Embed:
    embed = Embed(title=title, description=content, color=color)
    embed.set_footer(
        text=f"Requested by {requested_by} ({requested_by.id})",
        icon_url=requested_by.avatar_url,
    )
    return embed


# Note: wikipedia allows bots, but only bots that are responsible
# (not going too fast).
class WikipediaCog(Cog, name="Wikipedia"):
    CONTRIBUTORS = []

    @commands.command(usage="<topic>", aliases=["wiki"])
    @commands.cooldown(5, 10, commands.BucketType.user)
    async def wikipedia(self, ctx: Context, *, title: str):
        """
        display wikipedia summary about a topic
        """

        try:
            c_summary = await run_in_thread(summary, title)

        # this error occurs when the topic searched for has not been found,
        # but there are suggestions
        except DisambiguationError as err:
            await ctx.send(
                embed=make_embed(
                    title=f"{title} was not found!",
                    content=str(err),
                    color=Colors.Wiki,
                    requested_by=ctx.author,
                ),
            )

        # this error occurs when the topic searched has not been found
        # and there are no suggestions
        except PageError as err:
            await ctx.send(
                embed=make_embed(
                    title=title,
                    content=str(err),
                    color=Colors.Wiki,
                    requested_by=ctx.author,
                ),
            )

        # WikipediaException is the base exception of all exceptions
        # of the wikipedia module
        # if an error occurs that has not been caught above
        # it may mean that wikipedia hasn't responded correctly or not at all
        except WikipediaException:
            await ctx.send(
                embed=make_embed(
                    title=title,
                    content="Wikipedia is not available currently!" 
                            " Try again later.",
                    color=Colors.Wiki,
                    requested_by=ctx.author,
                ),
            )

        else:
            await send_long_embed(
                ctx.channel,
                embed=make_embed(
                    title=title,
                    content=c_summary,
                    color=Colors.Wiki,
                    requested_by=ctx.author,
                ),
            )
