import string

from discord import Member, Embed, Role, Message
from discord.ext import commands, tasks
from discord.ext.commands import guild_only, Context, CommandError, UserInputError

import PyDrocsid.embeds
from PyDrocsid.cog import Cog
from PyDrocsid.command import reply
from PyDrocsid.database import db, select, db_wrapper, filter_by
from PyDrocsid.embeds import send_long_embed
from PyDrocsid.environment import CACHE_TTL
from PyDrocsid.logger import get_logger
from PyDrocsid.redis import redis
from PyDrocsid.translations import t
from PyDrocsid.util import calculate_edit_distance
from .colors import Colors
from .models import BTPUser, BTPTopic
from .permissions import BeTheProfessionalPermission
from .settings import BeTheProfessionalSettings
from ...contributor import Contributor
from ...pubsub import send_to_changelog, send_alert

tg = t.g
t = t.betheprofessional

logger = get_logger(__name__)

LEADERBOARD_TABLE_SPACING = 2


def split_topics(topics: str) -> list[str]:
    return [topic for topic in map(str.strip, topics.replace(";", ",").split(",")) if topic]


async def split_parents(topics: list[str], assignable: bool) -> list[tuple[str, bool, list[BTPTopic]] | None]:
    result: list[tuple[str, bool, list[BTPTopic]] | None] = []
    for topic in topics:
        topic_tree = topic.split("/")

        parents: list[BTPTopic | None | CommandError] = [
            await db.first(filter_by(BTPTopic, name=topic))

            if await db.exists(filter_by(BTPTopic, name=topic))
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


async def parse_topics(topics_str: str) -> list[BTPTopic]:
    topics: list[BTPTopic] = []
    all_topics: list[BTPTopic] = await get_topics()

    if len(all_topics) == 0:
        raise CommandError(t.no_topics_registered)

    for topic_name in split_topics(topics_str):
        topic = await db.first(filter_by(BTPTopic, name=topic_name))

        if topic is None and len(all_topics) > 0:

            def dist(name: str) -> int:
                return calculate_edit_distance(name.lower(), topic_name.lower())

            best_dist, best_match = min((dist(r.name), r.name) for r in all_topics)
            if best_dist <= 5:
                raise CommandError(t.topic_not_found_did_you_mean(topic_name, best_match))

            raise CommandError(t.topic_not_found(topic_name))
        elif topic is None:
            raise CommandError(t.no_topics_registered)
        topics.append(topic)

    return topics


async def get_topics() -> list[BTPTopic]:
    topics: list[BTPTopic] = []
    async for topic in await db.stream(select(BTPTopic)):
        topics.append(topic)
    return topics


async def change_setting(ctx: Context, name: str, value: any):
    data = t.settings[name]
    await getattr(BeTheProfessionalSettings, data["internal_name"]).set(value)

    embed = Embed(title=t.betheprofessional, color=Colors.green)
    embed.description = data["updated"].format(value)

    await reply(ctx, embed=embed)
    await send_to_changelog(ctx.guild, embed.description)


class BeTheProfessionalCog(Cog, name="BeTheProfessional"):
    CONTRIBUTORS = [
        Contributor.Defelo,
        Contributor.wolflu,
        Contributor.MaxiHuHe04,
        Contributor.AdriBloober,
        Contributor.Tert0,
    ]

    async def on_ready(self):
        self.update_roles.cancel()
        try:
            self.update_roles.start()
        except RuntimeError:
            self.update_roles.restart()

    @commands.command(name="?")
    @guild_only()
    async def list_topics(self, ctx: Context, parent_topic: str | None):
        """
        list all direct children topics of the parent
        """
        parent: BTPTopic | None | CommandError = (
            None
            if parent_topic is None
            else await db.first(filter_by(BTPTopic, name=parent_topic))
            or CommandError(t.topic_not_found(parent_topic))  # noqa: W503
        )
        if isinstance(parent, CommandError):
            raise parent

        embed = Embed(title=t.available_topics_header, colour=Colors.BeTheProfessional)
        sorted_topics: dict[str, list[str]] = {}
        topics: list[BTPTopic] = await db.all(filter_by(BTPTopic, parent=None if parent is None else parent.id))
        if not topics:
            embed.colour = Colors.error
            embed.description = t.no_topics_registered
            await reply(ctx, embed=embed)
            return

        topics.sort(key=lambda btp_topic: btp_topic.name.lower())
        root_topic: BTPTopic | None = (
            None if parent_topic is None else await db.first(filter_by(BTPTopic, name=parent_topic))
        )
        for topic in topics:
            if (root_topic.name if root_topic is not None else "Topics") not in sorted_topics.keys():
                sorted_topics[root_topic.name if root_topic is not None else "Topics"] = [f"{topic.name}"]
            else:
                sorted_topics[root_topic.name if root_topic is not None else "Topics"].append(f"{topic.name}")

        for root_topic in sorted_topics.keys():
            embed.add_field(
                name=root_topic,
                value=", ".join(
                    [
                        f"`{topic.name}"
                        + (  # noqa: W503
                            f" ({c})`"
                            if (c := await db.count(filter_by(BTPTopic, parent=topic.id))) > 0
                            else "`"
                        )
                        for topic in topics
                    ]
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
        topics: list[BTPTopic] = [
            topic
            for topic in await parse_topics(topics)
            if (await db.exists(filter_by(BTPTopic, id=topic.id)))
            and not (await db.exists(filter_by(BTPUser, user_id=member.id, topic=topic.id)))  # noqa: W503
        ]

        roles: list[Role] = []

        for topic in topics:
            await BTPUser.create(member.id, topic.id)
            if topic.role_id:
                roles.append(ctx.guild.get_role(topic.role_id))
        await ctx.author.add_roles(*roles, atomic=False)

        embed = Embed(title=t.betheprofessional, colour=Colors.BeTheProfessional)
        embed.description = t.topics_added(cnt=len(topics))

        redis_key: str = f"btp:single_un_assign:{ctx.author.id}"

        if len(topics) == 0:
            embed.colour = Colors.error
        elif len(topics) == 1:
            count = await redis.incr(redis_key)
            await redis.expire(redis_key, 30)

            if count > 3:
                await reply(ctx, embed=embed)

                embed.colour = Colors.BeTheProfessional
                embed.description = t.single_un_assign_help
        else:
            await redis.delete(redis_key)

        await reply(ctx, embed=embed)

    @commands.command(name="-")
    @guild_only()
    async def unassign_topics(self, ctx: Context, *, topics: str):
        """
        remove one or more topics (use * to remove all topics)
        """
        member: Member = ctx.author
        if topics.strip() == "*":
            topics: list[BTPTopic] = await get_topics()
        else:
            topics: list[BTPTopic] = await parse_topics(topics)
        affected_topics: list[BTPTopic] = []
        for topic in topics:
            if await db.exists(filter_by(BTPUser, user_id=member.id, topic=topic.id)):
                affected_topics.append(topic)

        roles: list[Role] = []

        for topic in affected_topics:
            await db.delete(await db.first(filter_by(BTPUser, topic=topic.id)))
            if topic.role_id:
                roles.append(ctx.guild.get_role(topic.role_id))

        await ctx.author.remove_roles(*roles, atomic=False)

        embed = Embed(title=t.betheprofessional, colour=Colors.BeTheProfessional)
        embed.description = t.topics_removed(cnt=len(affected_topics))

        redis_key: str = f"btp:single_un_assign:{ctx.author.id}"

        if len(affected_topics) == 1:
            count = await redis.incr(redis_key)
            await redis.expire(redis_key, 30)

            if count > 3:
                await redis.delete(redis_key)
                await reply(ctx, embed=embed)

                embed.description = t.single_un_assign_help
        elif len(affected_topics) > 1:
            await redis.delete(redis_key)

        await reply(ctx, embed=embed)

    @commands.command(name="*")
    @BeTheProfessionalPermission.manage.check
    @guild_only()
    async def register_topics(self, ctx: Context, *, topic_paths: str, assignable: bool = True):
        """
        register one or more new topics by path
        """

        names = split_topics(topic_paths)
        topic_paths: list[tuple[str, bool, list[BTPTopic] | None]] = await split_parents(names, assignable)
        if not names or not topic_paths:
            raise UserInputError

        valid_chars = set(string.ascii_letters + string.digits + " !#$%&'()+-./:<=>?[\\]^_`{|}~")
        registered_topics: list[tuple[str, bool, list[BTPTopic]] | None] = []
        for topic in topic_paths:
            if len(topic) > 100:
                raise CommandError(t.topic_too_long(topic))
            if any(c not in valid_chars for c in topic[0]):
                raise CommandError(t.topic_invalid_chars(topic))

            if await db.exists(filter_by(BTPTopic, name=topic[0])):
                raise CommandError(t.topic_already_registered(topic[0]))
            else:
                registered_topics.append(topic)

        for registered_topic in registered_topics:
            await BTPTopic.create(
                registered_topic[0], None, True, registered_topic[2][-1].id if len(registered_topic[2]) > 0 else None
            )

        embed = Embed(title=t.betheprofessional, colour=Colors.BeTheProfessional)
        embed.description = t.topics_registered(cnt=len(registered_topics))
        await send_to_changelog(
            ctx.guild,
            t.log_topics_registered(
                cnt=len(registered_topics), topics=", ".join(f"`{r[0]}`" for r in registered_topics)
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

        topics: list[str] = split_topics(topics)

        delete_topics: list[BTPTopic] = []

        for topic in topics:
            if not (btp_topic := await db.exists(filter_by(BTPTopic, name=topic))):
                raise CommandError(t.topic_not_registered(topic))
            else:
                delete_topics.append(btp_topic)

                # TODO use relationships for children
                queue: list[int] = [btp_topic.id]

                while len(queue) != 0:
                    topic_id = queue.pop()
                    for child_topic in await db.all(select(BTPTopic).filter_by(parent=topic_id)):
                        delete_topics.insert(0, child_topic)
                        queue.append(child_topic.id)

        for topic in delete_topics:
            if topic.role_id is not None:
                role: Role = ctx.guild.get_role(topic.role_id)
                if role is not None:
                    await role.delete()
            for user_topic in await db.all(filter_by(BTPUser, topic=topic.id)):
                # TODO use db.exec
                await db.delete(user_topic)
            await db.commit()
            await db.delete(topic)

        embed = Embed(title=t.betheprofessional, colour=Colors.BeTheProfessional)
        embed.description = t.topics_unregistered(cnt=len(delete_topics))
        await send_to_changelog(
            ctx.guild,
            t.log_topics_unregistered(cnt=len(delete_topics), topics=", ".join(f"`{t.name}`" for t in delete_topics)),
        )
        await send_long_embed(ctx, embed)

    @commands.command()
    @guild_only()
    async def topic(self, ctx: Context, topic_name: str, message: Message | None):
        """
        pings the specified topic
        """

        topic: BTPTopic = await db.first(select(BTPTopic).filter_by(name=topic_name))
        mention: str
        if topic is None:
            raise CommandError(t.topic_not_found(topic_name))
        if topic.role_id is not None:
            mention = f"<@&{topic.role_id}>"
        else:
            topic_members: list[BTPUser] = await db.all(select(BTPUser).filter_by(topic=topic.id))
            mention = ", ".join(map(lambda m: f"<@{m.user_id}>", topic_members))

        if mention == "":
            raise CommandError(t.nobody_has_topic(topic_name))
        if message is None:
            await ctx.send(mention)
        else:
            await message.reply(mention)

    @commands.group()
    @guild_only()
    @BeTheProfessionalPermission.read.check
    async def btp(self, ctx: Context):
        if ctx.subcommand_passed is not None:
            if ctx.invoked_subcommand is None:
                raise UserInputError
            return

        embed = Embed(title=t.betheprofessional, color=Colors.BeTheProfessional)
        # TODO do not do that!!!!
        for setting_item in t.settings.__dict__["_fallback"].keys():
            data = getattr(t.settings, setting_item)
            embed.add_field(
                name=data.name, value=await getattr(BeTheProfessionalSettings, data.internal_name).get(), inline=False
            )
        await reply(ctx, embed=embed)

    @btp.command()
    @guild_only()
    @BeTheProfessionalPermission.manage.check
    async def role_limit(self, ctx: Context, role_limit: int):
        """
        changes the btp role limit
        """

        if role_limit <= 0:
            # TODO use quotes for the name in the embed
            raise CommandError(t.must_be_above_zero(t.settings.role_limit.name))
        await change_setting(ctx, "role_limit", role_limit)

    @btp.command()
    @guild_only()
    @BeTheProfessionalPermission.manage.check
    async def role_create_min_users(self, ctx: Context, role_create_min_users: int):
        """
        changes the btp role create min users count
        """

        if role_create_min_users < 0:
            # TODO use quotes for the name in the embed
            raise CommandError(t.must_be_zero_or_above(t.settings.role_create_min_users.name))
        await change_setting(ctx, "role_create_min_users", role_create_min_users)

    @btp.command()
    @guild_only()
    @BeTheProfessionalPermission.manage.check
    async def leaderboard_default_n(self, ctx: Context, leaderboard_default_n: int):
        """
        changes the btp leaderboard default n
        """

        if leaderboard_default_n <= 0:
            # TODO use quotes for the name in the embed
            raise CommandError(t.must_be_above_zero(t.settings.leaderboard_default_n.name))
        await change_setting(ctx, "leaderboard_default_n", leaderboard_default_n)

    @btp.command()
    @guild_only()
    @BeTheProfessionalPermission.manage.check
    async def leaderboard_max_n(self, ctx: Context, leaderboard_max_n: int):
        """
        changes the btp leaderboard max n
        """

        if leaderboard_max_n <= 0:
            # TODO use quotes for the name in the embed
            raise CommandError(t.must_be_above_zero(t.settings.leaderboard_max_n.name))
        await change_setting(ctx, "leaderboard_max_n", leaderboard_max_n)

    @btp.command(aliases=["lb"])
    @guild_only()
    # TODO parameters
    async def leaderboard(self, ctx: Context, n: int | None = None, use_cache: bool = True):
        """
        lists the top n topics
        """

        default_n = await BeTheProfessionalSettings.LeaderboardDefaultN.get()
        max_n = await BeTheProfessionalSettings.LeaderboardMaxN.get()
        if n is None:
            n = default_n
        if default_n > max_n:
            await send_alert(ctx.guild, t.leaderboard_default_n_bigger_than_max_n)
            raise CommandError(t.leaderboard_configuration_error)
        if n > max_n and not await BeTheProfessionalPermission.bypass_leaderboard_n_limit.check_permissions(ctx.author):
            raise CommandError(t.leaderboard_n_too_big(n, max_n))
        if n <= 0:
            raise CommandError(t.leaderboard_n_zero_error)

        cached_leaderboard_parts: list[str] | None = None

        redis_key = f"btp:leaderboard:n:{n}"
        if use_cache:
            if not await BeTheProfessionalPermission.bypass_leaderboard_cache.check_permissions(ctx.author):
                raise CommandError(t.missing_cache_bypass_permission)
            cached_leaderboard_parts = await redis.lrange(redis_key, 0, await redis.llen(redis_key))

        leaderboard_parts: list[str] = []
        if not cached_leaderboard_parts:
            topic_count: dict[int, int] = {}

            for topic in await db.all(select(BTPTopic)):
                topic_count[topic.id] = await db.count(select(BTPUser).filter_by(topic=topic.id))

            top_topics: list[int] = sorted(topic_count, key=lambda x: topic_count[x], reverse=True)[:n]

            if len(top_topics) == 0:
                raise CommandError(t.no_topics_registered)

            name_field = t.leaderboard_colmn_name
            users_field = t.leaderboard_colmn_users

            rank_len = len(str(len(top_topics))) + 1
            name_len = max(max([len(topic.name) for topic in await db.all(select(BTPTopic))]), len(name_field))

            rank_spacing = " " * (rank_len + LEADERBOARD_TABLE_SPACING)
            name_spacing = " " * (name_len + LEADERBOARD_TABLE_SPACING - len(name_field))

            header: str = f"{rank_spacing}{name_field}{name_spacing}{users_field}"

            current_part: str = header
            for i, topic_id in enumerate(top_topics):
                topic: BTPTopic = await db.first(select(BTPTopic).filter_by(id=topic_id))
                users: int = topic_count[topic_id]
                name: str = topic.name.ljust(name_len, " ")
                rank: str = "#" + str(i + 1).rjust(rank_len - 1, "0")
                current_line = f"{rank}{' ' * LEADERBOARD_TABLE_SPACING}{name}{' ' * LEADERBOARD_TABLE_SPACING}{users}"
                if current_part == "":
                    current_part = current_line
                else:
                    if len(current_part + "\n" + current_line) + 9 > PyDrocsid.embeds.EmbedLimits.FIELD_VALUE:
                        leaderboard_parts.append(current_part)
                        current_part = current_line
                    else:
                        current_part += "\n" + current_line
            if current_part != "":
                leaderboard_parts.append(current_part)

            for part in leaderboard_parts:
                await redis.lpush(redis_key, part)
            await redis.expire(redis_key, CACHE_TTL)
        else:
            leaderboard_parts = cached_leaderboard_parts

        embed = Embed(title=t.leaderboard_title(n))
        for part in leaderboard_parts:
            embed.add_field(name="** **", value=f"```css\n{part}\n```", inline=False)
        await send_long_embed(ctx, embed, paginate=True)

    @commands.command(name="usertopics", aliases=["usertopic", "utopics", "utopic"])
    async def user_topics(self, ctx: Context, member: Member | None):
        """
        lists all topics of a member
        """

        if member is None:
            member = ctx.author

        # TODO use relationships and join
        topics_assigns: list[BTPUser] = await db.all(select(BTPUser).filter_by(user_id=member.id))
        topics: list[BTPTopic] = [
            await db.first(select(BTPTopic).filter_by(id=assignment.topic)) for assignment in topics_assigns
        ]

        embed = Embed(title=t.betheprofessional, color=Colors.BeTheProfessional)

        embed.set_author(name=str(member), icon_url=member.display_avatar.url)

        topics_str: str = ""

        if len(topics_assigns) == 0:
            embed.colour = Colors.red
        else:
            topics_str = ", ".join([f"`{topic.name}`" for topic in topics])

        embed.description = t.user_topics(member.mention, topics_str, cnt=len(topics))

        await reply(ctx, embed=embed)

    @commands.command(aliases=["topic_update", "update_roles"])
    @guild_only()
    @BeTheProfessionalPermission.manage.check
    async def topic_update_roles(self, ctx: Context):
        """
        updates the topic roles manually
        """

        await self.update_roles()
        await reply(ctx, "Updated Topic Roles")

    @tasks.loop(hours=24)
    @db_wrapper
    async def update_roles(self):
        role_create_min_users = await BeTheProfessionalSettings.RoleCreateMinUsers.get()

        logger.info("Started Update Role Loop")
        topic_count: dict[int, int] = {}

        # TODO rewrite from here....
        for topic in await db.all(select(BTPTopic)):
            # TODO use relationship and join
            topic_count[topic.id] = await db.count(select(BTPUser).filter_by(topic=topic.id))
        # not using dict.items() because of typing
        # TODO Let db sort topics by count and then by
        # TODO fix TODO ^^
        topic_count_items: list[tuple[int, int]] = list(zip(topic_count.keys(), topic_count.values()))
        topic_count = dict(sorted(topic_count_items, key=lambda x: x[0]))

        # Sort Topics By Count, Keep only Topics with a Count of BeTheProfessionalSettings.RoleCreateMinUsers or above
        # Limit Roles to BeTheProfessionalSettings.RoleLimit
        top_topics: list[int] = list(
            filter(
                lambda topic_id: topic_count[topic_id] >= role_create_min_users,
                sorted(topic_count, key=lambda x: topic_count[x], reverse=True),
            )
        )[: await BeTheProfessionalSettings.RoleLimit.get()]

        # TODO until here

        # Delete old Top Topic Roles
        # TODO use filter_by
        for topic in await db.all(select(BTPTopic).filter(BTPTopic.role_id is not None)):  # type: BTPTopic
            # TODO use sql "NOT IN" expression
            if topic.id not in top_topics:
                if topic.role_id is not None:
                    await self.bot.guilds[0].get_role(topic.role_id).delete()
                    topic.role_id = None

        # Create new Topic Roles
        roles: dict[int, Role] = {}
        # TODO use sql "IN" expression
        for top_topic in top_topics:
            topic: BTPTopic = await db.first(select(BTPTopic).filter_by(id=top_topic))
            if topic.role_id is None:
                role = await self.bot.guilds[0].create_role(name=topic.name)
                topic.role_id = role.id
                roles[topic.id] = role

        # Iterate over all members(with topics) and add the role to them
        # TODO add filter, only select topics with newly added roles
        member_ids: set[int] = {btp_user.user_id for btp_user in await db.all(select(BTPUser))}
        for member_id in member_ids:
            member: Member = self.bot.guilds[0].get_member(member_id)
            if member is None:
                continue
            member_roles: list[Role] = [
                roles.get(btp_user.topic) for btp_user in await db.all(select(BTPUser).filter_by(user_id=member_id))
            ]
            # TODO use filter or something?
            member_roles = [item for item in member_roles if item is not None]
            await member.add_roles(*member_roles, atomic=False)

        logger.info("Created Top Topic Roles")

    async def on_member_join(self, member: Member):
        # TODO use relationship and join
        topics: list[BTPUser] = await db.all(select(BTPUser).filter_by(user_id=member.id))
        role_ids: list[int] = [(await db.first(select(BTPTopic).filter_by(id=topic))).role_id for topic in topics]
        roles: list[Role] = [self.bot.guilds[0].get_role(role_id) for role_id in role_ids]
        await member.add_roles(*roles, atomic=False)
