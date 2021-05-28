from asyncio import gather
from datetime import datetime, timedelta
from typing import Optional, List

import requests
from discord import Embed, TextChannel, Guild
from discord.ext import commands, tasks
from discord.ext.commands import guild_only, Context, CommandError, UserInputError

from PyDrocsid.cog import Cog
from PyDrocsid.command import reply
from PyDrocsid.config import Config
from PyDrocsid.database import db, select, filter_by, db_wrapper
from PyDrocsid.logger import get_logger
from PyDrocsid.translations import t
from .colors import Colors
from .models import RedditPost, RedditChannel
from .permissions import RedditPermission
from .settings import RedditSettings
from ...contributor import Contributor
from ...pubsub import send_to_changelog

tg = t.g
t = t.reddit

logger = get_logger(__name__)


def exists_subreddit(subreddit: str) -> bool:
    return requests.head(
        # raw_json=1 as parameter to get unicode characters instead of html escape sequences
        f"https://www.reddit.com/r/{subreddit}/hot.json?raw_json=1",
        headers={"User-agent": f"MorpheusHelper/{Config.VERSION}"},
    ).ok


def get_subreddit_name(subreddit: str) -> str:
    return requests.get(
        # raw_json=1 as parameter to get unicode characters instead of html escape sequences
        f"https://www.reddit.com/r/{subreddit}/about.json?raw_json=1",
        headers={"User-agent": f"MorpheusHelper/{Config.VERSION}"},
    ).json()["data"]["display_name"]


def fetch_reddit_posts(subreddit: str, limit: int) -> List[dict]:
    response = requests.get(
        # raw_json=1 as parameter to get unicode characters instead of html escape sequences
        f"https://www.reddit.com/r/{subreddit}/hot.json?raw_json=1",
        headers={"User-agent": f"{Config.NAME}/{Config.VERSION}"},
        params={"limit": str(limit)},
    )

    if not response.ok:
        logger.warning("could not fetch reddit posts of r/%s - %s - %s", subreddit, response.status_code, response.text)
        return []

    posts: List[dict] = []
    for post in response.json()["data"]["children"]:
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
        try:
            self.reddit_loop.start()
        except RuntimeError:
            self.reddit_loop.restart()

    @tasks.loop(hours=1)
    async def reddit_loop(self):
        await gather(*[self.pull_hot_posts(guild) for guild in self.bot.guilds])
        await RedditPost.clean()

    @db_wrapper
    async def pull_hot_posts(self, guild: Guild, force: bool = False):
        interval = await RedditSettings.limit.get(guild)

        if not force and await db.exists(
            select(RedditPost).filter(
                RedditPost.timestamp > datetime.utcnow() - timedelta(hours=interval, minutes=-10),
            ),
        ):
            return

        logger.info("pulling hot reddit posts for %s (%s)", guild.name, guild.id)
        limit = await RedditSettings.limit.get(guild)
        reddit_channel: RedditChannel
        async for reddit_channel in await db.stream(select(RedditChannel).filter_by(guild_id=guild.id)):
            text_channel: Optional[TextChannel] = guild.get_channel(reddit_channel.channel)
            if text_channel is None:
                await db.delete(reddit_channel)
                continue

            for post in fetch_reddit_posts(reddit_channel.subreddit, limit):
                if await RedditPost.post(guild.id, post["id"]):
                    await text_channel.send(embed=create_embed(post))

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

        interval = await RedditSettings.interval.get(ctx.guild)
        embed.add_field(name=t.interval, value=t.x_hours(cnt=interval))

        limit = await RedditSettings.limit.get(ctx.guild)
        embed.add_field(name=t.limit, value=str(limit))

        out = []
        reddit_channel: RedditChannel
        async for reddit_channel in await db.stream(select(RedditChannel).filter_by(guild_id=ctx.guild.id)):
            text_channel: Optional[TextChannel] = ctx.guild.get_channel(reddit_channel.channel)
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

        guild: Guild = channel.guild

        if not exists_subreddit(subreddit):
            raise CommandError(t.subreddit_not_found)
        if not channel.permissions_for(guild.me).send_messages:
            raise CommandError(t.reddit_link_not_created_permission)

        subreddit = get_subreddit_name(subreddit)
        if await db.exists(filter_by(RedditChannel, subreddit=subreddit, channel=channel.id, guild_id=guild.id)):
            raise CommandError(t.reddit_link_already_exists)

        await RedditChannel.create(subreddit, channel.id, guild.id)
        embed = Embed(title=t.reddit, colour=Colors.Reddit, description=t.reddit_link_created)
        await reply(ctx, embed=embed)
        await send_to_changelog(ctx.guild, t.log_reddit_link_created(subreddit, channel.mention))

    @reddit.command(name="remove", aliases=["r", "del", "d", "-"])
    @RedditPermission.write.check
    async def reddit_remove(self, ctx: Context, subreddit: str, channel: TextChannel):
        """
        remove a reddit link
        """

        guild: Guild = channel.guild

        subreddit = get_subreddit_name(subreddit)
        link: Optional[RedditChannel] = await db.get(
            RedditChannel,
            subreddit=subreddit,
            channel=channel.id,
            guild_id=guild.id,
        )
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
            raise CommandError(tg.invalid_interval)

        await RedditSettings.interval.set(ctx.guild, hours)
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

        await RedditSettings.limit.set(ctx.guild, limit)
        embed = Embed(title=t.reddit, colour=Colors.Reddit, description=t.reddit_limit_set)
        await reply(ctx, embed=embed)
        await send_to_changelog(ctx.guild, t.log_reddit_limit_set(limit))

    @reddit.command(name="trigger", aliases=["t"])
    @RedditPermission.trigger.check
    async def reddit_trigger(self, ctx: Context):
        """
        pull hot posts now and reset the timer
        """

        await self.pull_hot_posts(ctx.guild, force=True)
        embed = Embed(title=t.reddit, colour=Colors.Reddit, description=t.done)
        await reply(ctx, embed=embed)
