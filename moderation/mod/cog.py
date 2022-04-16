import re
from asyncio import sleep
from datetime import datetime, timedelta
from typing import List, Tuple, Type, TypeVar

from dateutil.relativedelta import relativedelta
from discord import (
    Role,
    Guild,
    Member,
    Forbidden,
    HTTPException,
    User,
    Embed,
    NotFound,
    Message,
    Attachment,
    AuditLogAction,
    AuditLogEntry,
    TextChannel,
    Thread,
)
from discord.ext import commands, tasks
from discord.ext.commands import guild_only, Context, CommandError, Converter, BadArgument, UserInputError
from discord.utils import utcnow

from PyDrocsid.cog import Cog
from PyDrocsid.command import reply, UserCommandError, confirm, docs
from PyDrocsid.config import Config
from PyDrocsid.converter import UserMemberConverter
from PyDrocsid.database import db, filter_by, db_wrapper, Base as DBBase
from PyDrocsid.environment import CACHE_TTL
from PyDrocsid.redis import redis
from PyDrocsid.settings import RoleSettings
from PyDrocsid.translations import t
from PyDrocsid.util import is_teamler, check_role_assignable
from .colors import Colors
from .models import Mute, Ban, Report, Warn, Kick
from .permissions import ModPermission
from .settings import ModSettings
from ...contributor import Contributor
from ...pubsub import (
    send_to_changelog,
    send_alert,
    log_auto_kick,
    get_userlog_entries,
    get_user_info_entries,
    get_user_status_entries,
    revoke_verification,
)

tg = t.g
t = t.mod
TBase = TypeVar("TBase", bound=DBBase)


class DurationConverter(Converter):
    async def convert(self, ctx, argument: str) -> int | None:
        if argument.lower() in ("inf", "perm", "permanent", "-1", "∞"):
            return None
        if (match := re.match(r"^(\d+w)?(\d+d)?(\d+h)?(\d+m)?$", argument)) is None:
            raise BadArgument(tg.invalid_duration)

        weeks, days, hours, minutes = [0 if (value := match.group(i)) is None else int(value[:-1]) for i in range(1, 5)]

        days += weeks * 7
        td = timedelta(days=days, hours=hours, minutes=minutes)
        duration = int(td.total_seconds() / 60)

        if duration <= 0:
            raise BadArgument(tg.invalid_duration)
        if duration >= (1 << 31):
            raise BadArgument(t.invalid_duration_inf)
        return duration


async def load_entries():
    async def fill(db_model: Type[TBase]):
        async with redis.pipeline() as pipe:
            await pipe.delete(entry_key := f"mod_entries:{db_model.__tablename__}")

            async for entry in await db.stream(filter_by(db_model, active=True)):
                if entry.minutes == -1:
                    continue

                expiration_timestamp = entry.timestamp + timedelta(minutes=entry.minutes)

                await pipe.hmset(entry_key, {str(entry.id): str(expiration_timestamp)})

            await pipe.expire(entry_key, CACHE_TTL)
            await pipe.execute()

    if await redis.exists("mod_entries_loaded"):
        return

    await fill(Ban)
    await fill(Mute)

    await redis.setex("mod_entries_loaded", CACHE_TTL, 1)


async def invalidate_entry_cache():
    await redis.delete("mod_entries_loaded")


def time_to_units(minutes: int | float) -> str:
    _keys = ("years", "months", "days", "hours", "minutes")

    rd = relativedelta(
        datetime.fromtimestamp(0) + timedelta(minutes=minutes), datetime.fromtimestamp(0)
    )  # Workaround that should be improved later

    def get_func(key, value):
        func = getattr(t.times, key)
        return func(cnt=value)

    return ", ".join(get_func(key, time) for key in _keys if (time := getattr(rd, key)) != 0)


async def get_mute_role(guild: Guild) -> Role:
    mute_role: Role | None = guild.get_role(await RoleSettings.get("mute"))
    if mute_role is None:
        await send_alert(guild, t.mute_role_not_set)
    return mute_role


def show_evidence(evidence: str | None) -> str:
    return t.ulog.evidence(evidence) if evidence else ""


async def get_mod_level(mod: Member) -> int:
    return (await Config.PERMISSION_LEVELS.get_permission_level(mod)).level


async def compare_mod_level(mod: Member, mod_level: int) -> bool:
    return await get_mod_level(mod) > mod_level or mod == mod.guild.owner


async def get_and_compare_entry(entry_format: Type[TBase], entry_id: int, mod: Member) -> TBase:
    entry = await db.get(entry_format, id=entry_id)
    if entry is None:
        raise CommandError(getattr(t.not_found, entry_format.__tablename__))

    if mod.id != entry.mod and not await compare_mod_level(mod, entry.mod_level):
        raise CommandError(tg.permission_denied)

    return entry


async def confirm_action(
    ctx: Context, embed: Embed, message_confirmed: str = t.edit_confirmed, message_canceled: str = t.edit_canceled
) -> bool:
    async with confirm(ctx, embed) as (result, msg):
        if not result:
            embed.description += f"\n\n{message_canceled}"
            return result

        embed.description += f"\n\n{message_confirmed}"
        if msg:
            await msg.delete(delay=5)
        return result


async def confirm_no_evidence(ctx: Context):
    conf_embed = Embed(title=t.confirmation, description=t.no_evidence, color=Colors.ModTools)

    return await confirm_action(ctx, conf_embed, t.action_confirmed, t.action_cancelled)


