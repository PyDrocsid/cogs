import asyncio
import time
from asyncio import Event
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional, Union

from PyDrocsid.async_thread import semaphore_gather
from PyDrocsid.cog import Cog
from PyDrocsid.command import reply, optional_permissions
from PyDrocsid.config import Contributor
from PyDrocsid.database import db, filter_by, db_wrapper, db_context
from PyDrocsid.embeds import send_long_embed
from PyDrocsid.emojis import name_to_emoji
from PyDrocsid.logger import get_logger
from PyDrocsid.settings import RoleSettings
from PyDrocsid.translations import t
from dateutil.relativedelta import relativedelta
from discord import (
    User,
    NotFound,
    Embed,
    Guild,
    Forbidden,
    HTTPException,
    Member,
    Role,
    Message,
    MessageType,
    TextChannel,
)
from discord.ext import commands
from discord.ext.commands import Context, UserInputError, CommandError, max_concurrency, guild_only
from discord.utils import snowflake_time

from .colors import Colors
from .models import Join, Leave, UsernameUpdate, Verification
from .permissions import UserInfoPermission
from ...pubsub import (
    get_userlog_entries,
    get_user_info_entries,
    get_user_status_entries,
    revoke_verification,
    send_alert,
)

logger = get_logger(__name__)

tg = t.g
t = t.user_info


def date_diff_to_str(date1: datetime, date2: datetime):
    rd = relativedelta(date1, date2)
    if rd.years:
        return t.joined_years(cnt=rd.years)
    if rd.months:
        return t.joined_months(cnt=rd.months)
    if rd.weeks:
        return t.joined_weeks(cnt=rd.weeks)
    return t.joined_days


async def get_user(
    ctx: Context,
    user: Optional[Union[User, int]],
    permission: UserInfoPermission,
) -> tuple[Union[User, int], int, bool]:
    arg_passed = len(ctx.message.content.strip(ctx.prefix).split()) >= 2
    if user is None:
        if arg_passed:
            raise UserInputError
        user = ctx.author

    if isinstance(user, int):
        if not 0 <= user < (1 << 63):
            raise UserInputError
        try:
            user = await ctx.bot.fetch_user(user)
        except NotFound:
            pass

    user_id = user if isinstance(user, int) else user.id

    if user_id != ctx.author.id and not await permission.check_permissions(ctx.author):
        raise CommandError(t.not_allowed)

    return user, user_id, arg_passed


