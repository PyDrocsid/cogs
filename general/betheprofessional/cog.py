import string
from typing import List, Union

from discord import Role, Guild, Member, Embed
from discord.ext import commands
from discord.ext.commands import guild_only, Context, CommandError, UserInputError

from PyDrocsid.cog import Cog
from PyDrocsid.command import reply
from PyDrocsid.database import db, select
from PyDrocsid.embeds import send_long_embed
from PyDrocsid.translations import t
from PyDrocsid.util import calculate_edit_distance, check_role_assignable
from .colors import Colors
from .models import BTPUser, BTPTopic
from .permissions import BeTheProfessionalPermission
from ...contributor import Contributor
from ...pubsub import send_to_changelog

tg = t.g
t = t.betheprofessional


def split_topics(topics: str) -> List[str]:
    return [topic for topic in map(str.strip, topics.replace(";", ",").split(",")) if topic]


async def parse_topics(topics_str: str, author: Member) -> List[BTPTopic]:
    # TODO

    topics: List[BTPTopic] = []
    all_topics: List[BTPTopic] = await get_topics()
    for topic in split_topics(topics_str):
        query = select(BTPTopic).filter_by(name=topic)
        topic_db = await db.first(query)
        if not (await db.exists(query)):
            def dist(name: str) -> int:
                return calculate_edit_distance(name.lower(), topic.lower())

            best_match = min([r.name for r in all_topics], key=dist)
            if best_match:
                raise CommandError(t.topic_not_found_did_you_mean(topic, best_match))
            else:
                raise CommandError(t.topic_not_found(topic))
        topics.append(topic_db)
    return topics


async def get_topics() -> List[BTPTopic]:
    topics: List[BTPTopic] = []
    async for topic in await db.stream(select(BTPTopic)):
        topics.append(topic)
    return topics


class BeTheProfessionalCog(Cog, name="Self Assignable Topic Roles"):
    CONTRIBUTORS = [Contributor.Defelo, Contributor.wolflu, Contributor.MaxiHuHe04, Contributor.AdriBloober]

    @commands.command(name="?")
    @guild_only()
    async def list_topics(self, ctx: Context):
        """
        list all registered topics
        """

        embed = Embed(title=t.available_topics_header, colour=Colors.BeTheProfessional)
        out = [topic.name for topic in await get_topics()]
        if not out:
            embed.colour = Colors.error
            embed.description = t.no_topics_registered
            await reply(ctx, embed=embed)
            return

        out.sort(key=str.lower)
        embed.description = ", ".join(f"`{topic}`" for topic in out)
        await send_long_embed(ctx, embed)

    @commands.command(name="+")
    @guild_only()
    async def assign_topics(self, ctx: Context, *, topics: str):
        """
        add one or more topics (comma separated) you are interested in
        """

        member: Member = ctx.author
        topics: List[BTPTopic] = [topic for topic in await parse_topics(topics, ctx.author)]  # TODO check if user has it already
        for topic in topics:
            await BTPUser.create(member.id, topic.id)
        embed = Embed(title=t.betheprofessional, colour=Colors.BeTheProfessional)
        embed.description = t.topics_added(cnt=len(topics))
        if not topics:
            embed.colour = Colors.error

        await reply(ctx, embed=embed)

    @commands.command(name="-")
    @guild_only()
    async def unassign_topics(self, ctx: Context, *, topics: str):
        """
        remove one or more topics (use * to remove all topics)
        """

        # TODO

        member: Member = ctx.author
        if topics.strip() == "*":
            topics: List[BTPTopic] = await get_topics()
        else:
            topics: List[BTPTopic] = await parse_topics(ctx.guild, topics, ctx.author)
        # TODO Check if user has
        for topic in topics:
            user_has_topic = False
            for user_topic in db.all(select(BTPUser).filter_by(user_id=member.id)):
                if user_topic.id == topic.id:
                    user_has_topic = True
            if not user_has_topic:
                raise CommandError("you have da topic not")  # TODO
        for topic in topics:
            await db.delete(topic)

        embed = Embed(title=t.betheprofessional, colour=Colors.BeTheProfessional)
        embed.description = t.topics_removed(cnt=len(topics))
        await reply(ctx, embed=embed)

    @commands.command(name="*")
    @BeTheProfessionalPermission.manage.check
    @guild_only()
    async def register_topics(self, ctx: Context, *, topics: str):
        """
        register one or more new topics
        """

        names = split_topics(topics)
        if not names:
            raise UserInputError

        valid_chars = set(string.ascii_letters + string.digits + " !#$%&'()+-./:<=>?[\\]^_`{|}~")
        registered_topics: list[tuple[str, Union[BTPTopic, None]]] = []
        for topic in names:
            if any(c not in valid_chars for c in topic):
                raise CommandError(t.topic_invalid_chars(topic))

            if await db.exists(select(BTPTopic).filter_by(name=topic)):
                raise CommandError(t.topic_already_registered(topic))
            else:
                registered_topics.append((topic, None))

        for registered_topic in registered_topics:
            await BTPTopic.create(registered_topic[0], None, registered_topic[1])

        embed = Embed(title=t.betheprofessional, colour=Colors.BeTheProfessional)
        embed.description = t.topics_registered(cnt=len(registered_topics))
        await send_to_changelog(
            ctx.guild,
            t.log_topics_registered(cnt=len(registered_topics), topics=", ".join(f"`{r}`" for r in registered_topics)),
        )
        await reply(ctx, embed=embed)

    @commands.command(name="/")
    @BeTheProfessionalPermission.manage.check
    @guild_only()
    async def delete_topics(self, ctx: Context, *, topics: str):
        """
        delete one or more topics
        """

        topics = split_topics(topics)

        delete_topics: list[BTPTopic] = []

        for topic in topics:
            if not await db.exists(select(BTPTopic).filter_by(name=topic)):
                raise CommandError(t.topic_not_registered(topic))
            else:
                delete_topics.append(await db.first(select(BTPTopic).filter_by(name=topic)))

        for topic in delete_topics:
            await db.delete(topic)  # TODO Delete Role

        embed = Embed(title=t.betheprofessional, colour=Colors.BeTheProfessional)
        embed.description = t.topics_unregistered(cnt=len(delete_topics))
        await send_to_changelog(
            ctx.guild,
            t.log_topics_unregistered(cnt=len(delete_topics), topics=", ".join(f"`{r}`" for r in delete_topics)),
        )
        await send_long_embed(ctx, embed)
