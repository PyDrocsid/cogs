import re
from asyncio import sleep
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable, Tuple, Type, TypeVar

from dateutil.relativedelta import relativedelta
from discord import (
    Attachment,
    AuditLogAction,
    AuditLogEntry,
    Embed,
    Forbidden,
    Guild,
    HTTPException,
    Member,
    Message,
    NotFound,
    Role,
    TextChannel,
    Thread,
    User,
)
from discord.ext import commands, tasks
from discord.ext.commands import BadArgument, CommandError, Context, Converter, UserInputError, guild_only
from discord.utils import utcnow

from PyDrocsid.cog import Cog
from PyDrocsid.command import Confirmation, UserCommandError, docs, reply
from PyDrocsid.converter import UserMemberConverter
from PyDrocsid.database import Base as DBBase
from PyDrocsid.database import db, db_wrapper, filter_by
from PyDrocsid.environment import CACHE_TTL
from PyDrocsid.redis import redis
from PyDrocsid.settings import RoleSettings
from PyDrocsid.translations import t
from PyDrocsid.util import check_role_assignable, is_teamler

from .colors import Colors
from .models import Ban, Kick, Mute, Report, Warn
from .permissions import ModPermission
from .settings import ModSettings
from ...contributor import Contributor
from ...pubsub import (
    get_user_info_entries,
    get_user_status_entries,
    get_userlog_entries,
    log_auto_kick,
    revoke_verification,
    send_alert,
    send_to_changelog,
)


tg = t.g
t = t.mod
TBase = TypeVar("TBase", bound=DBBase)
MAX_TIMEOUT = timedelta(days=28)


# TODO
#  Docstring for all methods, functions and classes
#  make all functions private, if the are not ment to be used by other
#  use timeout function for mutes (see actual mod tools)
#  do not require mute role, update whole code accordingly
#  assign mute role to all muted members, when mute role gets set
#  remove mute role from all muted members if mute role gets cleared
#  to be continued......


class DurationConverter(Converter):  # TODO: Move to library
    """
    Converter for retrieving simple time spans from a string containing different time units
    """

    async def convert(self, ctx, argument: str) -> int | None:
        if argument.lower() in ("inf", "perm", "permanent", "-1", "∞"):
            return None
        if (match := re.match(r"^(\d+y)?(\d+m)?(\d+w)?(\d+d)?(\d+H)?(\d+M)?$", argument)) is None:
            raise BadArgument(t.duration_suffixes)

        years, months, weeks, days, hours, minutes = [
            0 if (value := match.group(i)) is None else int(value[:-1]) for i in range(1, 5)
        ]

        years += days * 365
        days += months * 30
        days += weeks * 7
        td = timedelta(days=days, hours=hours, minutes=minutes)
        duration = int(td.total_seconds() / 60)

        if duration <= 0:
            raise BadArgument(tg.invalid_duration)
        if duration >= (1 << 31):
            raise BadArgument(t.invalid_duration_inf)
        return duration


async def load_entries():
    """
    Loads active mute and ban entries from the database and caches them in Redis.
    Bans and timed mutes are stored in hashes, while infinite mutes are stored in a list
    """

    async def fill(db_model: Type[TBase]):
        async with redis.pipeline() as pipe:
            await pipe.delete(entry_key := f"mod_entries:{db_model.__tablename__}")

            async for entry in await db.stream(filter_by(db_model, active=True)):
                if entry.minutes == -1:
                    new_key = f"{entry_key}_inf"
                    await pipe.rpush(new_key, str(entry.id))
                    continue

                expiration_timestamp = entry.timestamp + timedelta(minutes=entry.minutes)

                await pipe.hset(entry_key, str(entry.id), str(expiration_timestamp))

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
    """
    Util function to split minutes back into different time units
    """
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
    if not mute_role:
        await send_alert(guild, t.mute.role_not_set)
    return mute_role


def extract_evidence(message: Message) -> Tuple[Attachment | None, str | None]:
    """
    Extracts possible evidence attachments from a message
    """
    attachments = message.attachments
    evidence = attachments[0] if attachments else None
    evidence_url = evidence.url if attachments else None

    return evidence, evidence_url


