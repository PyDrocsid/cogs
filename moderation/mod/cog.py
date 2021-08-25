import re
from datetime import datetime, timedelta
from typing import Optional, Union, List, Tuple

from discord import Role, Guild, Member, Forbidden, HTTPException, User, Embed, NotFound, Message
from discord.ext import commands, tasks
from discord.ext.commands import (
    guild_only,
    Context,
    CommandError,
    Converter,
)

from PyDrocsid.cog import Cog
from PyDrocsid.command import reply, UserCommandError
from PyDrocsid.converter import UserMemberConverter
from PyDrocsid.database import db, filter_by, db_wrapper
from PyDrocsid.settings import RoleSettings
from PyDrocsid.translations import t
from PyDrocsid.util import is_teamler, check_role_assignable
from .colors import Colors
from .models import Mute, Ban, Report, Warn, Kick
from .permissions import ModPermission
from ...contributor import Contributor
from ...pubsub import (
    send_to_changelog,
    log_auto_kick,
    get_userlog_entries,
    get_user_info_entries,
    get_user_status_entries,
    revoke_verification,
    send_alert,
)

tg = t.g
t = t.mod


class DurationConverter(Converter):
    async def convert(self, ctx, argument: str) -> Optional[int]:
        if argument.lower() in ("inf", "perm", "permanent", "-1", "∞"):
            return None
        if (match := re.match(r"^(\d+)d?$", argument)) is None:
            raise CommandError(tg.invalid_duration)
        if (days := int(match.group(1))) <= 0:
            raise CommandError(tg.invalid_duration)
        if days >= (1 << 31):
            raise CommandError(t.invalid_duration_inf)
        return days


async def get_mute_role(guild: Guild) -> Role:
    mute_role: Optional[Role] = guild.get_role(await RoleSettings.get("mute"))
    if mute_role is None:
        raise CommandError(t.mute_role_not_set)
    return mute_role


async def send_to_changelog_mod(
    guild: Guild,
    message: Optional[Message],
    colour: int,
    title: str,
    member: Union[Member, User, Tuple[int, str]],
    reason: str,
    *,
    duration: Optional[str] = None,
):
    embed = Embed(title=title, colour=colour, timestamp=datetime.utcnow())

    if isinstance(member, tuple):
        member_id, member_name = member
        embed.set_author(name=member_name)
    else:
        member_id: int = member.id
        member_name: str = str(member)
        embed.set_author(name=member_name, icon_url=member.avatar_url)

    embed.add_field(name=t.log_field.member, value=f"<@{member_id}>", inline=True)
    embed.add_field(name=t.log_field.member_id, value=str(member_id), inline=True)

    if message:
        embed.set_footer(text=str(message.author), icon_url=message.author.avatar_url)
        embed.add_field(
            name=t.log_field.channel,
            value=t.jump_url(message.channel.mention, message.jump_url),
            inline=True,
        )

    if duration:
        embed.add_field(name=t.log_field.duration, value=duration, inline=True)

    embed.add_field(name=t.log_field.reason, value=reason, inline=False)

    await send_to_changelog(guild, embed)


