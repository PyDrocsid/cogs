import string
from typing import List, Union

from discord import Member, Embed, Role
from discord.ext import commands
from discord.ext.commands import guild_only, Context, CommandError, UserInputError

from PyDrocsid.cog import Cog
from PyDrocsid.command import reply
from PyDrocsid.database import db, select
from PyDrocsid.embeds import send_long_embed
from PyDrocsid.translations import t
from PyDrocsid.util import calculate_edit_distance
from .colors import Colors
from .models import BTPUser, BTPTopic
from .permissions import BeTheProfessionalPermission
from ...contributor import Contributor
from ...pubsub import send_to_changelog

tg = t.g
t = t.betheprofessional


def split_topics(topics: str) -> List[str]:
    return [topic for topic in map(str.strip, topics.replace(";", ",").split(",")) if topic]


async def split_parents(topics: List[str]) -> List[tuple[str, str, Union[BTPTopic, None]]]:
    result: List[tuple[str, str, Union[BTPTopic, None]]] = []
    for topic in topics:
        topic_tree = topic.split("/")
        if len(topic_tree) > 3 or len(topic_tree) < 2:
            raise CommandError(t.group_parent_format_help)
        group = topic_tree[0]
        query = select(BTPTopic).filter_by(name=topic_tree[1])
        parent: Union[BTPTopic, None, CommandError] = (
            (await db.first(query) if await db.exists(query) else CommandError(t.parent_not_exists(topic_tree[1])))
            if len(topic_tree) > 2
            else None
        )
        if isinstance(parent, CommandError):
            raise parent
        topic = topic_tree[-1]
        result.append((topic, group, parent))
    return result


async def parse_topics(topics_str: str) -> List[BTPTopic]:
    topics: List[BTPTopic] = []
    all_topics: List[BTPTopic] = await get_topics()
    for topic in split_topics(topics_str):
        query = select(BTPTopic).filter_by(name=topic)
        topic_db = await db.first(query)
        if not (await db.exists(query)) and len(all_topics) > 0:

            def dist(name: str) -> int:
                return calculate_edit_distance(name.lower(), topic.lower())

            best_match = min([r.name for r in all_topics], key=dist)
            if best_match:
                raise CommandError(t.topic_not_found_did_you_mean(topic, best_match))
            else:
                raise CommandError(t.topic_not_found(topic))
        elif not (await db.exists(query)):
            raise CommandError(t.no_topics_registered)
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
        topics: List[BTPTopic] = [
            topic
            for topic in await parse_topics(topics)
            if (await db.exists(select(BTPTopic).filter_by(id=topic.id)))
               and not (await db.exists(select(BTPUser).filter_by(user_id=member.id, topic=topic.id)))  # noqa: W503
        ]
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
        member: Member = ctx.author
        if topics.strip() == "*":
            topics: List[BTPTopic] = await get_topics()
        else:
            topics: List[BTPTopic] = await parse_topics(topics)
        affected_topics: List[BTPTopic] = []
        for topic in topics:
            if await db.exists(select(BTPUser).filter_by(user_id=member.id, topic=topic.id)):
                affected_topics.append(topic)

        for topic in affected_topics:
            await db.delete(topic)

        embed = Embed(title=t.betheprofessional, colour=Colors.BeTheProfessional)
        embed.description = t.topics_removed(cnt=len(affected_topics))
        await reply(ctx, embed=embed)

    @commands.command(name="*")
    @BeTheProfessionalPermission.manage.check
    @guild_only()
    async def register_topics(self, ctx: Context, *, topics: str):
        """
        register one or more new topics
        """

        names = split_topics(topics)
        topics: List[tuple[str, str, Union[BTPTopic, None]]] = await split_parents(names)
        if not names or not topics:
            raise UserInputError

        valid_chars = set(string.ascii_letters + string.digits + " !#$%&'()+-./:<=>?[\\]^_`{|}~")
        registered_topics: List[tuple[str, str, Union[BTPTopic, None]]] = []
        for topic in topics:
            if any(c not in valid_chars for c in topic[0]):
                raise CommandError(t.topic_invalid_chars(topic))

            if await db.exists(select(BTPTopic).filter_by(name=topic[0])):
                raise CommandError(
                    t.topic_already_registered(f"{topic[1]}/{topic[2].name + '/' if topic[2] else ''}{topic[0]}"),
                )
            else:
                registered_topics.append(topic)

        for registered_topic in registered_topics:
            await BTPTopic.create(
                registered_topic[0],
                None,
                registered_topic[1],
                registered_topic[2].id if registered_topic[2] is not None else None,
            )

        embed = Embed(title=t.betheprofessional, colour=Colors.BeTheProfessional)
        embed.description = t.topics_registered(cnt=len(registered_topics))
        await send_to_changelog(
            ctx.guild,
            t.log_topics_registered(
                cnt=len(registered_topics),
                topics=", ".join(f"`{r[0]}`" for r in registered_topics),
            ),
        )
        await reply(ctx, embed=embed)

    @commands.command(name="/")
    @BeTheProfessionalPermission.manage.check
    @guild_only()
    async def delete_topics(self, ctx: Context, *, topics: str):
        """
        delete one or more topics
        """

        topics: List[str] = split_topics(topics)

        delete_topics: list[BTPTopic] = []

        for topic in topics:
            if not await db.exists(select(BTPTopic).filter_by(name=topic)):
                raise CommandError(t.topic_not_registered(topic))
            else:
                btp_topic = await db.first(select(BTPTopic).filter_by(name=topic))
                delete_topics.append(btp_topic)
                for child_topic in await db.all(
                        select(BTPTopic).filter_by(parent=btp_topic.id),
                ):  # TODO Recursive? Fix more level childs
                    delete_topics.insert(0, child_topic)
        for topic in delete_topics:
            if topic.role_id is not None:
                role: Role = ctx.guild.get_role(topic.role_id)
                await role.delete()
            for user_topic in await db.all(select(BTPUser).filter_by(topic=topic.id)):
                await db.delete(user_topic)
                await db.commit()
            await db.delete(topic)

        embed = Embed(title=t.betheprofessional, colour=Colors.BeTheProfessional)
        embed.description = t.topics_unregistered(cnt=len(delete_topics))
        await send_to_changelog(
            ctx.guild,
            t.log_topics_unregistered(cnt=len(delete_topics), topics=", ".join(f"`{r}`" for r in delete_topics)),
        )
        await send_long_embed(ctx, embed)