def show_evidence(evidence: str | None) -> str:
    """
    Util function to display evidences correctly
    """
    return t.ulog.evidence(evidence) if evidence else ""


async def get_database_entry(entry_format: Type[TBase], entry_id: int) -> TBase:
    """
    Loads an entry with a given id from the database
    """
    entry = await db.get(entry_format, id=entry_id)
    if entry is None:
        raise CommandError(getattr(t.not_found, entry_format.__tablename__))

    return entry


async def confirm_no_evidence(ctx: Context):
    """
    Function that lets the user confirm that he does not want to attach an evidence
    """
    conf_embed = Embed(title=t.confirmation, description=t.no_evidence, color=Colors.ModTools)

    return await Confirmation().run(ctx, embed=conf_embed)


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
    """
    Function that sends logging messages to the moderation log channel
    """
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
        embed.add_field(name=t.log_field.original_reason, value=original_reason, inline=True)

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
                        await Ban.create(entry.target.id, str(entry.target), entry.user.id, -1, entry.reason, None)

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

            await sleep((i * 10) / 100)
            search_limit = int(search_limit / 2)

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
                    break

                await Ban.deactivate(ban.id)

                await redis.hdel(ban_entries_key, key)

                await send_to_changelog_mod(
                    guild=guild,
                    message=None,
                    colour=Colors.unban,
                    title=t.ban.log_undo,
                    member=user,
                    reason=t.ban.log_undo_expired,
                )

        mute_role: Role | None = guild.get_role(await RoleSettings.get("mute"))
        if mute_role is None:
            return

        try:
            check_role_assignable(mute_role)  # TODO move into get_mute_role
        except CommandError:
            await send_alert(guild, t.cannot_assign_mute_role(mute_role, mute_role.id))
            return

        mute_keys = await redis.hkeys(mute_entries_key := f"mod_entries:{Mute.__tablename__}")

        for key in mute_keys:
            if utcnow() >= datetime.fromisoformat(await redis.hget(mute_entries_key, key)):
                mute = await db.get(Mute, id=int(key))

                member = guild.get_member(mute.member)
                timeout: datetime | None = member.communication_disabled_until

                if member:
                    await member.remove_roles(mute_role)
                    await member.remove_timeout()
                else:
                    member = mute.member, mute.member_name

                await send_to_changelog_mod(
                    guild=guild,
                    message=None,
                    colour=Colors.unmute,
                    title=t.mute.log_undo,
                    member=member,
                    reason=t.mute.log_undo_expired,
                )

                await Mute.deactivate(mute.id)

                await redis.hdel(mute_entries_key, key)

        for infinite_mute in await redis.lrange(
            inf_mute_key := f"mod_entries:{Mute.__tablename__}_inf", 0, await redis.llen(inf_mute_key) - 1
        ):
            mute = await db.get(Mute, id=int(infinite_mute))

            member = guild.get_member(mute.member)
            timeout: datetime | None = member.communication_disabled_until

            if member and infinite_mute.days == -1:
                await member.timeout_for(MAX_TIMEOUT)
            elif member and (
                not timeout
                or timeout + timedelta(seconds=2) < infinite_mute.timestamp + timedelta(days=infinite_mute.days)
            ):
                delta = min(infinite_mute.timestamp + timedelta(days=infinite_mute.days) - utcnow(), MAX_TIMEOUT)
                await member.timeout_for(delta)

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
            translation, mod: int, reason: str, evidence: str, minutes: int | None = None, entry_id: int | None = None
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

    async def handle_single(
        self, ctx: Context, user: User | Member, reason: str, translation: Any, model: Type[TBase], color: int
    ) -> bool:
        user: Member | User

        if len(reason) > 900:
            raise CommandError(t.reason_too_long)

        if user == self.bot.user:
            raise UserCommandError(user, translation.cannot)

        evidence, evidence_url = extract_evidence(ctx.message)

        if not evidence:
            if not await confirm_no_evidence(ctx):
                return False

        user_embed = Embed(
            title=translation.action,
            colour=Colors.ModTools,
            description=translation.done(ctx.author.mention, ctx.guild.name, reason),
        )

        server_embed = Embed(title=translation.action, description=translation.response, colour=Colors.ModTools)
        server_embed.set_author(name=str(user), icon_url=user.display_avatar.url)
        try:
            await user.send(embed=user_embed)
        except (Forbidden, HTTPException):
            server_embed.description = f"{t.no_dm}\n\n{server_embed.description}"
            server_embed.colour = Colors.error
        await model.create(user.id, str(user), ctx.author.id, reason, evidence_url)
        await reply(ctx, embed=server_embed)
        await send_to_changelog_mod(
            guild=ctx.guild,
            message=ctx.message,
            colour=color,
            title=translation.log,
            member=user,
            reason=reason,
            evidence=evidence,
        )

        return True

    async def handle_edit_single(
        self, ctx: Context, entry_id: int, reason: str, translation: Any, model: Type[TBase], color: int
    ):
        entry = await get_database_entry(model, entry_id)

        if len(reason) > 900:
            raise CommandError(t.reason_too_long)

        conf_embed = Embed(
            title=t.confirmation, description=translation.confirm_edit(entry.reason, reason), color=Colors.ModTools
        )

        if not await Confirmation().run(ctx, embed=conf_embed):
            return

        try:
            user = await self.bot.fetch_user(entry.member)
        except (NotFound, HTTPException):
            raise CommandError(t.user_not_found)

        user_embed = Embed(
            title=translation.action, description=translation.edited(entry.reason, reason), colour=Colors.ModTools
        )
        server_embed = Embed(title=translation.action, description=translation.edited_response, colour=Colors.ModTools)
        server_embed.set_author(name=str(user), icon_url=user.display_avatar.url)

        await model.edit(entry_id, ctx.author.id, reason)

        try:
            await user.send(embed=user_embed)
        except (Forbidden, HTTPException):
            server_embed.description = f"{t.no_dm}\n\n{server_embed.description}"
            server_embed.colour = Colors.error
        await reply(ctx, embed=server_embed)
        await send_to_changelog_mod(
            guild=ctx.guild, message=ctx.message, colour=color, title=translation.log_edited, member=user, reason=reason
        )

    async def handle_delete_single(self, ctx: Context, entry_id: int, translation, model: Type[TBase], color: int):
        entry = await get_database_entry(model, entry_id)

        conf_embed = Embed(
            title=t.confirmation,
            description=translation.confirm_delete(entry.member_name, entry.id),
            color=Colors.ModTools,
        )

        if not await Confirmation().run(ctx, embed=conf_embed):
            return

        await model.delete(entry_id)

        try:
            user = await self.bot.fetch_user(entry.member)
        except (NotFound, HTTPException):
            raise CommandError(t.user_not_found)

        server_embed = Embed(title=translation.action, description=translation.deleted_response, colour=Colors.ModTools)
        server_embed.set_author(name=str(user), icon_url=user.display_avatar.url)

        if await ModSettings.send_delete_user_message.get():
            user_embed = Embed(
                title=translation.action, description=translation.deleted(entry.reason), colour=Colors.ModTools
            )

            try:
                await user.send(embed=user_embed)
            except (Forbidden, HTTPException):
                server_embed.description = f"{t.no_dm}\n\n{server_embed.description}"
                server_embed.colour = Colors.error

        await reply(ctx, embed=server_embed)
        await send_to_changelog_mod(
            guild=ctx.guild,
            message=ctx.message,
            colour=color,
            title=translation.log_deleted,
            member=user,
            reason=entry.reason,
        )

    async def handle_timed(
        self,
        ctx: Context,
        user: Member | User,
        time: int | None,
        reason: str,
        translation,
        model: Type[TBase],
        color: int,
        embed_addition: str,
    ) -> bool:
        time: int | None
        minutes = time

        if len(reason) > 900:
            raise CommandError(t.reason_too_long)

        if await db.exists(filter_by(model, active=True, member=user.id)):
            raise UserCommandError(user, translation.already_done)

        evidence, evidence_url = extract_evidence(ctx.message)

        if not evidence:
            if not await confirm_no_evidence(ctx):
                return False

        user_embed = Embed(title=translation.action, colour=Colors.ModTools)
        server_embed = Embed(title=translation.action, description=translation.response, colour=Colors.ModTools)
        server_embed.set_author(name=str(user), icon_url=user.display_avatar.url)

        await model.create(
            user.id, str(user), ctx.author.id, minutes if minutes is not None else -1, reason, evidence_url
        )

        await invalidate_entry_cache()

        await send_to_changelog_mod(
            guild=ctx.guild,
            message=ctx.message,
            colour=color,
            title=translation.log,
            member=user,
            reason=reason,
            duration=time_to_units(minutes) if minutes is not None else t.log_field.infinity,
            evidence=evidence,
        )

        if minutes is not None:
            user_embed.description = translation.done(
                ctx.author.mention, ctx.guild.name, time_to_units(minutes), reason
            )
        else:
            user_embed.description = translation.done_inf(ctx.author.mention, ctx.guild.name, reason)

        server_embed.description = f"{server_embed.description}{embed_addition}"

        try:
            await user.send(embed=user_embed)
        except (Forbidden, HTTPException):
            server_embed.description = f"{t.no_dm}\n\n{server_embed.description}"
            server_embed.colour = Colors.error

        await reply(ctx, embed=server_embed)

        return True

    async def handle_edit_timed_reason(
        self, ctx: Context, entry_id: int, reason: str, translation: Any, model: Type[TBase], color: int
    ):
        entry = await get_database_entry(model, entry_id)

        if len(reason) > 900:
            raise CommandError(t.reason_too_long)

        conf_embed = Embed(
            title=t.confirmation,
            description=translation.confirm_edit.reason(entry.reason, reason),
            color=Colors.ModTools,
        )

        if not await Confirmation().run(ctx, embed=conf_embed):
            return

        try:
            user = await self.bot.fetch_user(entry.member)
        except (NotFound, HTTPException):
            raise CommandError(t.user_not_found)

        user_embed = Embed(
            title=translation.action,
            description=translation.edited.reason(entry.reason, reason),
            colour=Colors.ModTools,
        )
        server_embed = Embed(title=translation.action, description=translation.edited_response, colour=Colors.ModTools)
        server_embed.set_author(name=str(user), icon_url=user.display_avatar.url)

        await model.edit_reason(entry_id, ctx.author.id, reason)

        try:
            await user.send(embed=user_embed)
        except (Forbidden, HTTPException):
            server_embed.description = f"{t.no_dm}\n\n{server_embed.description}"
            server_embed.colour = Colors.error
        await reply(ctx, embed=server_embed)
        await send_to_changelog_mod(
            guild=ctx.guild, message=ctx.message, colour=color, title=translation.log_edited, member=user, reason=reason
        )

    async def handle_edit_timed_duration(
        self, ctx: Context, user: User | Member, time: int | None, translation: Any, model: Type[TBase], color: int
    ):
        user: Member | User
        time: int | None
        minutes = time

        active_entries: list[TBase] = sorted(
            await db.all(filter_by(model, active=True, member=user.id)), key=lambda active_entry: active_entry.timestamp
        )

        if not active_entries:
            raise CommandError(translation.not_done)

        entry = active_entries[0]

        if entry.minutes == minutes or (entry.minutes == -1 and minutes is None):
            raise CommandError(translation.already_done)

        conf_embed = Embed(title=t.confirmation, color=Colors.ModTools)

        old_time = t.infinity if entry.minutes == -1 else time_to_units(entry.minutes)

        if minutes is None:
            conf_embed.description = translation.confirm_edit.duration(old_time, t.infinity)
        else:
            conf_embed.description = translation.confirm_edit.duration(old_time, time_to_units(minutes))

        if not await Confirmation().run(ctx, embed=conf_embed):
            return

        for active_entry in active_entries[1:]:
            await model.delete(active_entry.id)

        user_embed = Embed(title=translation.action, colour=Colors.ModTools)
        server_embed = Embed(title=translation.action, description=translation.edited_response, colour=Colors.ModTools)
        server_embed.set_author(name=str(user), icon_url=user.display_avatar.url)

        await model.edit_duration(entry.id, ctx.author.id, minutes)

        await invalidate_entry_cache()

        user_embed.description = translation.edited.duration(
            time_to_units(entry.minutes), t.infinity if minutes is None else time_to_units(minutes)
        )
        await send_to_changelog_mod(
            guild=ctx.guild,
            message=ctx.message,
            colour=color,
            title=translation.log_edited,
            member=user,
            reason=entry.reason,
            duration=t.log_field.infinity if minutes is None else time_to_units(minutes),
        )

        try:
            await user.send(embed=user_embed)
        except (Forbidden, HTTPException):
            server_embed.description = f"{t.no_dm}\n\n{server_embed.description}"
            server_embed.colour = Colors.error
        await reply(ctx, embed=server_embed)

    async def handle_delete_timed(
        self, ctx: Context, entry_id: int, translation: Any, model: Type[TBase], color: int
    ) -> TBase | None:
        entry = await get_database_entry(model, entry_id)

        conf_embed = Embed(
            title=t.confirmation,
            description=translation.confirm_delete(entry.member_name, entry.id),
            color=Colors.ModTools,
        )

        if not await Confirmation().run(ctx, embed=conf_embed):
            return

        try:
            user = await self.bot.fetch_user(entry.member)
        except (NotFound, HTTPException):
            raise CommandError(t.user_not_found)

        await model.delete(entry_id)

        await invalidate_entry_cache()

        server_embed = Embed(title=translation.action, description=translation.deleted_response, colour=Colors.ModTools)
        server_embed.set_author(name=str(user), icon_url=user.display_avatar.url)

        if await ModSettings.send_delete_user_message.get():
            user_embed = Embed(title=translation.action, colour=Colors.ModTools)

            if entry.minutes == -1:
                user_embed.description = translation.deleted.inf(entry.reason)
            else:
                user_embed.description = translation.deleted.not_inf(time_to_units(entry.minutes), entry.reason)

            try:
                await user.send(embed=user_embed)
            except (Forbidden, HTTPException):
                server_embed.description = f"{t.no_dm}\n\n{server_embed.description}"
                server_embed.colour = Colors.error

        await reply(ctx, embed=server_embed)

        await send_to_changelog_mod(
            guild=ctx.guild,
            message=ctx.message,
            colour=color,
            title=translation.log_deleted,
            member=user,
            reason=entry.reason,
            duration=t.log_field_infinity if entry.minutes == -1 else time_to_units(entry.minutes),
        )

        return entry

    async def handle_undo_timed(
        self,
        ctx: Context,
        user: User | Member,
        reason: str,
        translation: Any,
        model: Type[TBase],
        color: int,
        undo_function: Callable[[Context, Member | User], Awaitable[bool]],
    ):
        user: Member | User

        if len(reason) > 900:
            raise CommandError(t.reason_too_long)

        was_done = await undo_function(ctx, user)

        minutes = 0
        async for entry in await db.stream(filter_by(model, active=True, member=user.id)):
            await model.deactivate(entry.id, ctx.author.id, reason)

            was_done = True

            if entry.minutes > minutes or entry.minutes == -1:
                minutes = entry.minutes

        if not was_done:
            raise UserCommandError(user, translation.not_done)

        await invalidate_entry_cache()

        server_embed = Embed(title=translation.undo, description=translation.undo_response, colour=Colors.ModTools)
        server_embed.set_author(name=str(user), icon_url=user.display_avatar.url)
        await reply(ctx, embed=server_embed)

        await send_to_changelog_mod(
            guild=ctx.guild,
            message=ctx.message,
            colour=color,
            title=translation.log_undo,
            member=user,
            reason=reason,
            duration=time_to_units(minutes) if minutes is not None else t.log_field.infinity,
            mod=ctx.author,
            original_reason=entry.reason,
        )

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

        if not await Confirmation().run(ctx, embed=conf_embed):
            return

        evidence, evidence_url = extract_evidence(ctx.message)

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
        user: User | Member

        await self.handle_single(ctx, user, reason, t.warn, Warn, Colors.warn)

    @commands.command(aliases=["warn_edit"])
    @ModPermission.warn.check
    @guild_only()
    @docs(t.commands.edit_warn)
    async def edit_warn(self, ctx: Context, warn_id: int, *, reason: str):
        await self.handle_edit_single(ctx, warn_id, reason, t.warn, Warn, Colors.warn)

    @commands.command(aliases=["warn_delete"])
    @ModPermission.warn.check
    @guild_only()
    @docs(t.commands.delete_warn)
    async def delete_warn(self, ctx: Context, warn_id: int):
        await self.handle_delete_single(ctx, warn_id, t.warn, Warn, Colors.warn)

    @commands.command()
    @ModPermission.mute.check
    @guild_only()
    @docs(t.commands.mute)
    async def mute(self, ctx: Context, user: UserMemberConverter, time: DurationConverter, *, reason: str):
        user: Member | User
        time: int | None

        if user == self.bot.user or await is_teamler(user):
            raise UserCommandError(user, t.mute.cannot)

        mute_role: Role | None = await get_mute_role(ctx.guild)

        if mute_role is None:
            raise CommandError(t.mute.role_not_set)

        if not await self.handle_timed(ctx, user, time, reason, t.mute, Mute, Colors.mute, ""):
            return

        if isinstance(user, Member):
            await user.add_roles(mute_role)

            try:
                await user.timeout_for(min(timedelta(minutes=time), MAX_TIMEOUT) if time else MAX_TIMEOUT)
            except Forbidden:
                raise CommandError(t.mute.cannot)

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
        await self.handle_edit_timed_reason(ctx, mute_id, reason, t.mute, Mute, Colors.mute)

    @edit_mute.command(name="duration", aliases=["d"])
    @docs(t.commands.edit_mute_duration)
    async def edit_mute_duration(self, ctx: Context, user: UserMemberConverter, time: DurationConverter):
        user: User | Member
        time: int | None

        await self.handle_edit_timed_duration(ctx, user, time, t.mute, Mute, Colors.mute)

    @commands.command(aliases=["mute_delete"])
    @ModPermission.mute.check
    @guild_only()
    @docs(t.commands.delete_mute)
    async def delete_mute(self, ctx: Context, mute_id: int):
        if not (mute := await self.handle_delete_timed(ctx, mute_id, t.mute, Mute, Colors.mute)):
            return

        active_mutes: list[Mute] = await db.all(filter_by(Mute, active=True, member=mute.member))

        if len(active_mutes) == 1 and mute in active_mutes:
            user = ctx.guild.get_member(mute.member)
            if user is not None:
                if (mute_role := await get_mute_role(ctx.guild)) in user.roles:
                    await user.remove_roles(mute_role)

    @commands.command()
    @ModPermission.mute.check
    @guild_only()
    @docs(t.commands.unmute)
    async def unmute(self, ctx: Context, user: UserMemberConverter, *, reason: str):
        user: User | Member

        async def unmute_inner(context: Context, muted_user: Member | User) -> bool:
            mute_role: Role | None = await get_mute_role(context.guild)

            was_muted = False
            if isinstance(muted_user, Member) and mute_role in muted_user.roles:
                was_muted = True
                if mute_role is not None:
                    await muted_user.remove_roles(mute_role)

                try:
                    await user.remove_timeout()
                except Forbidden:
                    raise CommandError(t.mute.cannot_undo)

            return was_muted

        await self.handle_undo_timed(ctx, user, reason, t.mute, Mute, Colors.unmute, unmute_inner)

    @commands.command()
    @ModPermission.kick.check
    @guild_only()
    @docs(t.commands.kick)
    async def kick(self, ctx: Context, member: Member, *, reason: str):
        if member == self.bot.user or await is_teamler(member):
            raise UserCommandError(member, t.cannot_kick)

        if not ctx.guild.me.guild_permissions.kick_members:
            raise CommandError(t.cannot_kick_permissions)

        if member.top_role >= ctx.guild.me.top_role or member.id == ctx.guild.owner_id:
            raise UserCommandError(member, t.cannot_kick)

        if not self.handle_single(ctx, member, reason, t.kick, Kick, Colors.kick):
            return

        await member.kick(reason=reason)
        await revoke_verification(member)

    @commands.command(aliases=["kick_edit"])
    @ModPermission.kick.check
    @guild_only()
    @docs(t.commands.edit_kick)
    async def edit_kick(self, ctx: Context, kick_id: int, *, reason: str):
        await self.handle_edit_single(ctx, kick_id, reason, t.kick, Kick, Colors.kick)

    @commands.command(aliases=["kick_delete"])
    @ModPermission.kick.check
    @guild_only()
    @docs(t.commands.delete_kick)
    async def delete_kick(self, ctx: Context, kick_id: int):
        await self.handle_delete_single(ctx, kick_id, t.kick, Kick, Colors.kick)

    @commands.command()
    @ModPermission.ban.check
    @guild_only()
    @docs(t.commands.ban)
    async def ban(
        self, ctx: Context, user: UserMemberConverter, time: DurationConverter, delete_days: int, *, reason: str
    ):
        user: Member | User
        time: int | None

        if not ctx.guild.me.guild_permissions.ban_members:
            raise CommandError(t.cannot_ban_permissions)

        if not 0 <= delete_days <= 7:
            raise CommandError(tg.invalid_duration)

        if isinstance(user, Member) and (user.top_role >= ctx.guild.me.top_role or user.id == ctx.guild.owner_id):
            raise UserCommandError(user, t.cannot_ban)

        active_mutes: list[Mute] = await db.all(filter_by(Mute, active=True, member=user.id))

        if not await self.handle_timed(
            ctx, user, time, reason, t.ban, Ban, Colors.ban, f"\n\n{t.ban.previously_muted}" if active_mutes else ""
        ):
            return

        for mute in active_mutes:
            await Mute.deactivate(mute.id, ctx.author.id, t.cancelled_by_ban)

        await ctx.guild.ban(user, reason=reason, delete_message_days=delete_days)
        await revoke_verification(user)

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
        await self.handle_edit_timed_reason(ctx, ban_id, reason, t.ban, Ban, Colors.ban)

    @edit_ban.command(name="duration", aliases=["d"])
    @docs(t.commands.edit_ban_duration)
    async def edit_ban_duration(self, ctx: Context, user: UserMemberConverter, time: DurationConverter):
        user: User | Member
        time: int | None

        await self.handle_edit_timed_duration(ctx, user, time, t.ban, Ban, Colors.ban)

    @commands.command(aliases=["ban_delete"])
    @ModPermission.ban.check
    @guild_only()
    @docs(t.commands.delete_ban)
    async def delete_ban(self, ctx: Context, ban_id: int):
        if not (ban := await self.handle_delete_timed(ctx, ban_id, t.ban, Ban, Colors.ban)):
            return

        active_bans: list[Ban] = await db.all(filter_by(Ban, active=True, member=ban.member))

        if len(active_bans) == 1 and ban in active_bans:
            user = ctx.guild.get_member(ban.member)
            if user is not None:
                try:
                    await ctx.guild.unban(user, reason="Ban deleted")
                except HTTPException:
                    pass

    @commands.command()
    @ModPermission.ban.check
    @guild_only()
    @docs(t.commands.unban)
    async def unban(self, ctx: Context, user: UserMemberConverter, *, reason: str):
        user: User | Member

        if not ctx.guild.me.guild_permissions.ban_members:
            raise CommandError(t.cannot_unban_permissions)

        async def unban_inner(context: Context, banned_user: Member | User) -> bool:
            was_banned = True
            try:
                await ctx.guild.unban(banned_user, reason=reason)
            except HTTPException:
                was_banned = False

            return was_banned

        await self.handle_undo_timed(ctx, user, reason, t.ban, Ban, Colors.unban, unban_inner)
