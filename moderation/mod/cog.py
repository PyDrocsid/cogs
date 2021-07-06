import re
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from typing import Optional, Union, List, Tuple, Generator

from discord import Role, Guild, Member, Forbidden, HTTPException, User, Embed, NotFound, Message, Attachment
from discord.ext import commands, tasks
from discord.ext.commands import (
    guild_only,
    Context,
    CommandError,
    Converter,
    BadArgument,
    UserInputError,
)

from PyDrocsid.cog import Cog
from PyDrocsid.command import reply, UserCommandError, confirm
from PyDrocsid.converter import UserMemberConverter
from PyDrocsid.database import db, filter_by, db_wrapper
from PyDrocsid.settings import RoleSettings
from PyDrocsid.translations import t
from PyDrocsid.util import is_teamler
from PyDrocsid.config import Config
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
)

tg = t.g
t = t.mod


class DurationConverter(Converter):
    async def convert(self, ctx, argument: str) -> Optional[int]:
        if argument.lower() in ("inf", "perm", "permanent", "-1", "∞"):
            return None
        if (match := re.match(r"^(\d+y)?(\d+m)?(\d+w)?(\d+d)?(\d+h)?(\d+n)?$", argument)) is None:
            raise BadArgument(tg.invalid_duration)

        minutes = ToMinutes.convert(*[ToMinutes.toint(match.group(i)) for i in range(1, 7)])

        if minutes <= 0:
            raise BadArgument(tg.invalid_duration)
        if minutes >= (1 << 31):
            raise BadArgument(t.invalid_duration_inf)
        return minutes


class ToMinutes:
    @staticmethod
    def toint(value: str) -> int:
        return 0 if value is None else int(value[:-1])

    @staticmethod
    def convert(years: int, months: int, weeks: int, days: int, hours: int, minutes: int) -> int:
        days += years * 365
        days += months * 30
        days += weeks * 7

        td = timedelta(days=days, hours=hours, minutes=minutes)
        return int(td.total_seconds() / 60)


def time_to_units(minutes: Union[int, float]) -> str:
    rd = relativedelta(datetime.fromtimestamp(0) + timedelta(minutes=minutes),
                       datetime.fromtimestamp(0))  # Workaround that should be improved later

    def generator() -> Generator:
        for unit in [t.times.years(cnt=rd.years),
                     t.times.months(cnt=rd.months),
                     t.times.days(cnt=rd.days),
                     t.times.hours(cnt=rd.hours),
                     t.times.minutes(cnt=rd.minutes)]:
            if not str(unit).startswith("0"):
                yield str(unit)

    return ", ".join(generator())


async def get_mute_role(guild: Guild) -> Role:
    mute_role: Optional[Role] = guild.get_role(await RoleSettings.get("mute"))
    if mute_role is None:
        raise CommandError(t.mute_role_not_set)
    return mute_role


def show_evidence(evidence: Optional[str]) -> str:
    if evidence:
        return t.ulog.evidence(evidence)
    return ""


async def compare_mod_level(mod1: Member, mod2: Member) -> bool:
    lvl1 = await Config.PERMISSION_LEVELS.get_permission_level(mod1)
    lvl2 = await Config.PERMISSION_LEVELS.get_permission_level(mod2)

    return lvl1.level > lvl2.level or mod1 == mod1.guild.owner


