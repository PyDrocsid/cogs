from datetime import datetime
from typing import Optional, List

from aiohttp import ClientSession
from discord import Embed, TextChannel
from discord.ext import commands, tasks
from discord.ext.commands import guild_only, Context, CommandError, UserInputError

from PyDrocsid.cog import Cog
from PyDrocsid.command import reply
from PyDrocsid.config import Config
from PyDrocsid.database import db, select, filter_by, db_wrapper
from PyDrocsid.logger import get_logger
from PyDrocsid.translations import t
from PyDrocsid.util import check_message_send_permissions
from .colors import Colors
from .models import RedditPost, RedditChannel
from .permissions import RedditPermission
from .settings import RedditSettings
from ...contributor import Contributor
from ...pubsub import send_to_changelog, send_alert

tg = t.g
t = t.reddit

logger = get_logger(__name__)


async def exists_subreddit(subreddit: str) -> bool:
    async with ClientSession() as session, session.get(
        # raw_json=1 as parameter to get unicode characters instead of html escape sequences
        f"https://www.reddit.com/r/{subreddit}/about.json?raw_json=1",
        headers={"User-agent": f"{Config.NAME}/{Config.VERSION}"},
    ) as response:
        return response.ok


async def get_subreddit_name(subreddit: str) -> str:
    async with ClientSession() as session, session.get(
        # raw_json=1 as parameter to get unicode characters instead of html escape sequences
        f"https://www.reddit.com/r/{subreddit}/about.json?raw_json=1",
        headers={"User-agent": f"{Config.NAME}/{Config.VERSION}"},
    ) as response:
        return (await response.json())["data"]["display_name"]


async def fetch_reddit_posts(subreddit: str, limit: int) -> Optional[List[dict]]:
    async with ClientSession() as session, session.get(
        # raw_json=1 as parameter to get unicode characters instead of html escape sequences
        f"https://www.reddit.com/r/{subreddit}/hot.json?raw_json=1",
        headers={"User-agent": f"{Config.NAME}/{Config.VERSION}"},
        params={"limit": str(limit)},
    ) as response:
        if response.status != 200:
            return None

        data = (await response.json())["data"]

    posts: List[dict] = []
    for post in data["children"]:
        # t3 = link
        if post["kind"] == "t3" and post["data"].get("post_hint") == "image":
            posts.append(
                {
                    "id": post["data"]["id"],
                    "author": post["data"]["author"],
                    "title": post["data"]["title"],
                    "created_utc": post["data"]["created_utc"],
                    "score": post["data"]["score"],
                    "num_comments": post["data"]["num_comments"],
                    "permalink": post["data"]["permalink"],
                    "url": post["data"]["url"],
                    "subreddit": post["data"]["subreddit"],
                },
            )
    return posts


def create_embed(post: dict) -> Embed:
    embed = Embed(
        # add a blank character after every : and . to prevent wrong redirects for titles
        title=post["title"].replace(":", ":\u200b").replace(".", ".\u200b"),
        url=f"https://reddit.com{post['permalink']}",
        description=f"{post['score']} :thumbsup: \u00B7 {post['num_comments']} :speech_balloon:",
        colour=Colors.Reddit,  # Reddit's brand color
    )
    embed.set_author(name=f"u/{post['author']}", url=f"https://reddit.com/u/{post['author']}")
    embed.set_image(url=post["url"])
    embed.set_footer(text=f"r/{post['subreddit']}")
    embed.timestamp = datetime.utcfromtimestamp(post["created_utc"])
    return embed