class ModCog(Cog, name="Mod Tools"):
    CONTRIBUTORS = [Contributor.Defelo, Contributor.wolflu, Contributor.Florian]

    async def on_ready(self):
        guild: Guild = self.bot.guilds[0]
        mute_role: Optional[Role] = guild.get_role(await RoleSettings.get("mute"))
        if mute_role is not None:
            async for mute in await db.stream(filter_by(Mute, active=True)):
                member: Optional[Member] = guild.get_member(mute.member)
                if member is not None:
                    await member.add_roles(mute_role)

        try:
            self.mod_loop.start()
        except RuntimeError:
            self.mod_loop.restart()

    @tasks.loop(minutes=30)
    @db_wrapper
    async def mod_loop(self):
        guild: Guild = self.bot.guilds[0]

        async for ban in await db.stream(filter_by(Ban, active=True)):
            if ban.days != -1 and datetime.utcnow() >= ban.timestamp + timedelta(days=ban.days):
                await Ban.deactivate(ban.id)

                try:
                    user = await self.bot.fetch_user(ban.member)
                except NotFound:
                    user = ban.member, ban.member_name

                if isinstance(user, User):
                    try:
                        await guild.unban(user)
                    except Forbidden:
                        await send_alert(guild, t.cannot_unban_user_permissions(user.mention, user.id))

                await send_to_changelog_mod(
                    guild,
                    None,
                    Colors.unban,
                    t.log_unbanned,
                    user,
                    t.log_unbanned_expired,
                )

        mute_role: Optional[Role] = guild.get_role(await RoleSettings.get("mute"))
        if mute_role is None:
            return

        try:
            check_role_assignable(mute_role)
        except CommandError:
            await send_alert(guild, t.cannot_assign_mute_role(mute_role, mute_role.id))
            return

        async for mute in await db.stream(filter_by(Mute, active=True)):
            if mute.days != -1 and datetime.utcnow() >= mute.timestamp + timedelta(days=mute.days):
                if member := guild.get_member(mute.member):
                    await member.remove_roles(mute_role)
                else:
                    member = mute.member, mute.member_name

                await send_to_changelog_mod(
                    guild,
                    None,
                    Colors.unmute,
                    t.log_unmuted,
                    member,
                    t.log_unmuted_expired,
                )
                await Mute.deactivate(mute.id)

    @log_auto_kick.subscribe
    async def handle_log_auto_kick(self, member: Member):
        await Kick.create(member.id, str(member), None, None)

    @get_user_info_entries.subscribe
    async def handle_get_user_stats_entries(self, user_id: int) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []

        async def count(cls):
            if cls is Report:
                active = await db.count(filter_by(cls, reporter=user_id))
            else:
                active = await db.count(filter_by(cls, mod=user_id))

            passive = await db.count(filter_by(cls, member=user_id))

            if cls is Kick:
                if auto_kicks := await db.count(filter_by(cls, member=user_id, mod=None)):
                    return t.active_passive(active, passive - auto_kicks) + "\n" + t.autokicks(cnt=auto_kicks)

            return t.active_passive(active, passive)

        out.append((t.reported_cnt, await count(Report)))
        out.append((t.warned_cnt, await count(Warn)))
        out.append((t.muted_cnt, await count(Mute)))
        out.append((t.kicked_cnt, await count(Kick)))
        out.append((t.banned_cnt, await count(Ban)))

        return out

    @get_user_status_entries.subscribe
    async def handle_get_user_status_entries(self, user_id: int) -> list[tuple[str, str]]:
        status = t.none
        if (ban := await db.get(Ban, member=user_id, active=True)) is not None:
            if ban.days != -1:
                expiry_date: datetime = ban.timestamp + timedelta(days=ban.days)
                days_left = (expiry_date - datetime.utcnow()).days + 1
                status = t.status_banned_days(cnt=ban.days, left=days_left)
            else:
                status = t.status_banned
        elif (mute := await db.get(Mute, member=user_id, active=True)) is not None:
            if mute.days != -1:
                expiry_date: datetime = mute.timestamp + timedelta(days=mute.days)
                days_left = (expiry_date - datetime.utcnow()).days + 1
                status = t.status_muted_days(cnt=mute.days, left=days_left)
            else:
                status = t.status_muted
        return [(t.active_sanctions, status)]

    @get_userlog_entries.subscribe
    async def handle_get_userlog_entries(self, user_id: int, author: Member) -> list[tuple[datetime, str]]:
        out: list[tuple[datetime, str]] = []

        if await is_teamler(author):
            report: Report
            async for report in await db.stream(filter_by(Report, member=user_id)):
                out.append((report.timestamp, t.ulog.reported(f"<@{report.reporter}>", report.reason)))

        warn: Warn
        async for warn in await db.stream(filter_by(Warn, member=user_id)):
            out.append((warn.timestamp, t.ulog.warned(f"<@{warn.mod}>", warn.reason)))

        mute: Mute
        async for mute in await db.stream(filter_by(Mute, member=user_id)):
            text = t.ulog.muted.upgrade if mute.is_upgrade else t.ulog.muted.first

            if mute.days == -1:
                out.append((mute.timestamp, text.inf(f"<@{mute.mod}>", mute.reason)))
            else:
                out.append((mute.timestamp, text.temp(f"<@{mute.mod}>", mute.reason, cnt=mute.days)))

            if not mute.active and not mute.upgraded:
                if mute.unmute_mod is None:
                    out.append((mute.deactivation_timestamp, t.ulog.unmuted_expired))
                else:
                    out.append(
                        (
                            mute.deactivation_timestamp,
                            t.ulog.unmuted(f"<@{mute.unmute_mod}>", mute.unmute_reason),
                        ),
                    )

        kick: Kick
        async for kick in await db.stream(filter_by(Kick, member=user_id)):
            if kick.mod is not None:
                out.append((kick.timestamp, t.ulog.kicked(f"<@{kick.mod}>", kick.reason)))
            else:
                out.append((kick.timestamp, t.ulog.autokicked))

        ban: Ban
        async for ban in await db.stream(filter_by(Ban, member=user_id)):
            text = t.ulog.banned.upgrade if ban.is_upgrade else t.ulog.banned.first

            if ban.days == -1:
                out.append((ban.timestamp, text.inf(f"<@{ban.mod}>", ban.reason)))
            else:
                out.append((ban.timestamp, text.temp(f"<@{ban.mod}>", ban.reason, cnt=ban.days)))

            if not ban.active and not ban.upgraded:
                if ban.unban_mod is None:
                    out.append((ban.deactivation_timestamp, t.ulog.unbanned_expired))
                else:
                    out.append(
                        (
                            ban.deactivation_timestamp,
                            t.ulog.unbanned(f"<@{ban.unban_mod}>", ban.unban_reason),
                        ),
                    )

        return out

    async def on_member_join(self, member: Member):
        mute_role: Optional[Role] = member.guild.get_role(await RoleSettings.get("mute"))
        if mute_role is None:
            return

        if await db.exists(filter_by(Mute, active=True, member=member.id)):
            await member.add_roles(mute_role)

    @commands.command()
    @guild_only()
    async def report(self, ctx: Context, user: UserMemberConverter, *, reason: str):
        """
        report a user
        """

        user: Union[Member, User]

        if len(reason) > 900:
            raise CommandError(t.reason_too_long)

        if user == self.bot.user:
            raise UserCommandError(user, t.cannot_report)
        if user == ctx.author:
            raise UserCommandError(user, t.no_self_report)

        await Report.create(user.id, str(user), ctx.author.id, reason)
        server_embed = Embed(title=t.report, description=t.reported_response, colour=Colors.ModTools)
        server_embed.set_author(name=str(user), icon_url=user.avatar_url)
        await reply(ctx, embed=server_embed)
        await send_to_changelog_mod(ctx.guild, ctx.message, Colors.report, t.log_reported, user, reason)

    @commands.command()
    @ModPermission.warn.check
    @guild_only()
    async def warn(self, ctx: Context, user: UserMemberConverter, *, reason: str):
        """
        warn a user
        """

        user: Union[Member, User]

        if len(reason) > 900:
            raise CommandError(t.reason_too_long)

        if user == self.bot.user:
            raise UserCommandError(user, t.cannot_warn)

        user_embed = Embed(
            title=t.warn,
            description=t.warned(ctx.author.mention, ctx.guild.name, reason),
            colour=Colors.ModTools,
        )
        server_embed = Embed(title=t.warn, description=t.warned_response, colour=Colors.ModTools)
        server_embed.set_author(name=str(user), icon_url=user.avatar_url)
        try:
            await user.send(embed=user_embed)
        except (Forbidden, HTTPException):
            server_embed.description = t.no_dm + "\n\n" + server_embed.description
            server_embed.colour = Colors.error
        await Warn.create(user.id, str(user), ctx.author.id, reason)
        await reply(ctx, embed=server_embed)
        await send_to_changelog_mod(ctx.guild, ctx.message, Colors.warn, t.log_warned, user, reason)

    @commands.command()
    @ModPermission.mute.check
    @guild_only()
    async def mute(self, ctx: Context, user: UserMemberConverter, days: DurationConverter, *, reason: str):
        """
        mute a user
        set days to `inf` for a permanent mute
        """

        user: Union[Member, User]

        days: Optional[int]

        if len(reason) > 900:
            raise CommandError(t.reason_too_long)

        mute_role: Role = await get_mute_role(ctx.guild)

        if user == self.bot.user or await is_teamler(user):
            raise UserCommandError(user, t.cannot_mute)

        if isinstance(user, Member):
            check_role_assignable(mute_role)
            await user.add_roles(mute_role)
            await user.move_to(None)

        active_mutes: List[Mute] = await db.all(filter_by(Mute, active=True, member=user.id))
        for mute in active_mutes:
            if mute.days == -1:
                raise UserCommandError(user, t.already_muted)

            ts = mute.timestamp + timedelta(days=mute.days)
            if days is not None and datetime.utcnow() + timedelta(days=days) <= ts:
                raise UserCommandError(user, t.already_muted)

        for mute in active_mutes:
            await Mute.upgrade(mute.id, ctx.author.id)

        user_embed = Embed(title=t.mute, colour=Colors.ModTools)
        server_embed = Embed(title=t.mute, description=t.muted_response, colour=Colors.ModTools)
        server_embed.set_author(name=str(user), icon_url=user.avatar_url)

        if days is not None:
            await Mute.create(user.id, str(user), ctx.author.id, days, reason, bool(active_mutes))
            user_embed.description = t.muted(ctx.author.mention, ctx.guild.name, reason, cnt=days)
            await send_to_changelog_mod(
                ctx.guild,
                ctx.message,
                Colors.mute,
                t.log_muted,
                user,
                reason,
                duration=t.log_field.days(cnt=days),
            )
        else:
            await Mute.create(user.id, str(user), ctx.author.id, -1, reason, bool(active_mutes))
            user_embed.description = t.muted_inf(ctx.author.mention, ctx.guild.name, reason)
            await send_to_changelog_mod(
                ctx.guild,
                ctx.message,
                Colors.mute,
                t.log_muted,
                user,
                reason,
                duration=t.log_field.days_infinity,
            )

        try:
            await user.send(embed=user_embed)
        except (Forbidden, HTTPException):
            server_embed.description = t.no_dm + "\n\n" + server_embed.description
            server_embed.colour = Colors.error

        await reply(ctx, embed=server_embed)

    @commands.command()
    @ModPermission.mute.check
    @guild_only()
    async def unmute(self, ctx: Context, user: UserMemberConverter, *, reason: str):
        """
        unmute a user
        """

        user: Union[Member, User]

        if len(reason) > 900:
            raise CommandError(t.reason_too_long)

        mute_role: Role = await get_mute_role(ctx.guild)

        was_muted = False
        if isinstance(user, Member) and mute_role in user.roles:
            was_muted = True
            check_role_assignable(mute_role)
            await user.remove_roles(mute_role)

        async for mute in await db.stream(filter_by(Mute, active=True, member=user.id)):
            await Mute.deactivate(mute.id, ctx.author.id, reason)
            was_muted = True
        if not was_muted:
            raise UserCommandError(user, t.not_muted)

        server_embed = Embed(title=t.unmute, description=t.unmuted_response, colour=Colors.ModTools)
        server_embed.set_author(name=str(user), icon_url=user.avatar_url)
        await reply(ctx, embed=server_embed)
        await send_to_changelog_mod(ctx.guild, ctx.message, Colors.unmute, t.log_unmuted, user, reason)

    @commands.command()
    @ModPermission.kick.check
    @guild_only()
    async def kick(self, ctx: Context, member: Member, *, reason: str):
        """
        kick a member
        """

        if len(reason) > 900:
            raise CommandError(t.reason_too_long)

        if member == self.bot.user or await is_teamler(member):
            raise UserCommandError(member, t.cannot_kick)

        if not ctx.guild.me.guild_permissions.kick_members:
            raise CommandError(t.cannot_kick_permissions)

        if member.top_role >= ctx.guild.me.top_role or member.id == ctx.guild.owner_id:
            raise UserCommandError(member, t.cannot_kick)

        await Kick.create(member.id, str(member), ctx.author.id, reason)
        await send_to_changelog_mod(ctx.guild, ctx.message, Colors.kick, t.log_kicked, member, reason)

        user_embed = Embed(
            title=t.kick,
            description=t.kicked(ctx.author.mention, ctx.guild.name, reason),
            colour=Colors.ModTools,
        )
        server_embed = Embed(title=t.kick, description=t.kicked_response, colour=Colors.ModTools)
        server_embed.set_author(
            name=str(member),
            icon_url=member.avatar_url_as(format=("gif" if member.is_avatar_animated() else "png")),
        )

        try:
            await member.send(embed=user_embed)
        except (Forbidden, HTTPException):
            server_embed.description = t.no_dm + "\n\n" + server_embed.description
            server_embed.colour = Colors.error

        await member.kick(reason=reason)
        await revoke_verification(member)

        await reply(ctx, embed=server_embed)

    @commands.command()
    @ModPermission.ban.check
    @guild_only()
    async def ban(
        self,
        ctx: Context,
        user: UserMemberConverter,
        ban_days: DurationConverter,
        delete_days: int,
        *,
        reason: str,
    ):
        """
        ban a user
        set ban_days to `inf` for a permanent ban
        """

        ban_days: Optional[int]
        user: Union[Member, User]

        if not ctx.guild.me.guild_permissions.ban_members:
            raise CommandError(t.cannot_ban_permissions)

        if len(reason) > 900:
            raise CommandError(t.reason_too_long)
        if not 0 <= delete_days <= 7:
            raise CommandError(tg.invalid_duration)

        if user == self.bot.user or await is_teamler(user):
            raise UserCommandError(user, t.cannot_ban)
        if isinstance(user, Member) and (user.top_role >= ctx.guild.me.top_role or user.id == ctx.guild.owner_id):
            raise UserCommandError(user, t.cannot_ban)

        active_bans: List[Ban] = await db.all(filter_by(Ban, active=True, member=user.id))
        for ban in active_bans:
            if ban.days == -1:
                raise UserCommandError(user, t.already_banned)

            ts = ban.timestamp + timedelta(days=ban.days)
            if ban_days is not None and datetime.utcnow() + timedelta(days=ban_days) <= ts:
                raise UserCommandError(user, t.already_banned)

        for ban in active_bans:
            await Ban.upgrade(ban.id, ctx.author.id)
        async for mute in await db.stream(filter_by(Mute, active=True, member=user.id)):
            await Mute.upgrade(mute.id, ctx.author.id)

        user_embed = Embed(title=t.ban, colour=Colors.ModTools)
        server_embed = Embed(title=t.ban, description=t.banned_response, colour=Colors.ModTools)
        server_embed.set_author(name=str(user), icon_url=user.avatar_url)

        if ban_days is not None:
            await Ban.create(user.id, str(user), ctx.author.id, ban_days, reason, bool(active_bans))
            user_embed.description = t.banned(ctx.author.mention, ctx.guild.name, reason, cnt=ban_days)
            await send_to_changelog_mod(
                ctx.guild,
                ctx.message,
                Colors.ban,
                t.log_banned,
                user,
                reason,
                duration=t.log_field.days(cnt=ban_days),
            )
        else:
            await Ban.create(user.id, str(user), ctx.author.id, -1, reason, bool(active_bans))
            user_embed.description = t.banned_inf(ctx.author.mention, ctx.guild.name, reason)
            await send_to_changelog_mod(
                ctx.guild,
                ctx.message,
                Colors.ban,
                t.log_banned,
                user,
                reason,
                duration=t.log_field.days_infinity,
            )

        try:
            await user.send(embed=user_embed)
        except (Forbidden, HTTPException):
            server_embed.description = t.no_dm + "\n\n" + server_embed.description
            server_embed.colour = Colors.error

        await ctx.guild.ban(user, delete_message_days=delete_days, reason=reason)
        await revoke_verification(user)

        await reply(ctx, embed=server_embed)

    @commands.command()
    @ModPermission.ban.check
    @guild_only()
    async def unban(self, ctx: Context, user: UserMemberConverter, *, reason: str):
        """
        unban a user
        """

        user: Union[Member, User]

        if len(reason) > 900:
            raise CommandError(t.reason_too_long)

        if not ctx.guild.me.guild_permissions.ban_members:
            raise CommandError(t.cannot_unban_permissions)

        was_banned = True
        try:
            await ctx.guild.unban(user, reason=reason)
        except HTTPException:
            was_banned = False

        async for ban in await db.stream(filter_by(Ban, active=True, member=user.id)):
            was_banned = True
            await Ban.deactivate(ban.id, ctx.author.id, reason)
        if not was_banned:
            raise UserCommandError(user, t.not_banned)

        server_embed = Embed(title=t.unban, description=t.unbanned_response, colour=Colors.ModTools)
        server_embed.set_author(name=str(user), icon_url=user.avatar_url)
        await reply(ctx, embed=server_embed)
        await send_to_changelog_mod(ctx.guild, ctx.message, Colors.unban, t.log_unbanned, user, reason)