async def send_to_changelog_mod(
    guild: Guild,
    message: Optional[Message],
    colour: int,
    title: str,
    member: Union[Member, User, Tuple[int, str]],
    reason: str,
    *,
    duration: Optional[str] = None,
    evidence: Optional[Attachment] = None,
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

    if evidence:
        embed.add_field(name=t.log_field.evidence, value=t.image_link(evidence.filename, evidence.url), inline=True)

    embed.add_field(name=t.log_field.reason, value=reason, inline=False)

    await send_to_changelog(guild, embed)


class ModCog(Cog, name="Mod Tools"):
    CONTRIBUTORS = [Contributor.Defelo, Contributor.wolflu, Contributor.Florian, Contributor.LoC]

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
            if ban.minutes != -1 and datetime.utcnow() >= ban.timestamp + timedelta(minutes=ban.minutes):
                await Ban.deactivate(ban.id)

                try:
                    await guild.unban(user := await self.bot.fetch_user(ban.member))
                except NotFound:
                    user = ban.member, ban.member_name

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

        async for mute in await db.stream(filter_by(Mute, active=True)):
            if mute.minutes != -1 and datetime.utcnow() >= mute.timestamp + timedelta(minutes=mute.minutes):
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
            if ban.minutes != -1:
                expiry_date: datetime = ban.timestamp + timedelta(minutes=ban.minutes)
                time_left = time_to_units((expiry_date - datetime.utcnow()).total_seconds() / 60 + 1)
                status = t.status_banned_time(time_to_units(ban.minutes), time_left)
            else:
                status = t.status_banned
        elif (mute := await db.get(Mute, member=user_id, active=True)) is not None:
            if mute.minutes != -1:
                expiry_date: datetime = mute.timestamp + timedelta(minutes=mute.minutes)
                time_left = time_to_units((expiry_date - datetime.utcnow()).total_seconds() / 60 + 1)
                status = t.status_muted_time(time_to_units(mute.minutes), time_left)
            else:
                status = t.status_muted
        return [(t.active_sanctions, status)]

    @get_userlog_entries.subscribe
    async def handle_get_userlog_entries(self, user_id: int, show_ids: bool) -> list[tuple[datetime, str]]:
        out: list[tuple[datetime, str]] = []

        report: Report
        async for report in await db.stream(filter_by(Report, member=user_id)):
            if show_ids:
                out.append(
                    (report.timestamp,
                     t.ulog.reported.id_on(f"<@{report.reporter}>", report.reason, report.id,
                                           show_evidence(report.evidence)
                                           )
                     )
                )
            else:
                out.append(
                    (report.timestamp,
                     t.ulog.reported.id_off(f"<@{report.reporter}>", report.reason, show_evidence(report.evidence))
                     )
                )

        warn: Warn
        async for warn in await db.stream(filter_by(Warn, member=user_id)):
            if show_ids:
                out.append(
                    (
                        warn.timestamp,
                        t.ulog.warned.id_on(f"<@{warn.mod}>", warn.reason, warn.id, show_evidence(warn.evidence))
                    )
                )
            else:
                out.append(
                    (
                        warn.timestamp,
                        t.ulog.warned.id_off(f"<@{warn.mod}>", warn.reason, show_evidence(warn.evidence))
                    )
                )

        mute: Mute
        async for mute in await db.stream(filter_by(Mute, member=user_id)):
            if mute.is_update:
                text = t.ulog.muted.update
                mute.evidence = None
            else:
                text = t.ulog.muted.first

            if mute.minutes == -1:
                if show_ids:
                    out.append(
                        (
                            mute.timestamp,
                            text.inf.id_on(f"<@{mute.mod}>", mute.reason, mute.id, show_evidence(mute.evidence))
                        )
                    )
                else:
                    out.append(
                        (
                            mute.timestamp,
                            text.inf.id_off(f"<@{mute.mod}>", mute.reason, show_evidence(mute.evidence))
                        )
                    )
            else:
                if show_ids:
                    out.append(
                        (
                            mute.timestamp,
                            text.temp.id_on(f"<@{mute.mod}>", time_to_units(mute.minutes), mute.reason, mute.id,
                                            show_evidence(mute.evidence)
                                            )
                        )
                    )
                else:
                    out.append(
                        (
                            mute.timestamp,
                            text.temp.id_off(f"<@{mute.mod}>", time_to_units(mute.minutes), mute.reason,
                                             show_evidence(mute.evidence)
                                             )
                        )
                    )

            if not mute.active and not mute.updated:
                if mute.unmute_mod is None:
                    out.append((mute.deactivation_timestamp, t.ulog.unmuted_expired))
                else:
                    if show_ids:
                        out.append(
                            (
                                mute.deactivation_timestamp,
                                t.ulog.unmuted.id_on(f"<@{mute.unmute_mod}>", mute.unmute_reason, mute.id),
                            ),
                        )
                    else:
                        out.append(
                            (
                                mute.deactivation_timestamp,
                                t.ulog.unmuted.id_off(f"<@{mute.unmute_mod}>", mute.unmute_reason),
                            ),
                        )

        kick: Kick
        async for kick in await db.stream(filter_by(Kick, member=user_id)):
            if kick.mod is not None:
                if show_ids:
                    out.append(
                        (
                            kick.timestamp,
                            t.ulog.kicked.id_on(f"<@{kick.mod}>", kick.reason, kick.id, show_evidence(kick.evidence))
                        )
                    )
                else:
                    out.append(
                        (
                            kick.timestamp,
                            t.ulog.kicked.id_off(f"<@{kick.mod}>", kick.reason, show_evidence(kick.evidence))
                        )
                    )
            else:
                out.append((kick.timestamp, t.ulog.autokicked))

        ban: Ban
        async for ban in await db.stream(filter_by(Ban, member=user_id)):
            if ban.is_upgrade:
                text = t.ulog.banned.upgrade
                ban.evidence = None
            else:
                text = t.ulog.banned.first

            if ban.minutes == -1:
                if show_ids:
                    out.append(
                        (
                            ban.timestamp,
                            text.inf.id_on(f"<@{ban.mod}>", ban.reason, ban.id, show_evidence(ban.evidence))
                        )
                    )
                else:
                    out.append(
                        (
                            ban.timestamp, text.inf.id_off(f"<@{ban.mod}>", ban.reason)
                        )
                    )
            else:
                if show_ids:
                    out.append(
                        (
                            ban.timestamp,
                            text.temp.id_on(f"<@{ban.mod}>", time_to_units(ban.minutes), ban.reason, ban.id,
                                            show_evidence(ban.evidence)
                                            )
                        )
                    )
                else:
                    out.append(
                        (
                            ban.timestamp,
                            text.temp.id_off(f"<@{ban.mod}>", time_to_units(ban.minutes), ban.reason,
                                             show_evidence(ban.evidence)
                                             )
                        )
                    )

            if not ban.active and not ban.upgraded:
                if ban.unban_mod is None:
                    out.append((ban.deactivation_timestamp, t.ulog.unbanned_expired))
                else:
                    if show_ids:
                        out.append(
                            (
                                ban.deactivation_timestamp,
                                t.ulog.unbanned.id_on(f"<@{ban.unban_mod}>", ban.unban_reason, ban.id),
                            ),
                        )
                    else:
                        out.append(
                            (
                                ban.deactivation_timestamp,
                                t.ulog.unbanned.id_off(f"<@{ban.unban_mod}>", ban.unban_reason),
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

        if attachments := ctx.message.attachments:
            evidence = attachments[0]
            evidence_url = evidence.url
        else:
            evidence = None
            evidence_url = None

        await Report.create(user.id, str(user), ctx.author.id, reason, evidence_url)
        server_embed = Embed(title=t.report, description=t.reported_response, colour=Colors.ModTools)
        server_embed.set_author(name=str(user), icon_url=user.avatar_url)
        await reply(ctx, embed=server_embed)
        await send_to_changelog_mod(ctx.guild,
                                    ctx.message, Colors.report, t.log_reported, user, reason, evidence=evidence)

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

        if attachments := ctx.message.attachments:
            evidence = attachments[0]
            evidence_url = evidence.url
        else:
            evidence = None
            evidence_url = None

        user_embed = Embed(
            title=t.warn,
            colour=Colors.ModTools,
        )
        if evidence:
            user_embed.description = t.warned.evidence(ctx.author.mention, ctx.guild.name, reason,
                                                       t.image_link(evidence.filename, evidence_url),
                                                       )
        else:
            user_embed.description = t.warned.no_evidence(ctx.author.mention, ctx.guild.name, reason)

        server_embed = Embed(title=t.warn, description=t.warned_response, colour=Colors.ModTools)
        server_embed.set_author(name=str(user), icon_url=user.avatar_url)
        try:
            await user.send(embed=user_embed)
        except (Forbidden, HTTPException):
            server_embed.description = t.no_dm + "\n\n" + server_embed.description
            server_embed.colour = Colors.error
        await Warn.create(user.id, str(user), ctx.author.id, reason, evidence.url)
        await reply(ctx, embed=server_embed)
        await send_to_changelog_mod(ctx.guild, ctx.message, Colors.warn, t.log_warned, user, reason, evidence=evidence)

    @commands.command()
    @ModPermission.warn.check
    @guild_only()
    async def edit_warn(self, ctx: Context, warn_id: int, *, reason: str):
        """
        edit a warn
        get the warn id from the users user log
        """

        warn = await db.get(Warn, id=warn_id)
        if warn is None:
            raise CommandError(t.no_warn)

        if not await compare_mod_level(ctx.author, ctx.guild.get_member(warn.mod)):
            raise CommandError(tg.permission_denied)

        if len(reason) > 900:
            raise CommandError(t.reason_too_long)

        conf_embed = Embed(
            title=t.confirmation,
            description=t.confirm_warn_edit(warn.reason, reason),
            color=Colors.ModTools
        )

        async with confirm(ctx, conf_embed) as (result, msg):
            if not result:
                conf_embed.description += "\n\n" + t.edit_canceled
                return

            conf_embed.description += "\n\n" + t.edit_confirmed
            if msg:
                await msg.delete(delay=5)

        await Warn.edit(warn_id, ctx.author.id, reason)

        user = self.bot.get_user(warn.member)

        user_embed = Embed(
            title=t.warn,
            description=t.warn_edited(warn.reason, reason),
            colour=Colors.ModTools,
        )
        server_embed = Embed(title=t.warn, description=t.warn_edited_response, colour=Colors.ModTools)
        server_embed.set_author(name=str(user), icon_url=user.avatar_url)

        try:
            await user.send(embed=user_embed)
        except (Forbidden, HTTPException):
            server_embed.description = t.no_dm + "\n\n" + server_embed.description
            server_embed.colour = Colors.error
        await reply(ctx, embed=server_embed)
        await send_to_changelog_mod(ctx.guild, ctx.message, Colors.warn, t.log_warn_edited, user, reason)

    @commands.command()
    @ModPermission.mute.check
    @guild_only()
    async def mute(self, ctx: Context, user: UserMemberConverter, time: DurationConverter, *, reason: str):
        """
        mute a user
        time format: `ymwdhn`
        set time to `inf` for a permanent mute
        """

        user: Union[Member, User]

        time: Optional[int]
        minutes = time

        if len(reason) > 900:
            raise CommandError(t.reason_too_long)

        mute_role: Role = await get_mute_role(ctx.guild)

        if user == self.bot.user or await is_teamler(user):
            raise UserCommandError(user, t.cannot_mute)

        if isinstance(user, Member):
            await user.add_roles(mute_role)
            await user.move_to(None)

        active_mutes: List[Mute] = await db.all(filter_by(Mute, active=True, member=user.id))
        if active_mutes:
            raise UserCommandError(user, t.already_muted)

        if attachments := ctx.message.attachments:
            evidence = attachments[0]
            evidence_url = evidence.url
        else:
            evidence = None
            evidence_url = None

        user_embed = Embed(title=t.mute, colour=Colors.ModTools)
        server_embed = Embed(title=t.mute, description=t.muted_response, colour=Colors.ModTools)
        server_embed.set_author(name=str(user), icon_url=user.avatar_url)

        if minutes is not None:
            await Mute.create(user.id, str(user), ctx.author.id, minutes, reason, evidence_url)
            if evidence:
                user_embed.description = t.muted.evidence(ctx.author.mention, ctx.guild.name, time_to_units(minutes),
                                                          reason, t.image_link(evidence.filename, evidence_url),
                                                          )
            else:
                user_embed.description = t.muted.no_evidence(ctx.author.mention, ctx.guild.name, time_to_units(minutes),
                                                             reason,
                                                             )

            await send_to_changelog_mod(
                ctx.guild,
                ctx.message,
                Colors.mute,
                t.log_muted,
                user,
                reason,
                duration=time_to_units(minutes),
                evidence=evidence,
            )
        else:
            await Mute.create(user.id, str(user), ctx.author.id, -1, reason, evidence_url)
            if evidence:
                user_embed.description = t.muted_inf.evidence(ctx.author.mention, ctx.guild.name, reason,
                                                              t.image_link(evidence.filename, evidence_url),
                                                              )
            else:
                user_embed.description = t.muted_inf.no_evidence(ctx.author.mention, ctx.guild.name, reason)

            await send_to_changelog_mod(
                ctx.guild,
                ctx.message,
                Colors.mute,
                t.log_muted,
                user,
                reason,
                duration=t.log_field.infinity,
                evidence=evidence,
            )

        try:
            await user.send(embed=user_embed)
        except (Forbidden, HTTPException):
            server_embed.description = t.no_dm + "\n\n" + server_embed.description
            server_embed.colour = Colors.error

        await reply(ctx, embed=server_embed)

    @commands.group()
    @ModPermission.mute.check
    @guild_only()
    async def edit_mute(self, ctx):
        """
        edit a mute
        """

        if ctx.invoked_subcommand is None:
            raise UserInputError

    @edit_mute.command(name="reason")
    async def edit_mute_reason(self, ctx: Context, mute_id: int, *, reason: str):
        """
        edit a mute
        get the mute id from the users user log
        """

        mute = await db.get(Mute, id=mute_id)
        if mute is None:
            raise CommandError(t.no_mute)

        if not await compare_mod_level(ctx.author, ctx.guild.get_member(mute.mod)):
            raise CommandError(tg.permission_denied)

        if len(reason) > 900:
            raise CommandError(t.reason_too_long)

        conf_embed = Embed(
            title=t.confirmation,
            description=t.confirm_mute_edit.reason(mute.reason, reason),
            color=Colors.ModTools
        )

        async with confirm(ctx, conf_embed) as (result, msg):
            if not result:
                conf_embed.description += "\n\n" + t.edit_canceled
                return

            conf_embed.description += "\n\n" + t.edit_confirmed
            if msg:
                await msg.delete(delay=5)

        await Mute.edit(mute_id, ctx.author.id, reason)

        user = self.bot.get_user(mute.member)

        user_embed = Embed(
            title=t.mute,
            description=t.mute_edited.reason(mute.reason, reason),
            colour=Colors.ModTools,
        )
        server_embed = Embed(title=t.mute, description=t.mute_edited_response, colour=Colors.ModTools)
        server_embed.set_author(name=str(user), icon_url=user.avatar_url)

        try:
            await user.send(embed=user_embed)
        except (Forbidden, HTTPException):
            server_embed.description = t.no_dm + "\n\n" + server_embed.description
            server_embed.colour = Colors.error
        await reply(ctx, embed=server_embed)
        await send_to_changelog_mod(ctx.guild, ctx.message, Colors.mute, t.log_mute_edited, user, reason)

    @edit_mute.command(name="duration")
    async def edit_mute_duration(self, ctx: Context, user: UserMemberConverter, time: DurationConverter):
        """
        edit a mute duration
        time format: `ymwdhn`
        set time to `inf` for a permanent mute
        """

        user: Union[Member, User]
        time: Optional[int]
        minutes = time

        active_mutes: List[Mute] = await db.all(filter_by(Mute, active=True, member=user.id))

        if not active_mutes:
            raise CommandError(t.not_muted)

        mute = sorted(active_mutes, key=lambda active_mute: active_mute.timestamp)[0]

        if not await compare_mod_level(ctx.author, ctx.guild.get_member(mute.mod)):
            raise CommandError(tg.permission_denied)

        conf_embed = Embed(
            title=t.confirmation,
            color=Colors.ModTools,
        )

        if minutes is None:
            conf_embed.description = t.confirm_mute_edit.duration(time_to_units(mute.minutes), t.infinity)
        else:
            conf_embed.description = t.confirm_mute_edit.duration(time_to_units(mute.minutes), time_to_units(minutes))

        async with confirm(ctx, conf_embed) as (result, msg):
            if not result:
                conf_embed.description += "\n\n" + t.edit_canceled
                return

            conf_embed.description += "\n\n" + t.edit_confirmed
            if msg:
                await msg.delete(delay=5)

        for mute in active_mutes:
            await Mute.update(mute.id, ctx.author.id)

        user_embed = Embed(
            title=t.mute,
            colour=Colors.ModTools,
        )
        server_embed = Embed(title=t.mute, description=t.mute_edited_response, colour=Colors.ModTools)
        server_embed.set_author(name=str(user), icon_url=user.avatar_url)

        if minutes is not None:
            await Mute.create(user.id, str(user), ctx.author.id, minutes, mute.reason, mute.evidence, True)
            user_embed.description = t.mute_edited.duration(time_to_units(mute.minutes), time_to_units(minutes))
            await send_to_changelog_mod(
                ctx.guild,
                ctx.message,
                Colors.mute,
                t.log_mute_edited,
                user,
                mute.reason,
                duration=time_to_units(minutes),
            )

        else:
            await Mute.create(user.id, str(user), ctx.author.id, -1, mute.reason, mute.evidence, True)
            user_embed.description = t.mute_edited.duration(time_to_units(mute.minutes), t.infinity)
            await send_to_changelog_mod(
                ctx.guild,
                ctx.message,
                Colors.mute,
                t.log_mute_edited,
                user, mute.reason,
                duration=t.log_field.infinity,
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

        if attachments := ctx.message.attachments:
            evidence = attachments[0]
            evidence_url = evidence.url
        else:
            evidence = None
            evidence_url = None

        await Kick.create(member.id, str(member), ctx.author.id, reason, evidence_url)
        await send_to_changelog_mod(ctx.guild, ctx.message, Colors.kick, t.log_kicked, member, reason,
                                    evidence=evidence)

        user_embed = Embed(
            title=t.kick,
            colour=Colors.ModTools,
        )

        if evidence:
            user_embed.description = t.kicked.evidence(ctx.author.mention, ctx.guild.name, reason,
                                                       t.image_link(evidence.filename, evidence_url),
                                                       )
        else:
            user_embed.description = t.kicked.no_evidence(ctx.author.mention, ctx.guild.name, reason)

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
        time: DurationConverter,
        delete_days: int,
        *,
        reason: str,
    ):
        """
        ban a user
        time format: `ymwdhn`
        set ban_days to `inf` for a permanent ban
        """

        time: Optional[int]
        minutes = time

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
            if ban.minutes == -1:
                raise UserCommandError(user, t.already_banned)

            ts = ban.timestamp + timedelta(minutes=ban.minutes)
            if minutes is not None and datetime.utcnow() + timedelta(minutes=minutes) <= ts:
                raise UserCommandError(user, t.already_banned)

        for ban in active_bans:
            await Ban.upgrade(ban.id, ctx.author.id)
        async for mute in await db.stream(filter_by(Mute, active=True, member=user.id)):
            await Mute.upgrade(mute.id, ctx.author.id)

        if attachments := ctx.message.attachments:
            evidence = attachments[0]
            evidence_url = evidence.url
        else:
            evidence = None
            evidence_url = None

        user_embed = Embed(title=t.ban, colour=Colors.ModTools)
        server_embed = Embed(title=t.ban, description=t.banned_response, colour=Colors.ModTools)
        server_embed.set_author(name=str(user), icon_url=user.avatar_url)

        if minutes is not None:
            await Ban.create(user.id, str(user), ctx.author.id, minutes, reason, evidence_url, bool(active_bans))
            if evidence:
                user_embed.description = t.banned.evidence(ctx.author.mention, ctx.guild.name, time_to_units(minutes),
                                                           reason, t.image_link(evidence.filename, evidence_url)
                                                           )
            else:
                user_embed.description = t.banned.no_evidence(ctx.author.mention, ctx.guild.name,
                                                              time_to_units(minutes), reason
                                                              )
            await send_to_changelog_mod(
                ctx.guild,
                ctx.message,
                Colors.ban,
                t.log_banned,
                user,
                reason,
                duration=time_to_units(minutes),
                evidence=evidence,
            )
        else:
            await Ban.create(user.id, str(user), ctx.author.id, -1, reason, evidence_url, bool(active_bans))
            if evidence:
                user_embed.description = t.banned.evidence(ctx.author.mention, ctx.guild.name, reason,
                                                           t.image_link(evidence.filename, evidence_url)
                                                           )
            else:
                user_embed.description = t.banned.evidence(ctx.author.mention, ctx.guild.name, reason)

            await send_to_changelog_mod(
                ctx.guild,
                ctx.message,
                Colors.ban,
                t.log_banned,
                user,
                reason,
                duration=t.log_field.infinity,
                evidence=evidence
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