async def send_to_changelog_mod(
    guild: Guild,
    message: Message | None,
    colour: int,
    title: str,
    member: Member | User | Tuple[int, str],
    reason: str,
    *,
    duration: str | None = None,
    evidence: Attachment | None = None,
    mod: Member | User | None = None,
    original_reason: str | None = None,
):
    embed = Embed(title=title, colour=colour, timestamp=utcnow())

    if isinstance(member, tuple):
        member_id, member_name = member
        embed.set_author(name=member_name)
    else:
        member_id: int = member.id
        member_name: str = str(member)
        embed.set_author(name=member_name, icon_url=member.display_avatar.url)

    embed.add_field(name=t.log_field.member, value=f"<@{member_id}>", inline=True)
    embed.add_field(name=t.log_field.member_id, value=str(member_id), inline=True)

    if message:
        embed.set_footer(text=str(message.author), icon_url=message.author.display_avatar.url)
        embed.add_field(
            name=t.log_field.channel, value=t.jump_url(message.channel.mention, message.jump_url), inline=True
        )

    if duration:
        embed.add_field(name=t.log_field.duration, value=duration, inline=True)

    if evidence:
        embed.add_field(name=t.log_field.evidence, value=t.image_link(evidence.filename, evidence.url), inline=True)

    if mod:
        embed.add_field(name=t.log_field.mod, value=f"<@{mod.id}>", inline=True)

    if original_reason:
        embed.add_field(name=t.log_field_original_reason, value=original_reason, inline=True)

    embed.add_field(name=t.log_field.reason, value=reason, inline=False)

    await send_to_changelog(guild, embed)


