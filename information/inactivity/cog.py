import asyncio
from datetime import datetime, timedelta
from typing import Optional

from discord import Message, Guild, Member, Embed, Role, Permissions, NotFound, TextChannel, Status
from discord.ext import commands
from discord.ext.commands import guild_only, Context, CommandError, max_concurrency

from PyDrocsid.async_thread import semaphore_gather, run_as_task
from PyDrocsid.cog import Cog
from PyDrocsid.command import reply, optional_permissions
from PyDrocsid.config import Contributor
from PyDrocsid.database import db, db_wrapper
from PyDrocsid.embeds import send_long_embed
from PyDrocsid.translations import t
from .models import Activity
from .permissions import InactivityPermission
from .settings import InactivitySettings
from ...pubsub import ignore_message_edit, send_to_changelog, get_user_status_entries

tg = t.g
t = t.inactivity


def status_icon(status: Status) -> str:
    return {
        Status.online: ":green_circle:",
        Status.idle: ":yellow_circle:",
        Status.dnd: ":red_circle:",
        Status.offline: ":black_circle:",
    }[status]


@run_as_task
async def scan(ctx: Context, days: int):
    async def update_msg(m: Message, content):
        embed.description = content
        embed.timestamp = datetime.utcnow()
        await ignore_message_edit(m)
        try:
            await m.edit(embed=embed)
        except NotFound:
            return await reply(ctx, embed=embed)
        return m

    embed = Embed(title=t.scanning, timestamp=datetime.utcnow())
    message: list[Message] = [await reply(ctx, embed=embed)]
    guild: Guild = ctx.guild
    members: dict[Member, datetime] = {}
    active: dict[TextChannel, int] = {}
    completed: list[TextChannel] = []

    async def update_progress_message():
        while len(completed) < len(channels):
            content = t.scanning_channel(len(completed), len(channels), cnt=len(active))
            for a, d in active.items():
                channel_age = (datetime.utcnow() - a.created_at).days
                content += f"\n:small_orange_diamond: {a.mention} ({d} / {min(channel_age, days)})"
            message[0] = await update_msg(message[0], content)
            await asyncio.sleep(2)

    async def update_members(c: TextChannel):
        active[c] = 0

        async for msg in c.history(limit=None, oldest_first=False):
            s = (datetime.utcnow() - msg.created_at).total_seconds()
            if s > days * 24 * 60 * 60:
                break
            members[msg.author] = max(members.get(msg.author, msg.created_at), msg.created_at)
            active[c] = int(s / (24 * 60 * 60))

        del active[c]
        completed.append(c)

    channels: list[TextChannel] = []
    for channel in guild.text_channels:
        permissions: Permissions = channel.permissions_for(ctx.me)
        if permissions.read_messages and permissions.read_message_history:
            channels.append(channel)

    task = asyncio.create_task(update_progress_message())
    try:
        await semaphore_gather(10, *map(update_members, channels))
    finally:
        task.cancel()

    await update_msg(message[0], t.scan_complete(cnt=len(guild.text_channels)))

    embed = Embed(title=t.updating_members)
    message: Message = await reply(ctx, embed=embed)

    await semaphore_gather(50, *[Activity.update(m.id, ts) for m, ts in members.items()])

    await update_msg(message, t.updated_members(cnt=len(members)))


class InactivityCog(Cog, name="Inactivity"):
    CONTRIBUTORS = [Contributor.Defelo]

    async def on_message(self, message: Message):
        if message.guild is None:
            return

        await Activity.update(message.author.id, message.created_at)

        role: Role
        for role in message.role_mentions:
            await Activity.update(role.id, message.created_at)

    @commands.command()
    @InactivityPermission.scan.check
    @max_concurrency(1)
    @guild_only()
    async def scan(self, ctx: Context, days: int):
        """
        scan all channels for latest message of each user
        """

        if days <= 0:
            raise CommandError(tg.invalid_duration)

        await scan(ctx, days)

    @get_user_status_entries.subscribe
    async def handle_get_user_status_entries(self, user_id) -> list[tuple[str, str]]:
        inactive_days = await InactivitySettings.inactive_days.get()

        activity: Optional[Activity] = await db.get(Activity, id=user_id)

        if activity is None:
            status = t.status.inactive
        elif (days := (datetime.utcnow() - activity.timestamp).days) >= inactive_days:
            status = t.status.inactive_since(activity.timestamp.strftime("%d.%m.%Y %H:%M:%S"))
        else:
            status = t.status.active(cnt=days)

        return [(t.activity, status)]

    @commands.command(aliases=["in"])
    @InactivityPermission.read.check
    @guild_only()
    async def inactive(self, ctx: Context, days: Optional[int], *roles: Optional[Role]):
        """
        list inactive users
        """

        if role := ctx.guild.get_role(days):
            roles += (role,)
            days = None

        if days is None:
            days = await InactivitySettings.inactive_days.get()
        elif days not in range(1, 10001):
            raise CommandError(tg.invalid_duration)

        now = datetime.utcnow()

        @db_wrapper
        async def load_member(m: Member) -> tuple[Member, Optional[datetime]]:
            ts = await db.get(Activity, id=m.id)
            return m, ts.timestamp if ts else None

        if roles:
            members: set[Member] = {member for role in roles for member in role.members}
        else:
            members: set[Member] = set(ctx.guild.members)

        last_activity: list[tuple[Member, Optional[datetime]]] = await semaphore_gather(50, *map(load_member, members))
        last_activity.sort(key=lambda a: (a[1].timestamp() if a[1] else -1, str(a[0])))

        out = []
        for member, timestamp in last_activity:
            if timestamp is None:
                out.append(t.user_inactive(status_icon(member.status), member.mention, f"@{member}"))
            elif timestamp >= now - timedelta(days=days):
                break
            else:
                out.append(
                    t.user_inactive_since(
                        status_icon(member.status),
                        member.mention,
                        f"@{member}",
                        timestamp.strftime("%d.%m.%Y %H:%M:%S"),
                    ),
                )

        embed = Embed(title=t.inactive_users, colour=0x256BE6)
        if out:
            embed.title = t.inactive_users_cnt(len(out))
            embed.description = "\n".join(out)
        else:
            embed.description = t.no_inactive_users
            embed.colour = 0x03AD28
        await send_long_embed(ctx, embed, paginate=True)

    @commands.command(aliases=["indur"])
    @InactivityPermission.read.check
    @optional_permissions(InactivityPermission.write)
    @guild_only()
    async def inactive_duration(self, ctx: Context, days: Optional[int]):
        """
        configure inactivity duration
        """

        if days is None:
            days = await InactivitySettings.inactive_days.get()
            await reply(ctx, t.inactive_duration(cnt=days))
            return

        if not await InactivityPermission.write.check_permissions(ctx.author):
            raise CommandError(tg.not_allowed)

        if days not in range(1, 10001):
            raise CommandError(tg.invalid_duration)

        await InactivitySettings.inactive_days.set(days)
        await reply(ctx, t.inactive_duration_set(cnt=days))
        await send_to_changelog(ctx.guild, t.inactive_duration_set(cnt=days))
