import asyncio
import random
from datetime import datetime
from os import getenv
from pathlib import Path
from typing import Optional, Union

from discord import (
    VoiceChannel,
    Embed,
    TextChannel,
    Member,
    VoiceState,
    CategoryChannel,
    Guild,
    PermissionOverwrite,
    Role,
    Forbidden,
    HTTPException,
    Message,
    NotFound,
    PartialEmoji,
    User,
)
from discord.abc import Messageable
from discord.ext import commands, tasks
from discord.ext.commands import guild_only, Context, UserInputError, CommandError, Greedy

from PyDrocsid.async_thread import gather_any, GatherAnyException
from PyDrocsid.cog import Cog
from PyDrocsid.command import docs, reply, confirm, optional_permissions
from PyDrocsid.database import filter_by, db, select, delete, db_context, db_wrapper
from PyDrocsid.embeds import send_long_embed
from PyDrocsid.emojis import name_to_emoji
from PyDrocsid.multilock import MultiLock
from PyDrocsid.prefix import get_prefix
from PyDrocsid.redis import redis
from PyDrocsid.settings import RoleSettings
from PyDrocsid.translations import t
from PyDrocsid.util import send_editable_log, check_role_assignable
from .colors import Colors
from .models import DynGroup, DynChannel, DynChannelMember, RoleVoiceLink
from .permissions import VoiceChannelPermission
from ...contributor import Contributor
from ...pubsub import send_to_changelog, send_alert

tg = t.g
t = t.voice_channel

Overwrites = dict[Union[Member, Role], PermissionOverwrite]


def merge_permission_overwrites(
    overwrites: Overwrites,
    *args: tuple[Union[Member, Role], PermissionOverwrite],
) -> Overwrites:
    out = {k: PermissionOverwrite.from_pair(*v.pair()) for k, v in overwrites.items()}
    for k, v in args:
        out.setdefault(k, PermissionOverwrite()).update(**{p: q for p, q in v if q is not None})
    return out


def check_voice_permissions(voice_channel: VoiceChannel, role: Role) -> bool:
    view_channel = voice_channel.overwrites_for(role).view_channel
    connect = voice_channel.overwrites_for(role).connect
    if view_channel is None:
        view_channel = role.permissions.view_channel
    if connect is None:
        connect = role.permissions.connect
    return view_channel and connect


async def collect_links(guild: Guild, link_set, channel_id):
    link: RoleVoiceLink
    async for link in await db.stream(filter_by(RoleVoiceLink, voice_channel=channel_id)):
        if role := guild.get_role(link.role):
            link_set.add(role)


async def update_roles(member: Member, *, add: set[Role] = None, remove: set[Role] = None):
    add = add or set()
    remove = remove or set()
    add, remove = add - remove, remove - add

    for role in remove:
        try:
            await member.remove_roles(role)
        except Forbidden:
            await send_alert(member.guild, t.could_not_remove_roles(role.mention, member.mention))

    for role in add:
        try:
            await member.add_roles(role)
        except Forbidden:
            await send_alert(member.guild, t.could_not_add_roles(role.mention, member.mention))


async def get_commands_embed() -> Embed:
    return Embed(
        title=t.dyn_voice_help_title,
        color=Colors.Voice,
        description=t.dyn_voice_help_content(prefix=await get_prefix()),
    )


async def rename_channel(channel: Union[TextChannel, VoiceChannel], name: str):
    try:
        idx, _ = await gather_any(channel.edit(name=name), asyncio.sleep(3))
    except GatherAnyException as e:
        raise e.exception

    if idx:
        raise CommandError(t.rename_rate_limit)


def get_user_role(guild: Guild, channel: DynChannel) -> Optional[Role]:
    return guild.get_role(channel.group.user_role)


def remove_lock_overrides(
    channel: DynChannel,
    voice_channel: VoiceChannel,
    overwrites: Overwrites,
    *,
    keep_members: bool,
    reset_user_role: bool,
) -> Overwrites:
    me = voice_channel.guild.me
    overwrites = {
        k: v
        for k, v in overwrites.items()
        if not isinstance(k, Member) or k == me or (keep_members and k in voice_channel.members)
    }
    if not reset_user_role:
        return overwrites

    user_role = voice_channel.guild.get_role(channel.group.user_role)
    overwrites = merge_permission_overwrites(
        overwrites,
        (user_role, PermissionOverwrite(view_channel=True)),
    )
    overwrites[user_role].update(connect=None)
    return overwrites


async def safe_create_voice_channel(
    category: Union[CategoryChannel, Guild],
    channel: DynChannel,
    name: str,
    overwrites: Overwrites,
) -> VoiceChannel:
    guild: Guild = category.guild if isinstance(category, CategoryChannel) else category
    user_role: Role = get_user_role(guild, channel)

    try:
        return await category.create_voice_channel(name, overwrites=overwrites)
    except Forbidden:
        pass

    ov = overwrites.pop(user_role, None)
    voice_channel: VoiceChannel = await category.create_voice_channel(name, overwrites=overwrites)
    if ov:
        overwrites[user_role] = ov
        await voice_channel.edit(overwrites=overwrites)

    return voice_channel