class ModCog(Cog, name="Mod Tools"):
    CONTRIBUTORS = [Contributor.Defelo, Contributor.wolflu, Contributor.Florian, Contributor.LoC]

    async def on_ready(self):
        guild: Guild = self.bot.guilds[0]
        mute_role: Role | None = guild.get_role(await RoleSettings.get("mute"))
        if mute_role is not None:
            async for mute in await db.stream(filter_by(Mute, active=True)):
                member: Member | None = guild.get_member(mute.member)
                if member is not None:
                    await member.add_roles(mute_role)

        try:
            self.mod_loop.start()
        except RuntimeError:
            self.mod_loop.restart()

    @tasks.loop(minutes=1)
    @db_wrapper
    async def mod_loop(self):
        guild: Guild = self.bot.guilds[0]
        await load_entries()

        ban_keys = await redis.hkeys(ban_entries_key := f"mod_entries:{Ban.__tablename__}")

        for key in ban_keys:
            if utcnow() >= datetime.fromisoformat(await redis.hget(ban_entries_key, key)):
                ban = await db.get(Ban, id=int(key))

                try:
                    await guild.unban(user := await self.bot.fetch_user(ban.member))
                except NotFound:
                    user = ban.member, ban.member_name
                except Forbidden:
                    await send_alert(guild, t.cannot_unban_permissions)
                    continue

                await Ban.deactivate(ban.id)

                await redis.hdel(ban_entries_key, key)

                await send_to_changelog_mod(
                    guild=guild,
                    message=None,
                    colour=Colors.unban,
                    title=t.log_unbanned,
                    member=user,
                    reason=t.log_unbanned_expired,
                )

        mute_role: Role | None = guild.get_role(await RoleSettings.get("mute"))
        if mute_role is None:
            return

        try:
            check_role_assignable(mute_role)
        except CommandError:
            await send_alert(guild, t.cannot_assign_mute_role(mute_role, mute_role.id))
            return

        mute_keys = await redis.hkeys(mute_entries_key := f"mod_entries:{Mute.__tablename__}")

        for key in mute_keys:
            if utcnow() >= datetime.fromisoformat(await redis.hget(mute_entries_key, key)):
                mute = await db.get(Mute, id=int(key))

                if member := guild.get_member(mute.member):
                    await member.remove_roles(mute_role)
                else:
                    member = mute.member, mute.member_name

                await send_to_changelog_mod(
                    guild=guild,
                    message=None,
                    colour=Colors.unmute,
                    title=t.log_unmuted,
                    member=member,
                    reason=t.log_unmuted_expired,
                )

                await Mute.deactivate(mute.id)

                await redis.hdel(mute_entries_key, key)

    @log_auto_kick.subscribe
    async def handle_log_auto_kick(self, member: Member):
        await Kick.create(member.id, str(member), None, None, None, None)

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
                time_left = time_to_units((expiry_date - utcnow()).total_seconds() / 60 + 1)
                status = t.status_banned_time(time_to_units(ban.minutes), time_left)
            else:
                status = t.status_banned
        elif (mute := await db.get(Mute, member=user_id, active=True)) is not None:
            if mute.minutes != -1:
                expiry_date: datetime = mute.timestamp + timedelta(minutes=mute.minutes)
                time_left = time_to_units((expiry_date - utcnow()).total_seconds() / 60 + 1)
                status = t.status_muted_time(time_to_units(mute.minutes), time_left)
            else:
                status = t.status_muted
        return [(t.active_sanctions, status)]

    @get_userlog_entries.subscribe
    async def handle_get_userlog_entries(
        self, user_id: int, show_ids: bool, author: Member
    ) -> list[tuple[datetime, str]]:
        def wrap_time_entry(
            translation,
            mod: int,
            reason: str,
            evidence: str,
            minutes: int | None = None,
            entry_id: int | None = None,
        ) -> str:
            args = [f"<@{mod}>"]

            if minutes:
                translation = translation.temp
                args.append(time_to_units(minutes))
            else:
                translation = translation.inf

            args.append(reason)

            if entry_id:
                translation = translation.id_on
                args.append(entry_id)
            else:
                translation = translation.id_off

            args.append(show_evidence(evidence))

            return translation(*args)

        def wrap_entry(translation, user: int, reason: str, evidence: str | None, entry_id: int | None = None) -> str:
            if entry_id:
                return translation.id_on(f"<@{user}>", reason, entry_id, show_evidence(evidence))
            else:
                return translation.id_off(f"<@{user}>", reason, show_evidence(evidence))

        out: list[tuple[datetime, str]] = []

        if await is_teamler(author):
            report: Report
            async for report in await db.stream(filter_by(Report, member=user_id)):
                out.append(
                    (
                        report.timestamp,
                        wrap_entry(
                            t.ulog.reported,
                            report.reporter,
                            report.reason,
                            report.evidence,
                            report.id if show_ids else None,
                        ),
                    )
                )

        warn: Warn
        async for warn in await db.stream(filter_by(Warn, member=user_id)):
            out.append(
                (
                    warn.timestamp,
                    wrap_entry(t.ulog.warned, warn.mod, warn.reason, warn.evidence, warn.id if show_ids else None),
                )
            )

        mute: Mute
        async for mute in await db.stream(filter_by(Mute, member=user_id)):
            out.append(
                (
                    mute.timestamp,
                    wrap_time_entry(
                        translation=t.ulog.muted,
                        mod=mute.mod,
                        reason=mute.reason,
                        evidence=mute.evidence,
                        minutes=mute.minutes if mute.minutes != -1 else None,
                        entry_id=mute.id if show_ids else None,
                    ),
                )
            )

            if not mute.active:
                if mute.deactivate_mod is None:
                    out.append((mute.deactivation_timestamp, t.ulog.unmuted_expired))
                else:
                    out.append(
                        (
                            mute.deactivation_timestamp,
                            wrap_entry(
                                translation=t.unmuted,
                                user=mute.deactivate_mod,
                                reason=mute.deactivate_reason,
                                evidence=None,
                                entry_id=mute.id if show_ids else None,
                            ),
                        )
                    )

        kick: Kick
        async for kick in await db.stream(filter_by(Kick, member=user_id)):
            if kick.mod is not None:
                out.append(
                    (
                        kick.timestamp,
                        wrap_entry(t.ulog.kicked, kick.mod, kick.reason, kick.evidence, kick.id if show_ids else None),
                    )
                )
            else:
                out.append((kick.timestamp, t.ulog.autokicked))

        ban: Ban
        async for ban in await db.stream(filter_by(Ban, member=user_id)):
            out.append(
                (
                    ban.timestamp,
                    wrap_time_entry(
                        translation=t.ulog.banned,
                        mod=ban.mod,
                        reason=ban.reason,
                        evidence=ban.evidence,
                        minutes=ban.minutes if ban.minutes != -1 else None,
                        entry_id=ban.id if show_ids else None,
                    ),
                )
            )

            if not ban.active:
                if ban.deactivate_mod is None:
                    out.append((ban.deactivation_timestamp, t.ulog.unbanned_expired))
                else:
                    out.append(
                        (
                            ban.deactivation_timestamp,
                            wrap_entry(
                                translation=t.ulog.unbanned,
                                user=ban.deactivate_mod,
                                reason=ban.deactivate_reason,
                                evidence=None,
                                entry_id=ban.id if show_ids else None,
                            ),
                        )
                    )

        return out

    async def on_member_join(self, member: Member):
        mute_role: Role | None = member.guild.get_role(await RoleSettings.get("mute"))
        if mute_role is None:
            return

        if await db.exists(filter_by(Mute, active=True, member=member.id)):
            await member.add_roles(mute_role)

    async def on_member_ban(self, guild: Guild, member: Member):
        search_limit = 100
        for i in range(10, 1, -1):

            try:
                entry: AuditLogEntry
                async for entry in guild.audit_logs(limit=search_limit, action=AuditLogAction.ban):
                    if entry.user == self.bot.user:
                        continue

                    if member.id != entry.target.id:
                        continue

                    if entry.reason:
                        await Ban.create(
                            entry.target.id,
                            str(entry.target),
                            entry.user.id,
                            await get_mod_level(entry.user),
                            -1,
                            entry.reason,
                            None,
                        )

                        await send_to_changelog_mod(
                            guild=guild,
                            message=None,
                            colour=Colors.ban,
                            title=t.log_banned,
                            member=entry.target,
                            reason=entry.reason,
                            duration=t.log_field.infinity,
                        )

                    else:
                        await send_alert(guild, t.alert_member_banned(str(entry.target), str(entry.user)))

                    return

            except Forbidden:
                await send_alert(guild, t.cannot_fetch_audit_logs)

            await sleep(delay=i * 10)
            search_limit -= i * 10

    @commands.command()
    @guild_only()
    @ModPermission.modtools_write.check
    @docs(t.commands.send_delete_message)
    async def send_delete_message(self, ctx: Context, send: bool | None = None):
        embed = Embed(title=t.modtools, color=Colors.ModTools)

        if send is None:
            send = await ModSettings.send_delete_user_message.get()
            embed.description = t.current_send_delete_message[send]
        else:
            await ModSettings.send_delete_user_message.set(send)
            embed.description = t.configured_send_delete_message[send]

        await reply(ctx, embed=embed)
        await send_to_changelog(ctx.guild, t.configured_send_delete_message[send])

    @commands.command()
    @docs(t.commands.report)
    async def report(self, ctx: Context, user: UserMemberConverter, *, reason: str):
        user: Member | User

        if len(reason) > 900:
            raise CommandError(t.reason_too_long)

        if user == self.bot.user:
            raise UserCommandError(user, t.cannot_report)
        if user == ctx.author:
            raise UserCommandError(user, t.no_self_report)

        conf_embed = Embed(
            title=t.confirmation, description=t.confirm_report(user.mention, reason), color=Colors.ModTools
        )

        if not await confirm_action(ctx, conf_embed, t.report_confirmed, t.report_canceled):
            return

        attachments = ctx.message.attachments
        evidence = attachments[0] if attachments else None
        evidence_url = evidence.url if attachments else None

        await Report.create(user.id, str(user), ctx.author.id, reason, evidence_url)
        server_embed = Embed(title=t.report, description=t.reported_response, colour=Colors.ModTools)
        server_embed.set_author(name=str(user), icon_url=user.display_avatar.url)
        await reply(ctx, embed=server_embed)

        alert_embed = Embed(
            title=t.report,
            description=t.alert_report(ctx.author.mention, user.mention, reason),
            color=Colors.report,
            timestamp=utcnow(),
        )

        if type(ctx.channel) in (Thread, TextChannel):
            alert_embed.add_field(
                name=t.log_field.channel, value=t.jump_url(ctx.channel.mention, ctx.message.jump_url), inline=True
            )
        if evidence:
            alert_embed.add_field(
                name=t.log_field.evidence, value=t.image_link(evidence.filename, evidence_url), inline=True
            )

        await send_alert(self.bot.guilds[0], alert_embed)

    @commands.command()
    @ModPermission.warn.check
    @guild_only()
    @docs(t.commands.warn)
    async def warn(self, ctx: Context, user: UserMemberConverter, *, reason: str):
        user: Member | User

        if len(reason) > 900:
            raise CommandError(t.reason_too_long)

        if user == self.bot.user:
            raise UserCommandError(user, t.cannot_warn)

        attachments = ctx.message.attachments
        evidence = attachments[0] if attachments else None
        evidence_url = evidence.url if attachments else None

        if not evidence:
            if not await confirm_no_evidence(ctx):
                return

        user_embed = Embed(
            title=t.warn, colour=Colors.ModTools, description=t.warned(ctx.author.mention, ctx.guild.name, reason)
        )

        server_embed = Embed(title=t.warn, description=t.warned_response, colour=Colors.ModTools)
        server_embed.set_author(name=str(user), icon_url=user.display_avatar.url)
        try:
            await user.send(embed=user_embed)
        except (Forbidden, HTTPException):
            server_embed.description = f"{t.no_dm}\n\n{server_embed.description}"
            server_embed.colour = Colors.error
        await Warn.create(user.id, str(user), ctx.author.id, await get_mod_level(ctx.author), reason, evidence_url)
        await reply(ctx, embed=server_embed)
        await send_to_changelog_mod(
            guild=ctx.guild,
            message=ctx.message,
            colour=Colors.warn,
            title=t.log_warned,
            member=user,
            reason=reason,
            evidence=evidence,
        )

    @commands.command(aliases=["warn_edit"])
    @ModPermission.warn.check
    @guild_only()
    @docs(t.commands.edit_warn)
    async def edit_warn(self, ctx: Context, warn_id: int, *, reason: str):
        warn = await get_and_compare_entry(Warn, warn_id, ctx.author)

        if len(reason) > 900:
            raise CommandError(t.reason_too_long)

        conf_embed = Embed(
            title=t.confirmation, description=t.confirm_warn_edit(warn.reason, reason), color=Colors.ModTools
        )

        if not await confirm_action(ctx, conf_embed):
            return

        try:
            user = await self.bot.fetch_user(warn.member)
        except (NotFound, HTTPException):
            raise CommandError(t.user_not_found)

        user_embed = Embed(title=t.warn, description=t.warn_edited(warn.reason, reason), colour=Colors.ModTools)
        server_embed = Embed(title=t.warn, description=t.warn_edited_response, colour=Colors.ModTools)
        server_embed.set_author(name=str(user), icon_url=user.display_avatar.url)

        await Warn.edit(warn_id, ctx.author.id, await get_mod_level(ctx.author), reason)

        try:
            await user.send(embed=user_embed)
        except (Forbidden, HTTPException):
            server_embed.description = f"{t.no_dm}\n\n{server_embed.description}"
            server_embed.colour = Colors.error
        await reply(ctx, embed=server_embed)
        await send_to_changelog_mod(
            guild=ctx.guild,
            message=ctx.message,
            colour=Colors.warn,
            title=t.log_warn_edited,
            member=user,
            reason=reason,
        )

    @commands.command(aliases=["warn_delete"])
    @ModPermission.warn.check
    @guild_only()
    @docs(t.commands.delete_warn)
    async def delete_warn(self, ctx: Context, warn_id: int):
        warn = await get_and_compare_entry(Warn, warn_id, ctx.author)

        conf_embed = Embed(
            title=t.confirmation, description=t.confirm_warn_delete(warn.member_name, warn.id), color=Colors.ModTools
        )

        if not await confirm_action(ctx, conf_embed):
            return

        await Warn.delete(warn_id)

        try:
            user = await self.bot.fetch_user(warn.member)
        except (NotFound, HTTPException):
            raise CommandError(t.user_not_found)

        server_embed = Embed(title=t.warn, description=t.warn_deleted_response, colour=Colors.ModTools)
        server_embed.set_author(name=str(user), icon_url=user.display_avatar.url)

        if await ModSettings.send_delete_user_message.get():
            user_embed = Embed(title=t.warn, description=t.warn_deleted(warn.reason), colour=Colors.ModTools)

            try:
                await user.send(embed=user_embed)
            except (Forbidden, HTTPException):
                server_embed.description = f"{t.no_dm}\n\n{server_embed.description}"
                server_embed.colour = Colors.error

        await reply(ctx, embed=server_embed)
        await send_to_changelog_mod(
            guild=ctx.guild,
            message=ctx.message,
            colour=Colors.warn,
            title=t.log_warn_deleted,
            member=user,
            reason=warn.reason,
        )

    @commands.command()
    @ModPermission.mute.check
    @guild_only()
    @docs(t.commands.mute)
    async def mute(self, ctx: Context, user: UserMemberConverter, time: DurationConverter, *, reason: str):
        user: Member | User

        time: int | None
        minutes = time

        if len(reason) > 900:
            raise CommandError(t.reason_too_long)

        mute_role: Role = await get_mute_role(ctx.guild)

        if user == self.bot.user or await is_teamler(user):
            raise UserCommandError(user, t.cannot_mute)

        if isinstance(user, Member):
            await user.add_roles(mute_role)
            await user.move_to(None)

        if await db.exists(filter_by(Mute, active=True, member=user.id)):
            raise UserCommandError(user, t.already_muted)

        attachments = ctx.message.attachments
        evidence = attachments[0] if attachments else None
        evidence_url = evidence.url if attachments else None

        if not evidence:
            if not await confirm_no_evidence(ctx):
                return

        user_embed = Embed(title=t.mute, colour=Colors.ModTools)
        server_embed = Embed(title=t.mute, description=t.muted_response, colour=Colors.ModTools)
        server_embed.set_author(name=str(user), icon_url=user.display_avatar.url)

        await Mute.create(
            user.id,
            str(user),
            ctx.author.id,
            await get_mod_level(ctx.author),
            minutes if minutes is not None else -1,
            reason,
            evidence_url,
        )

        await invalidate_entry_cache()

        await send_to_changelog_mod(
            guild=ctx.guild,
            message=ctx.message,
            colour=Colors.mute,
            title=t.log_muted,
            member=user,
            reason=reason,
            duration=time_to_units(minutes) if minutes is not None else t.log_field.infinity,
            evidence=evidence,
        )

        if minutes is not None:
            user_embed.description = t.muted(ctx.author.mention, ctx.guild.name, time_to_units(minutes), reason)
        else:
            user_embed.description = t.muted_inf(ctx.author.mention, ctx.guild.name, reason)

        try:
            await user.send(embed=user_embed)
        except (Forbidden, HTTPException):
            server_embed.description = f"{t.no_dm}\n\n{server_embed.description}"
            server_embed.colour = Colors.error

        await reply(ctx, embed=server_embed)

    @commands.group(aliases=["mute_edit"])
    @ModPermission.mute.check
    @guild_only()
    @docs(t.commands.edit_mute)
    async def edit_mute(self, ctx):
        if ctx.invoked_subcommand is None:
            raise UserInputError

    @edit_mute.command(name="reason", aliases=["r"])
    @docs(t.commands.edit_mute_reason)
    async def edit_mute_reason(self, ctx: Context, mute_id: int, *, reason: str):
        mute = await get_and_compare_entry(Mute, mute_id, ctx.author)

        if len(reason) > 900:
            raise CommandError(t.reason_too_long)

        conf_embed = Embed(
            title=t.confirmation, description=t.confirm_mute_edit.reason(mute.reason, reason), color=Colors.ModTools
        )

        if not await confirm_action(ctx, conf_embed):
            return

        try:
            user = await self.bot.fetch_user(mute.member)
        except (NotFound, HTTPException):
            raise CommandError(t.user_not_found)

        user_embed = Embed(title=t.mute, description=t.mute_edited.reason(mute.reason, reason), colour=Colors.ModTools)
        server_embed = Embed(title=t.mute, description=t.mute_edited_response, colour=Colors.ModTools)
        server_embed.set_author(name=str(user), icon_url=user.display_avatar.url)

        await Mute.edit_reason(mute_id, ctx.author.id, await get_mod_level(ctx.author), reason)

        try:
            await user.send(embed=user_embed)
        except (Forbidden, HTTPException):
            server_embed.description = f"{t.no_dm}\n\n{server_embed.description}"
            server_embed.colour = Colors.error
        await reply(ctx, embed=server_embed)
        await send_to_changelog_mod(
            guild=ctx.guild,
            message=ctx.message,
            colour=Colors.mute,
            title=t.log_mute_edited,
            member=user,
            reason=reason,
        )

    @edit_mute.command(name="duration", aliases=["d"])
    @docs(t.commands.edit_mute_duration)
    async def edit_mute_duration(self, ctx: Context, user: UserMemberConverter, time: DurationConverter):
        user: Member | User
        time: int | None
        minutes = time

        active_mutes: List[Mute] = sorted(
            await db.all(filter_by(Mute, active=True, member=user.id)), key=lambda active_mute: active_mute.timestamp
        )

        if not active_mutes:
            raise CommandError(t.not_muted)

        mute = active_mutes[0]

        if not await compare_mod_level(ctx.author, mute.mod_level) or not ctx.author.id == mute.mod:
            raise CommandError(tg.permission_denied)

        if mute.minutes == minutes or (mute.minutes == -1 and minutes is None):
            raise CommandError(t.already_muted)

        conf_embed = Embed(title=t.confirmation, color=Colors.ModTools)

        old_time = t.infinity if mute.minutes == -1 else time_to_units(mute.minutes)

        if minutes is None:
            conf_embed.description = t.confirm_mute_edit.duration(old_time, t.infinity)
        else:
            conf_embed.description = t.confirm_mute_edit.duration(old_time, time_to_units(minutes))

        if not await confirm_action(ctx, conf_embed):
            return

        for active_mute in active_mutes[1:]:
            await Mute.delete(active_mute.id)

        user_embed = Embed(title=t.mute, colour=Colors.ModTools)
        server_embed = Embed(title=t.mute, description=t.mute_edited_response, colour=Colors.ModTools)
        server_embed.set_author(name=str(user), icon_url=user.display_avatar.url)

        await Mute.edit_duration(mute.id, ctx.author.id, await get_mod_level(ctx.author), minutes)

        await invalidate_entry_cache()

        user_embed.description = t.mute_edited.duration(
            time_to_units(mute.minutes), t.infinity if minutes is None else time_to_units(minutes)
        )
        await send_to_changelog_mod(
            guild=ctx.guild,
            message=ctx.message,
            colour=Colors.mute,
            title=t.log_mute_edited,
            member=user,
            reason=Mute.reason,
            duration=t.log_field.infinity if minutes is None else time_to_units(minutes),
        )

        try:
            await user.send(embed=user_embed)
        except (Forbidden, HTTPException):
            server_embed.description = f"{t.no_dm}\n\n{server_embed.description}"
            server_embed.colour = Colors.error
        await reply(ctx, embed=server_embed)

    @commands.command(aliases=["mute_delete"])
    @ModPermission.mute.check
    @guild_only()
    @docs(t.commands.delete_mute)
    async def delete_mute(self, ctx: Context, mute_id: int):
        mute = await get_and_compare_entry(Mute, mute_id, ctx.author)

        conf_embed = Embed(
            title=t.confirmation, description=t.confirm_mute_delete(mute.member_name, mute.id), color=Colors.ModTools
        )

        if not await confirm_action(ctx, conf_embed):
            return

        active_mutes: List[Mute] = await db.all(filter_by(Mute, active=True, member=mute.member))

        if len(active_mutes) == 1 and mute in active_mutes:
            user = ctx.guild.get_member(mute.member)
            if user is not None:
                if (mute_role := await get_mute_role(ctx.guild)) in user.roles:
                    await user.remove_roles(mute_role)

        try:
            user = await self.bot.fetch_user(mute.member)
        except (NotFound, HTTPException):
            raise CommandError(t.user_not_found)

        await Mute.delete(mute_id)

        await invalidate_entry_cache()

        server_embed = Embed(title=t.mute, description=t.mute_deleted_response, colour=Colors.ModTools)
        server_embed.set_author(name=str(user), icon_url=user.display_avatar.url)

        if await ModSettings.send_delete_user_message.get():
            user_embed = Embed(title=t.warn, colour=Colors.ModTools)

            if mute.minutes == -1:
                user_embed.description = t.mute_deleted.inf(mute.reason)
            else:
                user_embed.description = t.mute_deleted.not_inf(time_to_units(mute.minutes), mute.reason)

            try:
                await user.send(embed=user_embed)
            except (Forbidden, HTTPException):
                server_embed.description = f"{t.no_dm}\n\n{server_embed.description}"
                server_embed.colour = Colors.error

        await reply(ctx, embed=server_embed)

        await send_to_changelog_mod(
            guild=ctx.guild,
            message=ctx.message,
            colour=Colors.mute,
            title=t.log_mute_deleted,
            member=user,
            reason=mute.reason,
            duration=t.log_field_infinity if mute.minutes == -1 else time_to_units(mute.minutes),
        )

    @commands.command()
    @ModPermission.mute.check
    @guild_only()
    @docs(t.commands.unmute)
    async def unmute(self, ctx: Context, user: UserMemberConverter, *, reason: str):
        user: Member | User

        if len(reason) > 900:
            raise CommandError(t.reason_too_long)

        mute_role: Role = await get_mute_role(ctx.guild)

        was_muted = False
        if isinstance(user, Member) and mute_role in user.roles:
            was_muted = True
            await user.remove_roles(mute_role)

        minutes = 0
        async for mute in await db.stream(filter_by(Mute, active=True, member=user.id)):
            if not await compare_mod_level(ctx.author, mute.mod_level) or not ctx.author.id == mute.mod:
                raise CommandError(tg.permission_denied)

            await Mute.deactivate(mute.id, ctx.author.id, reason)

            was_muted = True

            if mute.minutes > minutes or mute.minutes == -1:
                minutes = mute.minutes

        if not was_muted:
            raise UserCommandError(user, t.not_muted)

        await invalidate_entry_cache()

        server_embed = Embed(title=t.unmute, description=t.unmuted_response, colour=Colors.ModTools)
        server_embed.set_author(name=str(user), icon_url=user.display_avatar.url)
        await reply(ctx, embed=server_embed)
        await send_to_changelog_mod(
            guild=ctx.guild,
            message=ctx.message,
            colour=Colors.unmute,
            title=t.log_unmuted,
            member=user,
            reason=reason,
            duration=time_to_units(minutes) if minutes is not None else t.log_field.infinity,
            mod=ctx.author,
            original_reason=mute.reason,
        )

    @commands.command()
    @ModPermission.kick.check
    @guild_only()
    @docs(t.commands.kick)
    async def kick(self, ctx: Context, member: Member, *, reason: str):
        if len(reason) > 900:
            raise CommandError(t.reason_too_long)

        if member == self.bot.user or await is_teamler(member):
            raise UserCommandError(member, t.cannot_kick)

        if not ctx.guild.me.guild_permissions.kick_members:
            raise CommandError(t.cannot_kick_permissions)

        if member.top_role >= ctx.guild.me.top_role or member.id == ctx.guild.owner_id:
            raise UserCommandError(member, t.cannot_kick)

        attachments = ctx.message.attachments
        evidence = attachments[0] if attachments else None
        evidence_url = evidence.url if attachments else None

        if not evidence:
            if not await confirm_no_evidence(ctx):
                return

        await Kick.create(member.id, str(member), ctx.author.id, await get_mod_level(ctx.author), reason, evidence_url)
        await send_to_changelog_mod(
            guild=ctx.guild,
            message=ctx.message,
            colour=Colors.kick,
            title=t.log_kicked,
            member=member,
            reason=reason,
            evidence=evidence,
        )

        user_embed = Embed(
            title=t.kick,
            colour=Colors.ModTools,
            description=t.kicked(ctx.author.mention, ctx.guild.name, reason),
        )

        server_embed = Embed(title=t.kick, description=t.kicked_response, colour=Colors.ModTools)
        server_embed.set_author(name=str(member), icon_url=member.display_avatar.url)

        try:
            await member.send(embed=user_embed)
        except (Forbidden, HTTPException):
            server_embed.description = f"{t.no_dm}\n\n{server_embed.description}"
            server_embed.colour = Colors.error

        await member.kick(reason=reason)
        await revoke_verification(member)

        await reply(ctx, embed=server_embed)

    @commands.command(aliases=["kick_edit"])
    @ModPermission.kick.check
    @guild_only()
    @docs(t.commands.edit_kick)
    async def edit_kick(self, ctx: Context, kick_id: int, *, reason: str):
        kick = await get_and_compare_entry(Kick, kick_id, ctx.author)

        if len(reason) > 900:
            raise CommandError(t.reason_too_long)

        conf_embed = Embed(
            title=t.confirmation, description=t.confirm_kick_edit(kick.reason, reason), color=Colors.ModTools
        )

        if not await confirm_action(ctx, conf_embed):
            return

        try:
            user = await self.bot.fetch_user(kick.member)
        except (NotFound, HTTPException):
            raise CommandError(t.user_not_found)

        user_embed = Embed(title=t.kick, description=t.kick_edited(kick.reason, reason), colour=Colors.ModTools)
        server_embed = Embed(title=t.kick, description=t.kick_edited_reponse, colour=Colors.ModTools)
        server_embed.set_author(name=str(user), icon_url=user.display_avatar.url)

        await Kick.edit(kick_id, ctx.author.id, await get_mod_level(ctx.author), reason)

        try:
            await user.send(embed=user_embed)
        except (Forbidden, HTTPException):
            server_embed.description = f"{t.no_dm}\n\n{server_embed.description}"
            server_embed.colour = Colors.error
        await reply(ctx, embed=server_embed)
        await send_to_changelog_mod(
            guild=ctx.guild,
            message=ctx.message,
            colour=Colors.kick,
            title=t.log_kick_edited,
            member=user,
            reason=reason,
        )

    @commands.command(aliases=["kick_delete"])
    @ModPermission.kick.check
    @guild_only()
    @docs(t.commands.delete_kick)
    async def delete_kick(self, ctx: Context, kick_id: int):
        kick = await get_and_compare_entry(Kick, kick_id, ctx.author)

        conf_embed = Embed(
            title=t.confirmation, description=t.confirm_kick_delete(kick.member_name, kick.id), color=Colors.ModTools
        )

        if not await confirm_action(ctx, conf_embed):
            return

        await Kick.delete(kick_id)

        try:
            user = await self.bot.fetch_user(kick.member)
        except (NotFound, HTTPException):
            raise CommandError(t.user_not_found)

        server_embed = Embed(title=t.warn, description=t.kick_deleted_response, colour=Colors.ModTools)
        server_embed.set_author(name=str(user), icon_url=user.display_avatar.url)

        if await ModSettings.send_delete_user_message.get():
            user_embed = Embed(title=t.kick, description=t.kick_deleted(kick.reason), colour=Colors.ModTools)

            try:
                await user.send(embed=user_embed)
            except (Forbidden, HTTPException):
                server_embed.description = f"{t.no_dm}\n\n{server_embed.description}"
                server_embed.colour = Colors.error

        await reply(ctx, embed=server_embed)
        await send_to_changelog_mod(
            guild=ctx.guild,
            message=ctx.message,
            colour=Colors.kick,
            title=t.log_kick_deleted,
            member=user,
            reason=kick.reason,
        )

    @commands.command()
    @ModPermission.ban.check
    @guild_only()
    @docs(t.commands.ban)
    async def ban(
        self, ctx: Context, user: UserMemberConverter, time: DurationConverter, delete_days: int, *, reason: str
    ):
        time: int | None
        minutes = time

        user: Member | User

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
        if active_bans:
            raise UserCommandError(user, t.already_banned)

        active_mutes: List[Mute] = await db.all(filter_by(Mute, active=True, member=user.id))
        for mute in active_mutes:
            await Mute.deactivate(mute.id, ctx.author.id, t.cancelled_by_ban)

        attachments = ctx.message.attachments
        evidence = attachments[0] if attachments else None
        evidence_url = evidence.url if attachments else None

        if not evidence:
            if not await confirm_no_evidence(ctx):
                return

        user_embed = Embed(title=t.ban, colour=Colors.ModTools)
        server_embed = Embed(title=t.ban, description=t.banned_response, colour=Colors.ModTools)
        server_embed.set_author(name=str(user), icon_url=user.display_avatar.url)

        if active_mutes:
            server_embed.description += f"\n\n{t.previously_muted}"

        await Ban.create(
            user.id,
            str(user),
            ctx.author.id,
            await get_mod_level(ctx.author),
            minutes if minutes is not None else -1,
            reason,
            evidence_url,
        )

        await invalidate_entry_cache()

        await send_to_changelog_mod(
            guild=ctx.guild,
            message=ctx.message,
            colour=Colors.ban,
            title=t.log_banned,
            member=user,
            reason=reason,
            duration=time_to_units(minutes) if minutes is not None else t.log_field.infinity,
            evidence=evidence,
        )

        if minutes is not None:
            user_embed.description = t.banned(ctx.author.mention, ctx.guild.name, time_to_units(minutes), reason)

        else:
            user_embed.description = t.banned_inf(ctx.author.mention, ctx.guild.name, reason)

        try:
            await user.send(embed=user_embed)
        except (Forbidden, HTTPException):
            server_embed.description = f"{t.no_dm}\n\n{server_embed.description}"
            server_embed.colour = Colors.error

        await ctx.guild.ban(user, reason=reason, delete_message_days=delete_days)
        await revoke_verification(user)

        await reply(ctx, embed=server_embed)

    @commands.group(aliases=["ban_edit"])
    @ModPermission.mute.check
    @guild_only()
    @docs(t.commands.edit_ban)
    async def edit_ban(self, ctx):
        if ctx.invoked_subcommand is None:
            raise UserInputError

    @edit_ban.command(name="reason", aliases=["r"])
    @docs(t.commands.edit_ban_reason)
    async def edit_ban_reason(self, ctx: Context, ban_id: int, *, reason: str):
        ban = await get_and_compare_entry(Ban, ban_id, ctx.author)

        if len(reason) > 900:
            raise CommandError(t.reason_too_long)

        conf_embed = Embed(
            title=t.confirmation, description=t.confirm_ban_edit.reason(ban.reason, reason), color=Colors.ModTools
        )

        if not await confirm_action(ctx, conf_embed):
            return

        try:
            user = await self.bot.fetch_user(ban.member)
        except (NotFound, HTTPException):
            raise CommandError(t.user_not_found)

        user_embed = Embed(title=t.ban, description=t.ban_edited.reason(ban.reason, reason), colour=Colors.ModTools)
        server_embed = Embed(title=t.ban, description=t.ban_edited_response, colour=Colors.ModTools)
        server_embed.set_author(name=str(user), icon_url=user.display_avatar.url)

        await Ban.edit_reason(ban_id, ctx.author.id, await get_mod_level(ctx.author), reason)

        try:
            await user.send(embed=user_embed)
        except (Forbidden, HTTPException):
            server_embed.description = f"{t.no_dm}\n\n{server_embed.description}"
            server_embed.colour = Colors.error
        await reply(ctx, embed=server_embed)
        await send_to_changelog_mod(
            guild=ctx.guild, message=ctx.message, colour=Colors.ban, title=t.log_ban_edited, member=user, reason=reason
        )

    @edit_ban.command(name="duration", aliases=["d"])
    @docs(t.commands.edit_ban_duration)
    async def edit_ban_duration(self, ctx: Context, user: UserMemberConverter, time: DurationConverter):
        user: Member | User
        time: int | None
        minutes = time

        active_bans: List[Ban] = sorted(
            await db.all(filter_by(Ban, active=True, member=user.id)), key=lambda active_ban: active_ban.timestamp
        )

        if not active_bans:
            raise CommandError(t.not_banned)

        ban = active_bans[0]

        if not await compare_mod_level(ctx.author, ban.mod_level) or not ctx.author.id == ban.mod:
            raise CommandError(tg.permission_denied)

        if ban.minutes == minutes or (ban.minutes == -1 and minutes is None):
            raise CommandError(t.already_banned)

        conf_embed = Embed(title=t.confirmation, color=Colors.ModTools)

        old_time = t.infinity if ban.minutes == -1 else time_to_units(ban.minutes)

        if minutes is None:
            conf_embed.description = t.confirm_ban_edit.duration(old_time, t.infinity)
        else:
            conf_embed.description = t.confirm_ban_edit.duration(old_time, time_to_units(minutes))

        if not await confirm_action(ctx, conf_embed):
            return

        for ban in active_bans[1:]:
            await Ban.delete(ban.id)

        user_embed = Embed(title=t.ban, colour=Colors.ModTools)
        server_embed = Embed(title=t.ban, description=t.ban_edited_response, colour=Colors.ModTools)
        server_embed.set_author(name=str(user), icon_url=user.display_avatar.url)

        await Ban.edit_duration(ban.id, ctx.author.id, await get_mod_level(ctx.author), minutes)

        await invalidate_entry_cache()

        user_embed.description = t.ban_edited.duration(
            time_to_units(ban.minutes), t.infinity if minutes is None else time_to_units(minutes)
        )
        await send_to_changelog_mod(
            guild=ctx.guild,
            message=ctx.message,
            colour=Colors.ban,
            title=t.log_ban_edited,
            member=user,
            reason=ban.reason,
            duration=t.log_field.infinity if minutes is None else time_to_units(minutes),
        )

        try:
            await user.send(embed=user_embed)
        except (Forbidden, HTTPException):
            server_embed.description = f"{t.no_dm}\n\n{server_embed.description}"
            server_embed.colour = Colors.error
        await reply(ctx, embed=server_embed)

    @commands.command(aliases=["ban_delete"])
    @ModPermission.ban.check
    @guild_only()
    @docs(t.commands.delete_ban)
    async def delete_ban(self, ctx: Context, ban_id: int):
        ban = await get_and_compare_entry(Ban, ban_id, ctx.author)

        conf_embed = Embed(
            title=t.confirmation, description=t.confirm_ban_delete(ban.member_name, ban.id), color=Colors.ModTools
        )

        if not await confirm_action(ctx, conf_embed):
            return

        active_bans: List[Ban] = await db.all(filter_by(Ban, active=True, member=ban.member))

        if len(active_bans) == 1 and ban in active_bans:
            user = ctx.guild.get_member(ban.member)
            if user is not None:
                try:
                    await ctx.guild.unban(user, reason="Ban deleted")
                except HTTPException:
                    pass

        try:
            user = await self.bot.fetch_user(ban.member)
        except (NotFound, HTTPException):
            raise CommandError(t.user_not_found)

        await Ban.delete(ban_id)

        await invalidate_entry_cache()

        server_embed = Embed(title=t.mute, description=t.ban_deleted_response, colour=Colors.ModTools)

        server_embed.set_author(name=str(user), icon_url=user.display_avatar.url)

        if await ModSettings.send_delete_user_message.get():
            user_embed = Embed(title=t.ban, colour=Colors.ModTools)

            if ban.minutes == -1:
                user_embed.description = t.ban_deleted.inf(ban.reason)
            else:
                user_embed.description = t.ban_deleted.not_inf(time_to_units(ban.minutes), ban.reason)

            try:
                await user.send(embed=user_embed)
            except (Forbidden, HTTPException):
                server_embed.description = f"{t.no_dm}\n\n{server_embed.description}"
                server_embed.colour = Colors.error

        await reply(ctx, embed=server_embed)

        await send_to_changelog_mod(
            guild=ctx.guild,
            message=ctx.message,
            colour=Colors.ban,
            title=t.log_ban_deleted,
            member=user,
            reason=ban.reason,
            duration=t.log_field_infinity if ban.minutes == -1 else time_to_units(ban.minutes),
        )

    @commands.command()
    @ModPermission.ban.check
    @guild_only()
    @docs(t.commands.unban)
    async def unban(self, ctx: Context, user: UserMemberConverter, *, reason: str):
        user: Member | User

        if len(reason) > 900:
            raise CommandError(t.reason_too_long)

        if not ctx.guild.me.guild_permissions.ban_members:
            raise CommandError(t.cannot_unban_permissions)

        was_banned = True
        try:
            await ctx.guild.unban(user, reason=reason)
        except HTTPException:
            was_banned = False

        minutes = 0
        async for ban in await db.stream(filter_by(Ban, active=True, member=user.id)):
            if not await compare_mod_level(ctx.author, ban.mod_level) or not ctx.author.id == ban.mod:
                raise CommandError(tg.permission_denied)

            await Ban.deactivate(ban.id, ctx.author.id, reason)

            was_banned = True

            if ban.minutes > minutes or ban.minutes == -1:
                minutes = ban.minutes

        if not was_banned:
            raise UserCommandError(user, t.not_banned)

        await invalidate_entry_cache()

        server_embed = Embed(title=t.unban, description=t.unbanned_response, colour=Colors.ModTools)
        server_embed.set_author(name=str(user), icon_url=user.display_avatar.url)
        await reply(ctx, embed=server_embed)
        await send_to_changelog_mod(
            guild=ctx.guild,
            message=ctx.message,
            colour=Colors.unban,
            title=t.log_unbanned,
            member=user,
            reason=reason,
            duration=time_to_units(minutes) if minutes is not None else t.log_field.infinity,
            mod=ctx.author,
            original_reason=ban.reason,
        )