class UserInfoCog(Cog, name="User Information"):
    CONTRIBUTORS = [Contributor.Defelo]

    def __init__(self):
        self.join_events: dict[int, Event] = defaultdict(Event)
        self.join_id: dict[int, int] = {}

    async def on_message(self, message: Message):
        if message.type != MessageType.new_member:
            return

        member_id: int = message.author.id
        await self.join_events[member_id].wait()
        self.join_events[member_id].clear()
        self.join_events.pop(member_id)

        async with db_context():
            join: Join = await db.get(Join, id=self.join_id.pop(member_id))
            join.join_msg_channel_id = message.channel.id
            join.join_msg_id = message.id

    async def on_member_join(self, member: Member):
        self.join_events[member.id].clear()

        join: Join = await Join.create(member.id, str(member), member.joined_at.replace(microsecond=0))

        async def trigger_join_event():
            await db.wait_for_close_event()
            self.join_id[member.id] = join.id
            self.join_events[member.id].set()

        asyncio.create_task(trigger_join_event())

        last_verification: Optional[Verification] = await db.first(
            filter_by(Verification, member=member.id).order_by(Verification.timestamp.desc()),
        )
        if not last_verification or not last_verification.accepted:
            return

        role: Optional[Role] = member.guild.get_role(await RoleSettings.get("verified"))
        if role:
            await member.add_roles(role)

    async def on_member_remove(self, member: Member):
        self.join_events.pop(member.id, None)
        self.join_id.pop(member.id, None)
        await Leave.create(member.id, str(member))

    async def on_member_nick_update(self, before: Member, after: Member):
        await UsernameUpdate.create(before.id, before.nick, after.nick, True)

    async def on_user_update(self, before: User, after: User):
        if str(before) == str(after):
            return

        await UsernameUpdate.create(before.id, str(before), str(after), False)

    async def update_verification_reaction(self, member: Member, add: bool):
        guild: Guild = member.guild

        for _ in range(10):
            async with db_context():
                join: Optional[Join] = await db.get(
                    Join,
                    member=member.id,
                    timestamp=member.joined_at.replace(microsecond=0),
                )
                if not join or not join.join_msg_id or not join.join_msg_channel_id:
                    await asyncio.sleep(2)
                    continue

                channel_id: int = join.join_msg_channel_id
                message_id: int = join.join_msg_id
                break
        else:
            return

        channel: Optional[TextChannel] = self.bot.get_channel(channel_id)
        if not channel:
            return

        try:
            message: Message = await channel.fetch_message(message_id)
        except (NotFound, Forbidden, HTTPException):
            return

        try:
            await message.remove_reaction(name_to_emoji["x" if add else "white_check_mark"], guild.me)
            await message.add_reaction(name_to_emoji["white_check_mark" if add else "x"])
        except Forbidden:
            await send_alert(guild, tg.could_not_add_reaction(message.channel.mention))

    async def on_member_role_add(self, member: Member, role: Role):
        if role.id != await RoleSettings.get("verified"):
            return

        asyncio.create_task(self.update_verification_reaction(member, add=True))

        last_verification: Optional[Verification] = await db.first(
            filter_by(Verification, member=member.id).order_by(Verification.timestamp.desc()),
        )
        if last_verification and last_verification.accepted:
            return

        await Verification.create(member.id, str(member), True)

    async def on_member_role_remove(self, member: Member, role: Role):
        if role.id != await RoleSettings.get("verified"):
            return

        asyncio.create_task(self.update_verification_reaction(member, add=False))

        await Verification.create(member.id, str(member), False)

    @revoke_verification.subscribe
    async def handle_revoke_verification(self, member: Member):
        await Verification.create(member.id, str(member), False)

    @commands.command(aliases=["user", "uinfo", "ui", "userstats", "stats"])
    @optional_permissions(UserInfoPermission.view_userinfo)
    async def userinfo(self, ctx: Context, user: Optional[Union[User, int]] = None):
        """
        show information about a user
        """

        user, user_id, arg_passed = await get_user(ctx, user, UserInfoPermission.view_userinfo)

        embed = Embed(title=t.userinfo, color=Colors.stats)
        if isinstance(user, int):
            embed.set_author(name=str(user))
        else:
            embed.set_author(name=f"{user} ({user_id})", icon_url=user.avatar_url)

        for response in await get_user_info_entries(user_id):
            for name, value in response:
                embed.add_field(name=name, value=value, inline=True)

        if (member := self.bot.guilds[0].get_member(user_id)) is not None:
            status = t.member_since(member.joined_at.strftime("%d.%m.%Y %H:%M:%S"))
        else:
            status = t.not_a_member
        embed.add_field(name=t.membership, value=status, inline=False)

        for response in await get_user_status_entries(user_id):
            for name, value in response:
                embed.add_field(name=name, value=value, inline=False)

        if arg_passed:
            await reply(ctx, embed=embed)
        else:
            try:
                await ctx.author.send(embed=embed)
            except (Forbidden, HTTPException):
                raise CommandError(t.could_not_send_dm)
            await ctx.message.add_reaction(name_to_emoji["white_check_mark"])

    @commands.command(aliases=["userlog", "ulog"])
    @optional_permissions(UserInfoPermission.view_userlog)
    async def userlogs(self, ctx: Context, user: Optional[Union[User, int]] = None):
        """
        show moderation log of a user
        """

        guild: Guild = self.bot.guilds[0]

        user, user_id, arg_passed = await get_user(ctx, user, UserInfoPermission.view_userlog)

        out: list[tuple[datetime, str]] = [(snowflake_time(user_id), t.ulog.created)]

        join: Join
        async for join in await db.stream(filter_by(Join, member=user_id)):
            out.append((join.timestamp, t.ulog.joined))

        leave: Leave
        async for leave in await db.stream(filter_by(Leave, member=user_id)):
            out.append((leave.timestamp, t.ulog.left))

        username_update: UsernameUpdate
        async for username_update in await db.stream(filter_by(UsernameUpdate, member=user_id)):
            if not username_update.nick:
                msg = t.ulog.username_updated(username_update.member_name, username_update.new_name)
            elif username_update.member_name is None:
                msg = t.ulog.nick.set(username_update.new_name)
            elif username_update.new_name is None:
                msg = t.ulog.nick.cleared(username_update.member_name)
            else:
                msg = t.ulog.nick.updated(username_update.member_name, username_update.new_name)
            out.append((username_update.timestamp, msg))

        if await RoleSettings.get("verified") in {role.id for role in guild.roles}:
            verification: Verification
            async for verification in await db.stream(filter_by(Verification, member=user_id)):
                if verification.accepted:
                    out.append((verification.timestamp, t.ulog.verification.accepted))
                else:
                    out.append((verification.timestamp, t.ulog.verification.revoked))

        responses = await get_userlog_entries(user_id, ctx.author)
        for response in responses:
            out += response

        out.sort()
        embed = Embed(title=t.userlogs, color=Colors.userlog)
        if isinstance(user, int):
            embed.set_author(name=str(user))
        else:
            embed.set_author(name=f"{user} ({user_id})", icon_url=user.avatar_url)
        for row in out:
            name = row[0].strftime("%d.%m.%Y %H:%M:%S")
            value = row[1]
            embed.add_field(name=name, value=value, inline=False)

        embed.set_footer(text=t.utc_note)

        if arg_passed:
            await send_long_embed(ctx, embed, paginate=True)
        else:
            try:
                await send_long_embed(ctx.author, embed)
            except (Forbidden, HTTPException):
                raise CommandError(t.could_not_send_dm)
            await ctx.message.add_reaction(name_to_emoji["white_check_mark"])

    @commands.command()
    @guild_only()
    async def joined(self, ctx: Context, member: Member = None):
        """
        Returns a rough estimate for the user's time on the server
        """

        member = member or ctx.author
        verification: Optional[Verification] = await db.first(
            filter_by(Verification, member=member.id).order_by(Verification.timestamp.desc()),
        )
        ts: datetime = verification.timestamp if verification else member.joined_at

        embed = Embed(
            title=t.userinfo,
            description=f"{member.mention} {date_diff_to_str(datetime.today(), ts)}",
        )
        await reply(ctx, embed=embed)

    @commands.command()
    @UserInfoPermission.init_join_log.check
    @max_concurrency(1)
    @guild_only()
    async def init_join_log(self, ctx: Context):
        """
        create a join log entry for each server member
        """

        guild: Guild = ctx.guild

        embed = Embed(
            title=t.init_join_log,
            description=t.filling_join_log(cnt=len(guild.members)),
            color=Colors.UserInfo,
        )
        await reply(ctx, embed=embed)

        @db_wrapper
        async def update(member):
            await Join.update(member.id, str(member), member.joined_at)

            relevant_join: Optional[Join] = await db.first(
                filter_by(Join, member=member.id).order_by(Join.timestamp.asc()),
            )

            if not relevant_join:
                return

            timestamp = relevant_join.timestamp + timedelta(seconds=10)
            if await db.exists(filter_by(Verification, member=member.id, accepted=True, timestamp=timestamp)):
                return

            await db.add(
                Verification(
                    member=member.id,
                    member_name=str(member),
                    accepted=True,
                    timestamp=timestamp,
                ),
            )

        ts = time.time()
        await semaphore_gather(50, *[update(m) for m in guild.members])

        embed.description = t.join_log_filled
        embed.set_footer(text=f"{time.time() - ts:.2f} s")
        await reply(ctx, embed=embed)
