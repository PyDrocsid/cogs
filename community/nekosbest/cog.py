import aiohttp

from discord import Embed
from discord.ext import commands
from discord.ext.commands import Context

from PyDrocsid.cog import Cog
from PyDrocsid.command import docs
from PyDrocsid.embeds import send_long_embed
from PyDrocsid.translations import t

from .colors import Colors
from ...contributor import Contributor


tg = t.g
t = t.nekosbest


async def get_endpoints() -> list:
    async with aiohttp.ClientSession() as session:
        resp = await session.get("https://nekos.best/api/v2/endpoints")
        endpoints: dict = await resp.json()

        return list(endpoints.keys())


async def get_request(endpoint: str) -> dict | None:
    async with aiohttp.ClientSession() as session:
        resp = await session.get(f"https://nekos.best/api/v2/{endpoint}")
        result: dict = await resp.json()
        try:
            return result["results"][0]
        except KeyError:
            return None


class NekosBestCog(Cog, name="NekosBest"):
    CONTRIBUTORS = [Contributor.NekoFanatic]

    @commands.command(name="nekosbest", aliases=["nb"])
    @docs(t.commands.nekosbest)
    async def nekosbest(self, ctx: Context, endpoint: str | None = None):
        result: dict = await get_request(endpoint)

        if result:
            if "anime_name" in result:
                embed = Embed(title=endpoint, description=result["anime_name"], color=Colors.NekosBest)
            else:
                embed = Embed(
                    title=endpoint,
                    description=t.description(result["source_url"], result["artist_name"], result["artist_href"]),
                    color=Colors.NekosBest,
                )
            embed.set_image(url=result["url"])

        else:
            endpoints = await get_endpoints()
            embed = Embed(
                title=t.endpoints, description=t.endpoint_list("`, `".join(endpoints)), color=Colors.NekosBest
            )

        await send_long_embed(ctx.channel, embed)