class VoiceChannelCog(Cog, name="Voice Channels"):
    CONTRIBUTORS = [
        Contributor.Defelo,
        Contributor.Florian,
        Contributor.wolflu,
        Contributor.TNT2k,
        Contributor.Scriptim,
        Contributor.MarcelCoding,
    ]

    def __init__(self, team_roles: list[str]):
        self.team_roles: list[str] = team_roles
        self._owners: dict[int, Member] = {}

        self._join_tasks: dict[tuple[Member, VoiceChannel], asyncio.Task] = {}
        self._leave_tasks: dict[tuple[Member, VoiceChannel], asyncio.Task] = {}
        self._channel_lock = MultiLock()
        self._recent_kicks: set[tuple[Member, VoiceChannel]] = set()

        names = getenv("VOICE_CHANNEL_NAMES", "*")
        if names == "*":
            name_lists = [file.name.removesuffix(".txt") for file in Path(__file__).parent.joinpath("names").iterdir()]
        else:
            name_lists = names.split(",")

        self.names: dict[str, set[str]] = {}
        for name_list in name_lists:
            self.names[name_list] = set()
            with Path(__file__).parent.joinpath(f"names/{name_list}.txt").open() as file:
                for name in file.readlines():
                    if name := name.strip():
                        self.names[name_list].add(name)

        self.allowed_names: set[str] = set()
        for path in Path(__file__).parent.joinpath("names").iterdir():
            if not path.name.endswith(".txt"):
                continue

            with path.open() as file:
                for name in file.readlines():
                    if name := name.strip():
                        self.allowed_names.add(name.lower())

    def prepare(self) -> bool:
        return bool(self.names)

    def _get_name_list(self, guild_id: int) -> str:
        r = random.Random(f"{guild_id}{datetime.utcnow().date().isoformat()}")
        return r.choice(sorted(self.names))

    def _random_channel_name(self, guild_id: int, avoid: set[str]) -> Optional[str]:
        names = self.names[self._get_name_list(guild_id)]
        allowed = list({*names} - avoid)
        if allowed and random.randrange(100):
            return random.choice(allowed)

        a = "acddflmrtneeelooanopflocrztrhetr pu2aolai hpkkxo a ea     n ul       st        u        f        f "
        c = len(b := [*range(13 - 37 + 42 >> (1 & 3 & 3 & 7 & ~42))])
        return random.shuffle(b) or next((e for d in b if (e := a[d::c].strip()) not in avoid), None)

    async def get_channel_name(self, guild: Guild) -> str:
        return self._random_channel_name(guild.id, {channel.name for channel in guild.voice_channels})

    async def is_teamler(self, member: Member) -> bool:
        return any(
            team_role in member.roles
            for role_name in self.team_roles
            if (team_role := member.guild.get_role(await RoleSettings.get(role_name))) is not None
        )

    def get_text_channel(self, channel: DynChannel) -> TextChannel:
        if text_channel := self.bot.get_channel(channel.text_id):
            return text_channel

        raise CommandError(t.no_text_channel(f"<#{channel.channel_id}>"))

    async def get_owner(self, channel: DynChannel) -> Optional[Member]:
        if out := self._owners.get(channel.channel_id):
            return out

        self._owners[channel.channel_id] = await self.fetch_owner(channel)
        return self._owners[channel.channel_id]

    async def update_owner(self, channel: DynChannel, new_owner: Optional[Member]) -> Optional[Member]:
        old_owner: Optional[Member] = self._owners.get(channel.channel_id)

        if not new_owner:
            self._owners.pop(channel.channel_id, None)
        elif old_owner != new_owner:
            self._owners[channel.channel_id] = new_owner
            await self.send_voice_msg(
                channel,
                t.voice_channel,
                t.voice_owner_changed(new_owner.mention),
            )

        return new_owner

    async def send_voice_msg(self, channel: DynChannel, title: str, msg: str, force_new_embed: bool = False):
        try:
            text_channel: TextChannel = self.get_text_channel(channel)
        except CommandError as e:
            await send_alert(self.bot.guilds[0], *e.args)
            return

        color = int([Colors.unlocked, Colors.locked][channel.locked])
        try:
            message: Message = await send_editable_log(
                text_channel,
                title,
                "",
                datetime.utcnow().strftime("%d.%m.%Y %H:%M:%S"),
                msg,
                colour=color,
                force_new_embed=force_new_embed,
                force_new_field=True,
            )
        except Forbidden:
            await send_alert(text_channel.guild, t.could_not_send_voice_msg(text_channel.mention))
            return

        await self.update_control_message(channel, message)

    async def update_control_message(self, channel: DynChannel, message: Message):
        async def clear_reactions(msg_id):
            try:
                await (await message.channel.fetch_message(msg_id)).clear_reactions()
            except Forbidden:
                await send_alert(message.guild, t.could_not_clear_reactions(message.jump_url, message.channel.mention))
            except NotFound:
                pass

        async def update_reactions(add, rm):
            if rm:
                try:
                    await asyncio.gather(*[rct.clear() for rct in rm])
                except Forbidden:
                    await send_alert(
                        message.guild,
                        t.could_not_clear_reactions(message.jump_url, message.channel.mention),
                    )
                except NotFound:
                    return

            if add:
                try:
                    await asyncio.gather(*[message.add_reaction(e) for e in add])
                except Forbidden:
                    await send_alert(
                        message.guild,
                        t.could_not_add_reactions(message.jump_url, message.channel.mention),
                    )
                except NotFound:
                    return

        if (msg := await redis.get(key := f"dynvc_control_message:{channel.text_id}")) and msg != str(message.id):
            asyncio.create_task(clear_reactions(msg))

        await redis.setex(key, 86400, message.id)

        voice_channel: VoiceChannel = self.bot.get_channel(channel.channel_id)
        user_role = voice_channel.guild.get_role(channel.group.user_role)
        locked = channel.locked
        hidden = voice_channel.overwrites_for(user_role).view_channel is False

        emojis = [
            "information_source",
            "grey_question",
            "lock" if not locked else "unlock",
            "man_detective" if not hidden else "eye",
        ]
        emojis = list(map(name_to_emoji.get, emojis))

        remove = []

        for reaction in message.reactions:
            if reaction.me and reaction.emoji in emojis:
                emojis.remove(reaction.emoji)
            else:
                remove.append(reaction)

        asyncio.create_task(update_reactions(emojis, remove))

    async def on_raw_reaction_add(self, message: Message, emoji: PartialEmoji, user: Union[Member, User]):
        if not message.guild or user.bot:
            return
        if str(message.id) != await redis.get(f"dynvc_control_message:{message.channel.id}"):
            return

        channel: Optional[DynChannel] = await DynChannel.get(text_id=message.channel.id)
        if not channel:
            return

        async with self._channel_lock[channel.group_id]:

            try:
                await message.remove_reaction(emoji, user)
            except Forbidden:
                await send_alert(message.guild, t.could_not_clear_reactions(message.jump_url, message.channel.mention))
            except NotFound:
                pass

            if str(emoji) == name_to_emoji["information_source"]:
                await self.send_voice_info(message.channel, channel)
                return
            elif str(emoji) == name_to_emoji["grey_question"]:
                await self.update_control_message(
                    channel,
                    await message.channel.send(embed=await get_commands_embed()),
                )
                return

            try:
                await self.check_authorization(channel, user)
            except CommandError:
                return

            voice_channel: VoiceChannel = self.bot.get_channel(channel.channel_id)
            user_role = voice_channel.guild.get_role(channel.group.user_role)
            locked = channel.locked
            hidden = voice_channel.overwrites_for(user_role).view_channel is False

            if str(emoji) == name_to_emoji["lock"] and not locked:
                await self.lock_channel(user, channel, voice_channel, hide=False)
            elif str(emoji) == name_to_emoji["unlock"] and locked:
                await self.unlock_channel(user, channel, voice_channel)
            elif str(emoji) == name_to_emoji["man_detective"] and not hidden:
                await self.lock_channel(user, channel, voice_channel, hide=True)
            elif str(emoji) == name_to_emoji["eye"] and hidden:
                await self.unhide_channel(user, channel, voice_channel)

    async def fix_owner(self, channel: DynChannel) -> Optional[Member]:
        voice_channel: VoiceChannel = self.bot.get_channel(channel.channel_id)

        in_voice = {m.id for m in voice_channel.members}
        for m in channel.members:
            if m.member_id in in_voice:
                member = voice_channel.guild.get_member(m.member_id)
                if member.bot:
                    continue

                channel.owner_id = m.id
                return await self.update_owner(channel, member)

        channel.owner_id = None
        return await self.update_owner(channel, None)

    async def fetch_owner(self, channel: DynChannel) -> Optional[Member]:
        voice_channel: VoiceChannel = self.bot.get_channel(channel.channel_id)

        if channel.owner_override and any(channel.owner_override == member.id for member in voice_channel.members):
            return voice_channel.guild.get_member(channel.owner_override)

        owner: Optional[DynChannelMember] = await db.get(DynChannelMember, id=channel.owner_id)
        if owner and any(owner.member_id == member.id for member in voice_channel.members):
            return voice_channel.guild.get_member(owner.member_id)

        return await self.fix_owner(channel)

    async def check_authorization(self, channel: DynChannel, member: Member):
        if await VoiceChannelPermission.override_owner.check_permissions(member):
            return

        if await self.get_owner(channel) == member:
            return

        raise CommandError(t.private_voice_owner_required)

    async def get_channel(
        self,
        member: Member,
        *,
        check_owner: bool,
        check_locked: bool = False,
    ) -> tuple[DynChannel, VoiceChannel]:
        if member.voice is None or member.voice.channel is None:
            raise CommandError(t.not_in_voice)

        voice_channel: VoiceChannel = member.voice.channel
        channel: Optional[DynChannel] = await db.get(
            DynChannel,
            [DynChannel.group, DynGroup.channels],
            DynChannel.members,
            channel_id=voice_channel.id,
        )
        if not channel:
            raise CommandError(t.not_in_voice)

        if check_locked and not channel.locked:
            raise CommandError(t.channel_not_locked)

        if check_owner:
            await self.check_authorization(channel, member)

        return channel, voice_channel

    async def on_ready(self):
        guild: Guild = self.bot.guilds[0]

        role_voice_links: dict[Role, list[VoiceChannel]] = {}

        link: RoleVoiceLink
        async for link in await db.stream(select(RoleVoiceLink)):
            role: Optional[Role] = guild.get_role(link.role)
            if role is None:
                await db.delete(link)
                continue

            if link.voice_channel.isnumeric():
                voice: Optional[VoiceChannel] = guild.get_channel(int(link.voice_channel))
                if not voice:
                    await db.delete(link)
                else:
                    role_voice_links.setdefault(role, []).append(voice)
            else:
                group: Optional[DynGroup] = await db.get(DynGroup, DynGroup.channels, id=link.voice_channel)
                if not group:
                    await db.delete(link)
                    continue

                for channel in group.channels:
                    if voice := guild.get_channel(channel.channel_id):
                        role_voice_links.setdefault(role, []).append(voice)

        role_changes: dict[Member, tuple[set[Role], set[Role]]] = {}
        for role, channels in role_voice_links.items():
            members = set()
            for channel in channels:
                members.update(channel.members)
            for member in members:
                if role not in member.roles:
                    role_changes.setdefault(member, (set(), set()))[0].add(role)
            for member in role.members:
                if member not in members:
                    role_changes.setdefault(member, (set(), set()))[1].add(role)

        for member, (add, remove) in role_changes.items():
            asyncio.create_task(update_roles(member, add=add, remove=remove))

        try:
            self.vc_loop.start()
        except RuntimeError:
            self.vc_loop.restart()

    @tasks.loop(minutes=30)
    @db_wrapper
    async def vc_loop(self):
        guild: Guild = self.bot.guilds[0]

        channel: DynChannel
        async for channel in await db.stream(select(DynChannel)):
            voice_channel: Optional[VoiceChannel] = guild.get_channel(channel.channel_id)
            if not voice_channel:
                await db.delete(channel)
                continue

            if not voice_channel.members:
                asyncio.create_task(voice_channel.edit(name=await self.get_channel_name(guild)))

    async def lock_channel(self, member: Member, channel: DynChannel, voice_channel: VoiceChannel, *, hide: bool):
        locked = channel.locked
        channel.locked = True
        member_overwrites = [
            (member, PermissionOverwrite(view_channel=True, connect=True)) for member in voice_channel.members
        ]
        overwrites = merge_permission_overwrites(
            voice_channel.overwrites,
            (
                voice_channel.guild.get_role(channel.group.user_role),
                PermissionOverwrite(view_channel=not hide, connect=False),
            ),
            *member_overwrites,
        )

        try:
            await voice_channel.edit(overwrites=overwrites)
        except Forbidden:
            raise CommandError(t.could_not_overwrite_permissions(voice_channel.mention))

        text_channel = self.get_text_channel(channel)
        try:
            await text_channel.edit(overwrites=merge_permission_overwrites(text_channel.overwrites, *member_overwrites))
        except Forbidden:
            raise CommandError(t.could_not_overwrite_permissions(text_channel.mention))

        if hide:
            await self.send_voice_msg(channel, t.voice_channel, t.hidden(member.mention), force_new_embed=not locked)
        else:
            await self.send_voice_msg(channel, t.voice_channel, t.locked(member.mention), force_new_embed=True)

    async def unlock_channel(
        self,
        member: Optional[Member],
        channel: DynChannel,
        voice_channel: VoiceChannel,
        *,
        skip_text: bool = False,
    ):
        channel.locked = False
        overwrites = remove_lock_overrides(
            channel,
            voice_channel,
            voice_channel.overwrites,
            keep_members=False,
            reset_user_role=True,
        )

        try:
            await voice_channel.edit(overwrites=overwrites)
        except Forbidden:
            raise CommandError(t.could_not_overwrite_permissions(voice_channel.mention))

        if skip_text:
            return

        text_channel = self.get_text_channel(channel)
        try:
            await text_channel.edit(
                overwrites=remove_lock_overrides(
                    channel,
                    voice_channel,
                    text_channel.overwrites,
                    keep_members=True,
                    reset_user_role=False,
                ),
            )
        except Forbidden:
            raise CommandError(t.could_not_overwrite_permissions(text_channel.mention))

        await self.send_voice_msg(channel, t.voice_channel, t.unlocked(member.mention), force_new_embed=True)

    async def unhide_channel(self, member: Member, channel: DynChannel, voice_channel: VoiceChannel):
        user_role = voice_channel.guild.get_role(channel.group.user_role)

        try:
            await voice_channel.set_permissions(user_role, view_channel=True, connect=False)
        except Forbidden:
            raise CommandError(t.could_not_overwrite_permissions(voice_channel.mention))

        await self.send_voice_msg(channel, t.voice_channel, t.visible(member.mention))

    async def add_to_channel(self, channel: DynChannel, voice_channel: VoiceChannel, member: Member):
        overwrite = PermissionOverwrite(view_channel=True, connect=True)
        try:
            await voice_channel.set_permissions(member, overwrite=overwrite)
        except Forbidden:
            raise CommandError(t.could_not_overwrite_permissions(voice_channel.mention))

        text_channel = self.get_text_channel(channel)
        try:
            await text_channel.set_permissions(member, overwrite=overwrite)
        except Forbidden:
            raise CommandError(t.could_not_overwrite_permissions(text_channel.mention))

        await self.send_voice_msg(channel, t.voice_channel, t.user_added(member.mention))

    async def remove_from_channel(self, channel: DynChannel, voice_channel: VoiceChannel, member: Member):
        try:
            await voice_channel.set_permissions(member, overwrite=None)
        except Forbidden:
            raise CommandError(t.could_not_overwrite_permissions(voice_channel.mention))

        text_channel = self.get_text_channel(channel)
        try:
            await text_channel.set_permissions(member, overwrite=None)
        except Forbidden:
            raise CommandError(t.could_not_overwrite_permissions(text_channel.mention))

        await db.exec(delete(DynChannelMember).filter_by(channel_id=voice_channel.id, member_id=member.id))
        is_owner = member == await self.get_owner(channel)
        if member.voice and member.voice.channel == voice_channel:
            try:
                await member.move_to(None)
            except Forbidden:
                await send_alert(member.guild, t.could_not_kick(member.mention, voice_channel.mention))
                is_owner = False
            else:
                self._recent_kicks.add((member, voice_channel))

        await self.send_voice_msg(channel, t.voice_channel, t.user_removed(member.mention))
        if is_owner:
            await self.fix_owner(channel)

    async def member_join(self, member: Member, voice_channel: VoiceChannel):
        channel: Optional[DynChannel] = await DynChannel.get(channel_id=voice_channel.id)
        if not channel:
            return

        guild: Guild = voice_channel.guild
        category: Union[CategoryChannel, Guild] = voice_channel.category or guild

        text_channel: Optional[TextChannel] = self.bot.get_channel(channel.text_id)
        if not text_channel:
            overwrites = {
                guild.default_role: PermissionOverwrite(read_messages=False, connect=False),
                guild.me: PermissionOverwrite(read_messages=True, manage_channels=True),
            }
            for role_name in self.team_roles:
                if not (team_role := guild.get_role(await RoleSettings.get(role_name))):
                    continue
                if check_voice_permissions(voice_channel, team_role):
                    overwrites[team_role] = PermissionOverwrite(read_messages=True)
            try:
                text_channel = await category.create_text_channel(
                    voice_channel.name,
                    topic=t.text_channel_for(voice_channel.mention),
                    overwrites=overwrites,
                )
            except (Forbidden, HTTPException):
                await send_alert(voice_channel.guild, t.could_not_create_text_channel(voice_channel.mention))
                return

            channel.text_id = text_channel.id
            await text_channel.send(embed=await get_commands_embed())
            await self.send_voice_msg(channel, t.voice_channel, t.dyn_voice_created(member.mention))

        try:
            await text_channel.set_permissions(member, overwrite=PermissionOverwrite(read_messages=True))
        except Forbidden:
            await send_alert(voice_channel.guild, t.could_not_overwrite_permissions(text_channel.mention))

        await self.send_voice_msg(channel, t.voice_channel, t.dyn_voice_joined(member.mention))

        if channel.locked and member not in voice_channel.overwrites:
            try:
                await self.add_to_channel(channel, voice_channel, member)
            except CommandError as e:
                await send_alert(voice_channel.guild, *e.args)

        channel_member: Optional[DynChannelMember] = await db.get(
            DynChannelMember,
            member_id=member.id,
            channel_id=voice_channel.id,
        )
        if not channel_member:
            channel.members.append(channel_member := await DynChannelMember.create(member.id, voice_channel.id))

        owner: Optional[DynChannelMember] = await db.get(DynChannelMember, id=channel.owner_id)
        update_owner = False
        if (not owner or channel_member.timestamp < owner.timestamp) and channel.owner_id != channel_member.id:
            if not member.bot:
                channel.owner_id = channel_member.id
                update_owner = True
        if update_owner or channel.owner_override == member.id:
            await self.update_owner(channel, await self.fetch_owner(channel))

        if all(c.members for chnl in channel.group.channels if (c := self.bot.get_channel(chnl.channel_id))):
            overwrites = voice_channel.overwrites
            if channel.locked:
                overwrites = remove_lock_overrides(
                    channel,
                    voice_channel,
                    overwrites,
                    keep_members=False,
                    reset_user_role=True,
                )
            try:
                new_channel = await safe_create_voice_channel(
                    category,
                    channel,
                    await self.get_channel_name(guild),
                    overwrites,
                )
            except (Forbidden, HTTPException):
                await send_alert(voice_channel.guild, t.could_not_create_voice_channel)
            else:
                await DynChannel.create(new_channel.id, channel.group_id)

    async def member_leave(self, member: Member, voice_channel: VoiceChannel):
        channel: Optional[DynChannel] = await DynChannel.get(channel_id=voice_channel.id)
        if not channel:
            return

        text_channel: Optional[TextChannel] = self.bot.get_channel(channel.text_id)
        if not text_channel:
            await send_alert(voice_channel.guild, t.no_text_channel(f"<#{channel.channel_id}>"))

        if text_channel and not channel.locked:
            try:
                await text_channel.set_permissions(member, overwrite=None)
            except Forbidden:
                await send_alert(voice_channel.guild, t.could_not_overwrite_permissions(text_channel.mention))

        if text_channel:
            await self.send_voice_msg(channel, t.voice_channel, t.dyn_voice_left(member.mention))

        owner: Optional[DynChannelMember] = await db.get(DynChannelMember, id=channel.owner_id)
        if owner and owner.member_id == member.id or channel.owner_override == member.id:
            await self.fix_owner(channel)

        if any(not m.bot for m in voice_channel.members):
            return

        async def delete_text():
            if text_channel:
                try:
                    await text_channel.delete()
                except Forbidden:
                    await send_alert(text_channel.guild, t.could_not_delete_channel(text_channel.mention))
                    return

        async def delete_voice():
            channel.owner_id = None
            channel.owner_override = None
            await db.exec(delete(DynChannelMember).filter_by(channel_id=voice_channel.id))
            channel.members.clear()

            try:
                await voice_channel.delete()
            except Forbidden:
                await send_alert(voice_channel.guild, t.could_not_delete_channel(voice_channel.mention))
                return
            else:
                await db.delete(channel)

        async def create_new_channel() -> bool:
            # check if there is at least one empty channel
            if not all(
                any(not m.bot for m in c.members)
                for chnl in channel.group.channels
                if chnl.channel_id != channel.channel_id and (c := self.bot.get_channel(chnl.channel_id))
            ):
                return True

            guild: Guild = voice_channel.guild
            category: Union[CategoryChannel, Guild] = voice_channel.category or guild

            overwrites = voice_channel.overwrites
            if channel.locked:
                overwrites = remove_lock_overrides(
                    channel,
                    voice_channel,
                    overwrites,
                    keep_members=False,
                    reset_user_role=True,
                )
            try:
                new_channel = await safe_create_voice_channel(
                    category,
                    channel,
                    await self.get_channel_name(guild),
                    overwrites,
                )
            except (Forbidden, HTTPException):
                await send_alert(guild, t.could_not_create_voice_channel)
                return False
            else:
                await DynChannel.create(new_channel.id, channel.group_id)
                return True

        await delete_text()
        if await create_new_channel():
            await delete_voice()

    async def on_voice_state_update(self, member: Member, before: VoiceState, after: VoiceState):
        if before.channel == after.channel:
            return

        async def delayed(delay, key, func, delay_callback, *args):
            await asyncio.sleep(delay)
            delay_callback()
            async with self._channel_lock[key]:
                async with db_context():
                    return await func(*args)

        async def create_task(delay, c, task_dict, cancel_dict, func):
            dyn_channel: Optional[DynChannel] = await DynChannel.get(channel_id=channel.id)
            if not dyn_channel:
                return

            await collect_links(member.guild, roles := set(), dyn_channel.group_id)
            if func == self.member_leave:
                await update_roles(member, remove=roles)
            else:
                await update_roles(member, add=roles)

            key = member, c
            if task := cancel_dict.pop(key, None):
                task.cancel()
            elif key not in task_dict:
                task_dict[key] = asyncio.create_task(
                    delayed(delay, dyn_channel.group_id, func, lambda: task_dict.pop(key, None), *key),
                )

        remove: set[Role] = set()
        add: set[Role] = set()

        if channel := before.channel:
            await collect_links(channel.guild, remove, str(channel.id))
            if (k := (member, channel)) in self._recent_kicks:
                self._recent_kicks.remove(k)
                await self.member_leave(member, channel)
            else:
                await create_task(5, channel, self._leave_tasks, self._join_tasks, self.member_leave)

        if channel := after.channel:
            await collect_links(channel.guild, add, str(channel.id))
            await create_task(1, channel, self._join_tasks, self._leave_tasks, self.member_join)

        await update_roles(member, add=add, remove=remove)

    @commands.group(aliases=["vc"])
    @guild_only()
    @docs(t.commands.voice)
    async def voice(self, ctx: Context):
        if ctx.invoked_subcommand is None:
            raise UserInputError

    @voice.group(name="dynamic", aliases=["dyn", "d"])
    @VoiceChannelPermission.dyn_read.check
    @docs(t.commands.voice_dynamic)
    async def voice_dynamic(self, ctx: Context):
        if len(ctx.message.content.lstrip(ctx.prefix).split()) > 2:
            if ctx.invoked_subcommand is None:
                raise UserInputError
            return

        embed = Embed(title=t.voice_channel, colour=Colors.Voice)

        group: DynGroup
        async for group in await db.stream(select(DynGroup, DynGroup.channels)):
            channels: list[tuple[str, VoiceChannel, Optional[TextChannel]]] = []
            for channel in group.channels:
                voice_channel: Optional[VoiceChannel] = ctx.guild.get_channel(channel.channel_id)
                text_channel: Optional[TextChannel] = ctx.guild.get_channel(channel.text_id)
                if not voice_channel:
                    await db.delete(channel)
                    continue

                if channel.locked:
                    if voice_channel.overwrites_for(voice_channel.guild.get_role(channel.group.user_role)).view_channel:
                        icon = "lock"
                    else:
                        icon = "man_detective"
                else:
                    icon = "unlock"

                channels.append((icon, voice_channel, text_channel))

            if not channels:
                await db.delete(group)
                continue

            embed.add_field(
                name=t.cnt_channels(cnt=len(channels)),
                value="\n".join(f":{icon}: {vc.mention} {txt.mention if txt else ''}" for icon, vc, txt in channels),
                inline=False,
            )

        if not embed.fields:
            embed.colour = Colors.error
            embed.description = t.no_dyn_group
        await send_long_embed(ctx, embed, paginate=True)

    @voice_dynamic.command(name="add", aliases=["a", "+"])
    @VoiceChannelPermission.dyn_write.check
    @docs(t.commands.voice_dynamic_add)
    async def voice_dynamic_add(self, ctx: Context, user_role: Optional[Role], *, voice_channel: VoiceChannel):
        everyone = voice_channel.guild.default_role
        user_role = user_role or everyone
        if not check_voice_permissions(voice_channel, user_role):
            raise CommandError(t.invalid_user_role(user_role.mention if user_role != everyone else "@everyone"))

        if await db.exists(filter_by(DynChannel, channel_id=voice_channel.id)):
            raise CommandError(t.dyn_group_already_exists)

        try:
            await voice_channel.edit(name=await self.get_channel_name(voice_channel.guild))
        except Forbidden:
            raise CommandError(t.cannot_edit)

        await DynGroup.create(voice_channel.id, user_role.id)
        embed = Embed(title=t.voice_channel, colour=Colors.Voice, description=t.dyn_group_created)
        await reply(ctx, embed=embed)
        await send_to_changelog(ctx.guild, t.log_dyn_group_created)

    @voice_dynamic.command(name="remove", aliases=["del", "d", "r", "-"])
    @VoiceChannelPermission.dyn_write.check
    @docs(t.commands.voice_dynamic_remove)
    async def voice_dynamic_remove(self, ctx: Context, *, voice_channel: VoiceChannel):
        channel: Optional[DynChannel] = await db.get(
            DynChannel,
            [DynChannel.group, DynGroup.channels],
            DynChannel.members,
            channel_id=voice_channel.id,
        )
        if not channel:
            raise CommandError(t.dyn_group_not_found)

        for c in channel.group.channels:
            if (x := self.bot.get_channel(c.channel_id)) and c.channel_id != voice_channel.id:
                try:
                    await x.delete()
                except Forbidden:
                    raise CommandError(t.could_not_delete_channel(x.mention))
            if x := self.bot.get_channel(c.text_id):
                try:
                    await x.delete()
                except Forbidden:
                    raise CommandError(t.could_not_delete_channel(x.mention))

        await db.delete(channel.group)
        embed = Embed(title=t.voice_channel, colour=Colors.Voice, description=t.dyn_group_removed)
        await reply(ctx, embed=embed)
        await send_to_changelog(ctx.guild, t.log_dyn_group_removed)

    @voice.command(name="help", aliases=["commands", "c"])
    @docs(t.commands.help)
    async def voice_help(self, ctx: Context):
        message = await reply(ctx, embed=await get_commands_embed())

        if channel := await DynChannel.get(text_id=ctx.channel.id):
            await self.update_control_message(channel, message)

    @voice.command(name="info", aliases=["i"])
    @docs(t.commands.voice_info)
    async def voice_info(self, ctx: Context, *, voice_channel: Optional[Union[VoiceChannel, Member]] = None):
        if not voice_channel:
            if channel := await db.get(DynChannel, text_id=ctx.channel.id):
                voice_channel = self.bot.get_channel(channel.channel_id)

        if not isinstance(voice_channel, VoiceChannel):
            member = voice_channel or ctx.author
            if not member.voice:
                if not voice_channel:
                    raise CommandError(t.not_in_voice)
                if await self.is_teamler(ctx.author):
                    raise CommandError(t.user_not_in_voice)
                raise CommandError(tg.permission_denied)
            voice_channel = member.voice.channel

        channel: Optional[DynChannel] = await db.get(
            DynChannel,
            [DynChannel.group, DynGroup.channels],
            DynChannel.members,
            channel_id=voice_channel.id,
        )
        if not channel:
            raise CommandError(t.dyn_group_not_found)

        if not voice_channel.permissions_for(ctx.author).connect:
            raise CommandError(tg.permission_denied)

        await self.send_voice_info(ctx, channel)

    async def send_voice_info(self, target: Messageable, channel: DynChannel):
        voice_channel: VoiceChannel = self.bot.get_channel(channel.channel_id)
        if channel.locked:
            if voice_channel.overwrites_for(voice_channel.guild.get_role(channel.group.user_role)).view_channel:
                state = t.state.locked
            else:
                state = t.state.hidden
        else:
            state = t.state.unlocked

        embed = Embed(
            title=t.voice_info,
            color=[Colors.unlocked, Colors.locked][channel.locked],
        )
        embed.add_field(name=t.voice_name, value=voice_channel.name)
        embed.add_field(name=t.voice_state, value=state)

        if owner := await self.get_owner(channel):
            embed.add_field(name=t.voice_owner, value=owner.mention)

        out = []

        active = members = set(voice_channel.members)
        if channel.locked:
            members = {m for m in voice_channel.overwrites if isinstance(m, Member)}

        join_map = {m.member_id: m.timestamp.timestamp() for m in channel.members}
        members = sorted(members, key=lambda m: -1 if m.id == channel.owner_override else join_map.get(m.id, 1e1337))

        for member in members:
            if member in active:
                out.append(f":small_orange_diamond: {member.mention}")
            else:
                out.append(f":small_blue_diamond: {member.mention}")

        if channel.locked:
            name = t.voice_members.locked(len(active), cnt=len(members))
        else:
            name = t.voice_members.unlocked(cnt=len(members))
        embed.add_field(name=name, value="\n".join(out), inline=False)

        messages = await send_long_embed(target, embed, paginate=True)
        if channel := await DynChannel.get(text_id=channel.text_id):
            await self.update_control_message(channel, messages[-1])

    @voice.command(name="rename")
    @optional_permissions(VoiceChannelPermission.dyn_rename, VoiceChannelPermission.override_owner)
    @docs(t.commands.voice_rename)
    async def voice_rename(self, ctx: Context, *, name: Optional[str]):
        channel, voice_channel = await self.get_channel(ctx.author, check_owner=True)
        text_channel: TextChannel = self.get_text_channel(channel)
        old_name = voice_channel.name

        if not name:
            name = await self.get_channel_name(ctx.guild)
        elif name.lower() not in self.allowed_names:
            if not await VoiceChannelPermission.dyn_rename.check_permissions(ctx.author):
                raise CommandError(t.no_custom_name)

        if any(c.id != voice_channel.id and name == c.name for c in voice_channel.guild.voice_channels):
            conf_embed = Embed(title=t.rename_confirmation, description=t.rename_description, color=Colors.Voice)
            async with confirm(ctx, conf_embed) as (result, msg):
                if not result:
                    conf_embed.description += "\n\n" + t.canceled
                    return

                conf_embed.description += "\n\n" + t.confirmed
                if msg:
                    await msg.delete(delay=5)

        try:
            await rename_channel(voice_channel, name)
            await rename_channel(text_channel, name)
        except Forbidden:
            raise CommandError(t.cannot_edit)
        except HTTPException:
            raise CommandError(t.rename_failed)

        await self.send_voice_msg(channel, t.voice_channel, t.renamed(ctx.author.mention, old_name, name))
        await ctx.message.add_reaction(name_to_emoji["white_check_mark"])

    @voice.command(name="owner", aliases=["o"])
    @optional_permissions(VoiceChannelPermission.override_owner)
    @docs(t.commands.voice_owner)
    async def voice_owner(self, ctx: Context, member: Member):
        channel, voice_channel = await self.get_channel(ctx.author, check_owner=True)

        if member not in voice_channel.members:
            raise CommandError(t.user_not_in_this_channel)
        if member.bot:
            raise CommandError(t.bot_no_owner_transfer)

        if await self.get_owner(channel) == member:
            raise CommandError(t.already_owner(member.mention))

        channel.owner_override = member.id
        await self.update_owner(channel, member)
        await ctx.message.add_reaction(name_to_emoji["white_check_mark"])

    @voice.command(name="lock", aliases=["l"])
    @optional_permissions(VoiceChannelPermission.override_owner)
    @docs(t.commands.voice_lock)
    async def voice_lock(self, ctx: Context):
        channel, voice_channel = await self.get_channel(ctx.author, check_owner=True)
        if channel.locked:
            raise CommandError(t.already_locked)

        await self.lock_channel(ctx.author, channel, voice_channel, hide=False)
        await ctx.message.add_reaction(name_to_emoji["white_check_mark"])

    @voice.command(name="hide", aliases=["h"])
    @optional_permissions(VoiceChannelPermission.override_owner)
    @docs(t.commands.voice_hide)
    async def voice_hide(self, ctx: Context):
        channel, voice_channel = await self.get_channel(ctx.author, check_owner=True)
        user_role = voice_channel.guild.get_role(channel.group.user_role)
        locked = channel.locked
        if locked and not voice_channel.overwrites_for(user_role).view_channel:
            raise CommandError(t.already_hidden)

        await self.lock_channel(ctx.author, channel, voice_channel, hide=True)
        await ctx.message.add_reaction(name_to_emoji["white_check_mark"])

    @voice.command(name="show", aliases=["s", "unhide"])
    @optional_permissions(VoiceChannelPermission.override_owner)
    @docs(t.commands.voice_show)
    async def voice_show(self, ctx: Context):
        channel, voice_channel = await self.get_channel(ctx.author, check_owner=True)
        user_role = voice_channel.guild.get_role(channel.group.user_role)
        if not channel.locked or voice_channel.overwrites_for(user_role).view_channel:
            raise CommandError(t.not_hidden)

        await self.unhide_channel(ctx.author, channel, voice_channel)
        await ctx.message.add_reaction(name_to_emoji["white_check_mark"])

    @voice.command(name="unlock", aliases=["u"])
    @optional_permissions(VoiceChannelPermission.override_owner)
    @docs(t.commands.voice_unlock)
    async def voice_unlock(self, ctx: Context):
        channel, voice_channel = await self.get_channel(ctx.author, check_owner=True)
        if not channel.locked:
            raise CommandError(t.already_unlocked)

        await self.unlock_channel(ctx.author, channel, voice_channel)
        await ctx.message.add_reaction(name_to_emoji["white_check_mark"])

    @voice.command(name="add", aliases=["a", "+", "invite"])
    @optional_permissions(VoiceChannelPermission.override_owner)
    @docs(t.commands.voice_add)
    async def voice_add(self, ctx: Context, *members: Greedy[Member]):
        if not members:
            raise UserInputError

        channel, voice_channel = await self.get_channel(ctx.author, check_owner=True, check_locked=True)

        if self.bot.user in members:
            raise CommandError(t.cannot_add_user(self.bot.user.mention))

        for member in set(members):
            await self.add_to_channel(channel, voice_channel, member)

        await ctx.message.add_reaction(name_to_emoji["white_check_mark"])

    @voice.command(name="remove", aliases=["r", "-", "kick", "k"])
    @optional_permissions(VoiceChannelPermission.override_owner)
    @docs(t.commands.voice_remove)
    async def voice_remove(self, ctx: Context, *members: Greedy[Member]):
        if not members:
            raise UserInputError

        channel, voice_channel = await self.get_channel(ctx.author, check_owner=True, check_locked=True)

        members = set(members)
        if self.bot.user in members:
            raise CommandError(t.cannot_remove_user(self.bot.user.mention))
        if ctx.author in members:
            raise CommandError(t.cannot_remove_user(ctx.author.mention))

        team_roles: list[Role] = [
            team_role
            for role_name in self.team_roles
            if (team_role := ctx.guild.get_role(await RoleSettings.get(role_name)))
            if check_voice_permissions(voice_channel, team_role)
        ]
        for member in members:
            if member not in voice_channel.overwrites:
                raise CommandError(t.not_added(member.mention))
            if any(role in member.roles for role in team_roles):
                raise CommandError(t.cannot_remove_user(member.mention))

        for member in members:
            await self.remove_from_channel(channel, voice_channel, member)

        await ctx.message.add_reaction(name_to_emoji["white_check_mark"])

    @voice.group(name="role_links", aliases=["rl"])
    @VoiceChannelPermission.link_read.check
    @docs(t.commands.voice_link)
    async def voice_link(self, ctx: Context):
        if len(ctx.message.content.lstrip(ctx.prefix).split()) > 2:
            if ctx.invoked_subcommand is None:
                raise UserInputError
            return

        guild: Guild = ctx.guild

        out: list[tuple[VoiceChannel, Role]] = []
        link: RoleVoiceLink
        async for link in await db.stream(select(RoleVoiceLink)):
            role: Optional[Role] = guild.get_role(link.role)
            if role is None:
                await db.delete(link)
                continue

            if link.voice_channel.isnumeric():
                voice: Optional[VoiceChannel] = guild.get_channel(int(link.voice_channel))
                if not voice:
                    await db.delete(link)
                    continue
                out.append((voice, role))
            else:
                group: Optional[DynGroup] = await db.get(DynGroup, DynGroup.channels, id=link.voice_channel)
                if not group:
                    await db.delete(link)
                    continue

                for channel in group.channels:
                    if voice := guild.get_channel(channel.channel_id):
                        out.append((voice, role))

        embed = Embed(title=t.voice_channel, color=Colors.Voice)
        embed.description = "\n".join(
            f"{voice.mention} (`{voice.id}`) -> {role.mention} (`{role.id}`)" for voice, role in out
        )

        if not out:
            embed.colour = Colors.error
            embed.description = t.no_links_created

        await send_long_embed(ctx, embed)

    def gather_members(self, channel: Optional[DynChannel], voice_channel: VoiceChannel) -> set[Member]:
        members: set[Member] = set(voice_channel.members)
        if not channel:
            return members

        for dyn_channel in channel.group.channels:
            if x := self.bot.get_channel(dyn_channel.channel_id):
                members.update(x.members)

        return members

    @voice_link.command(name="add", aliases=["a", "+"])
    @VoiceChannelPermission.link_write.check
    @docs(t.commands.voice_link_add)
    async def voice_link_add(self, ctx: Context, voice_channel: VoiceChannel, *, role: Role):
        if channel := await DynChannel.get(channel_id=voice_channel.id):
            voice_id = channel.group_id
        else:
            voice_id = str(voice_channel.id)

        if await db.exists(filter_by(RoleVoiceLink, role=role.id, voice_channel=voice_id)):
            raise CommandError(t.link_already_exists)

        check_role_assignable(role)

        await RoleVoiceLink.create(role.id, voice_id)

        for m in self.gather_members(channel, voice_channel):
            asyncio.create_task(update_roles(m, add={role}))

        embed = Embed(
            title=t.voice_channel,
            colour=Colors.Voice,
            description=t.link_created(voice_channel, role.id),
        )
        await reply(ctx, embed=embed)
        await send_to_changelog(ctx.guild, t.log_link_created(voice_channel, role))

    @voice_link.command(name="remove", aliases=["del", "r", "d", "-"])
    @VoiceChannelPermission.link_write.check
    @docs(t.commands.voice_link_remove)
    async def voice_link_remove(self, ctx: Context, voice_channel: VoiceChannel, *, role: Role):
        if channel := await DynChannel.get(channel_id=voice_channel.id):
            voice_id = channel.group_id
        else:
            voice_id = str(voice_channel.id)

        link: Optional[RoleVoiceLink] = await db.get(RoleVoiceLink, role=role.id, voice_channel=voice_id)
        if not link:
            raise CommandError(t.link_not_found)

        await db.delete(link)

        for m in self.gather_members(channel, voice_channel):
            asyncio.create_task(update_roles(m, remove={role}))

        embed = Embed(title=t.voice_channel, colour=Colors.Voice, description=t.link_deleted)
        await reply(ctx, embed=embed)
        await send_to_changelog(ctx.guild, t.log_link_deleted(voice_channel, role))
