import logging
import string
from collections import Counter
from typing import List, Union, Optional, Dict

from discord import Member, Embed, Role, Message, Guild
from discord.ext import commands, tasks
from discord.ext.commands import guild_only, Context, CommandError, UserInputError

from PyDrocsid.cog import Cog
from PyDrocsid.command import reply
from PyDrocsid.database import db, select, db_wrapper
from PyDrocsid.embeds import send_long_embed
from PyDrocsid.translations import t
from PyDrocsid.util import calculate_edit_distance
from .colors import Colors
from .models import BTPUser, BTPTopic
from .permissions import BeTheProfessionalPermission
from ...contributor import Contributor
from ...pubsub import send_to_changelog
from PyDrocsid.logger import get_logger

tg = t.g
t = t.betheprofessional

logger = get_logger(__name__)


def split_topics(topics: str) -> List[str]:
    return [topic for topic in map(str.strip, topics.replace(";", ",").split(",")) if topic]


async def split_parents(topics: List[str], assignable: bool) -> List[tuple[str, bool, Optional[list[BTPTopic]]]]:
    result: List[tuple[str, bool, Optional[list[BTPTopic]]]] = []
    for topic in topics:
        topic_tree = topic.split("/")

        parents: List[Union[BTPTopic, None, CommandError]] = [
            await db.first(select(BTPTopic).filter_by(name=topic))
            if await db.exists(select(BTPTopic).filter_by(name=topic))
            else CommandError(t.parent_not_exists(topic))
            for topic in topic_tree[:-1]
        ]

        parents = [parent for parent in parents if parent is not None]
        for parent in parents:
            if isinstance(parent, CommandError):
                raise parent

        topic = topic_tree[-1]
        result.append((topic, assignable, parents))
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

    async def on_ready(self):
        self.update_roles.start()

    @commands.command(name="?")
    @guild_only()
    async def list_topics(self, ctx: Context, parent_topic: Optional[str]):
        """
        list all registered topics
        """
        parent: Union[BTPTopic, None, CommandError] = (
            None
            if parent_topic is None
            else await db.first(select(BTPTopic).filter_by(name=parent_topic))
                 or CommandError(t.topic_not_found(parent_topic))  # noqa: W503
        )
        if isinstance(parent, CommandError):
            raise parent

        embed = Embed(title=t.available_topics_header, colour=Colors.BeTheProfessional)
        sorted_topics: Dict[str, List[str]] = {}
        topics: List[BTPTopic] = await db.all(select(BTPTopic).filter_by(parent=None if parent is None else parent.id))
        if not topics:
            embed.colour = Colors.error
            embed.description = t.no_topics_registered
            await reply(ctx, embed=embed)
            return

        topics.sort(key=lambda btp_topic: btp_topic.name.lower())
        root_topic: Union[BTPTopic, None] = (
            None if parent_topic is None else await db.first(select(BTPTopic).filter_by(name=parent_topic))
        )
        for topic in topics:
            if (root_topic.name if root_topic is not None else "Topics") not in sorted_topics.keys():
                sorted_topics[root_topic.name if root_topic is not None else "Topics"] = [f"{topic.name}"]
            else:
                sorted_topics[root_topic.name if root_topic is not None else "Topics"].append(f"{topic.name}")

        for root_topic in sorted_topics.keys():
            embed.add_field(
                name=root_topic.title(),
                value=", ".join(
                    [
                        f"`{topic.name}"
                        + (  # noqa: W503
                            f" ({c})`"
                            if (c := await db.count(select(BTPTopic).filter_by(parent=topic.id))) > 0
                            else "`"
                        )
                        for topic in topics
                    ],
                ),
                inline=False,
            )
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
            await db.delete(await db.first(select(BTPUser).filter_by(topic=topic.id)))

        embed = Embed(title=t.betheprofessional, colour=Colors.BeTheProfessional)
        embed.description = t.topics_removed(cnt=len(affected_topics))
        await reply(ctx, embed=embed)

    @commands.command(name="*")
    @BeTheProfessionalPermission.manage.check
    @guild_only()
    async def register_topics(self, ctx: Context, *, topics: str, assignable: bool = True):
        """
        register one or more new topics
        """

        names = split_topics(topics)
        topics: List[tuple[str, bool, Optional[list[BTPTopic]]]] = await split_parents(names, assignable)
        if not names or not topics:
            raise UserInputError

        valid_chars = set(string.ascii_letters + string.digits + " !#$%&'()+-./:<=>?[\\]^_`{|}~")
        registered_topics: List[tuple[str, bool, Optional[list[BTPTopic]]]] = []
        for topic in topics:
            if any(c not in valid_chars for c in topic[0]):
                raise CommandError(t.topic_invalid_chars(topic))

            if await db.exists(
                    select(BTPTopic).filter_by(name=topic[0], parent=topic[2][-1].id if len(topic[2]) > 0 else None),
            ):
                raise CommandError(
                    t.topic_already_registered(f"{topic[1]}/{topic[2][-1].name + '/' if topic[1] else ''}{topic[0]}"),
                )
            else:
                registered_topics.append(topic)

        for registered_topic in registered_topics:
            await BTPTopic.create(
                registered_topic[0],
                None,
                True,
                registered_topic[2][-1].id if len(registered_topic[2]) > 0 else None,
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

    @commands.command()
    @guild_only()
    async def topic(self, ctx: Context, topic_name: str, message: Optional[Message]):
        topic: BTPTopic = await db.first(select(BTPTopic).filter_by(name=topic_name))
        mention: str
        if topic is None:
            raise CommandError(t.topic_not_found(topic_name))
        if topic.role_id is not None:
            mention = ctx.guild.get_role(topic.role_id).mention
        else:
            topic_members: List[BTPUser] = await db.all(select(BTPUser).filter_by(topic=topic.id))
            members: List[Member] = [ctx.guild.get_member(member.user_id) for member in topic_members]
            mention = ', '.join(map(lambda m: m.mention, members))

        if mention == '':
            raise CommandError(t.nobody_has_topic(topic_name))
        if message is None:
            await ctx.send(mention)
        else:
            await message.reply(mention)

    @tasks.loop(seconds=30)  # SET hours to 24 in Prod
    @db_wrapper
    # TODO Change to Config
    async def update_roles(self):
        logger.info('Started Update Role Loop')
        topic_count: List[int] = []
        for topic in await db.all(select(BTPTopic)):
            for _ in range(await db.count(select(BTPUser).filter_by(topic=topic.id))):
                topic_count.append(topic.id)
        topic_count: Counter = Counter(topic_count)
        top_topics: List[int] = []
        for topic_count in sorted(topic_count)[:(100 if len(topic_count) >= 100 else len(topic_count))]:
            top_topics.append(topic_count)
        for topic in await db.all(select(BTPTopic).filter(BTPTopic.role_id != None)):  # noqa: E711
            if topic.id not in top_topics:
                await self.bot.guilds[0].get_role(topic.role_id).delete()
        for top_topic in top_topics:
            if (topic := await db.first(select(BTPTopic).filter(BTPTopic.id == top_topic, BTPTopic.role_id == None))) is not None:  # noqa: E711
                topic.role_id = (await self.bot.guilds[0].create_role(name=topic.name)).id
        logger.info('Created Top Topic Roles')