class RedditCog(Cog, name="Reddit"):
    CONTRIBUTORS = [Contributor.Scriptim, Contributor.Defelo, Contributor.wolflu, Contributor.Anorak]

    async def on_ready(self):
        interval = await RedditSettings.interval.get()
        await self.start_loop(interval)

    @tasks.loop()
    @db_wrapper
    async def reddit_loop(self):
        await self.pull_hot_posts()

    async def pull_hot_posts(self):
        logger.info("pulling hot reddit posts")
        limit = await RedditSettings.limit.get()
        async for reddit_channel in await db.stream(select(RedditChannel)):  # type: RedditChannel
            text_channel: Optional[TextChannel] = self.bot.get_channel(reddit_channel.channel)
            if text_channel is None:
                await db.delete(reddit_channel)
                continue

            try:
                check_message_send_permissions(text_channel, check_embed=True)
            except CommandError:
                await send_alert(self.bot.guilds[0], t.cannot_send(text_channel.mention))
                continue

            posts = await fetch_reddit_posts(reddit_channel.subreddit, limit)
            if posts is None:
                await send_alert(self.bot.guilds[0], t.could_not_fetch(reddit_channel.subreddit))
                continue

            for post in posts:
                if await RedditPost.post(post["id"]):
                    await text_channel.send(embed=create_embed(post))

        await RedditPost.clean()

    async def start_loop(self, interval):
        self.reddit_loop.cancel()
        self.reddit_loop.change_interval(hours=interval)
        try:
            self.reddit_loop.start()
        except RuntimeError:
            self.reddit_loop.restart()

    @commands.group()
    @RedditPermission.read.check
    @guild_only()
    async def reddit(self, ctx: Context):
        """
        manage reddit integration
        """

        if ctx.subcommand_passed is not None:
            if ctx.invoked_subcommand is None:
                raise UserInputError
            return

        embed = Embed(title=t.reddit, colour=Colors.Reddit)

        interval = await RedditSettings.interval.get()
        embed.add_field(name=t.interval, value=t.x_hours(cnt=interval))

        limit = await RedditSettings.limit.get()
        embed.add_field(name=t.limit, value=str(limit))

        out = []
        async for reddit_channel in await db.stream(select(RedditChannel)):  # type: RedditChannel
            text_channel: Optional[TextChannel] = self.bot.get_channel(reddit_channel.channel)
            if text_channel is None:
                await db.delete(reddit_channel)
            else:
                sub = reddit_channel.subreddit
                out.append(f":small_orange_diamond: [r/{sub}](https://reddit.com/r/{sub}) -> {text_channel.mention}")
        embed.add_field(name=t.reddit_links, value="\n".join(out) or t.no_reddit_links, inline=False)

        await reply(ctx, embed=embed)

    @reddit.command(name="add", aliases=["a", "+"])
    @RedditPermission.write.check
    async def reddit_add(self, ctx: Context, subreddit: str, channel: TextChannel):
        """
        create a link between a subreddit and a channel
        """

        if not await exists_subreddit(subreddit):
            raise CommandError(t.subreddit_not_found)

        check_message_send_permissions(channel, check_embed=True)

        subreddit = await get_subreddit_name(subreddit)
        if await db.exists(filter_by(RedditChannel, subreddit=subreddit, channel=channel.id)):
            raise CommandError(t.reddit_link_already_exists)

        await RedditChannel.create(subreddit, channel.id)
        embed = Embed(title=t.reddit, colour=Colors.Reddit, description=t.reddit_link_created)
        await reply(ctx, embed=embed)
        await send_to_changelog(ctx.guild, t.log_reddit_link_created(subreddit, channel.mention))

    @reddit.command(name="remove", aliases=["r", "del", "d", "-"])
    @RedditPermission.write.check
    async def reddit_remove(self, ctx: Context, subreddit: str, channel: TextChannel):
        """
        remove a reddit link
        """

        subreddit = await get_subreddit_name(subreddit)
        link: Optional[RedditChannel] = await db.get(RedditChannel, subreddit=subreddit, channel=channel.id)
        if link is None:
            raise CommandError(t.reddit_link_not_found)

        await db.delete(link)
        embed = Embed(title=t.reddit, colour=Colors.Reddit, description=t.reddit_link_removed)
        await reply(ctx, embed=embed)
        await send_to_changelog(ctx.guild, t.log_reddit_link_removed(subreddit, channel.mention))

    @reddit.command(name="interval", aliases=["int", "i"])
    @RedditPermission.write.check
    async def reddit_interval(self, ctx: Context, hours: int):
        """
        change lookup interval (in hours)
        """

        if not 0 < hours < (1 << 31):
            raise CommandError(t.invalid_interval)

        await RedditSettings.interval.set(hours)
        await self.start_loop(hours)
        embed = Embed(title=t.reddit, colour=Colors.Reddit, description=t.reddit_interval_set)
        await reply(ctx, embed=embed)
        await send_to_changelog(ctx.guild, t.log_reddit_interval_set(cnt=hours))

    @reddit.command(name="limit", aliases=["lim"])
    @RedditPermission.write.check
    async def reddit_limit(self, ctx: Context, limit: int):
        """
        change limit of posts to be sent concurrently
        """

        if not 0 < limit < (1 << 31):
            raise CommandError(t.invalid_limit)

        await RedditSettings.limit.set(limit)
        embed = Embed(title=t.reddit, colour=Colors.Reddit, description=t.reddit_limit_set)
        await reply(ctx, embed=embed)
        await send_to_changelog(ctx.guild, t.log_reddit_limit_set(limit))

    @reddit.command(name="trigger", aliases=["t"])
    @RedditPermission.trigger.check
    async def reddit_trigger(self, ctx: Context):
        """
        pull hot posts now and reset the timer
        """

        await self.start_loop(await RedditSettings.interval.get())
        embed = Embed(title=t.reddit, colour=Colors.Reddit, description=t.done)
        await reply(ctx, embed=embed)
