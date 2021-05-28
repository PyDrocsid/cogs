import random
import re
from datetime import datetime
from typing import Optional, Union, Tuple, List, Dict, Set

from discord import CategoryChannel, PermissionOverwrite, NotFound, Message, Embed, Forbidden
from discord import Member, VoiceState, Guild, VoiceChannel, Role, HTTPException, TextChannel
from discord.ext import commands
from discord.ext.commands import guild_only, Context, CommandError, UserInputError, Greedy

from PyDrocsid.cog import Cog
from PyDrocsid.command import reply
from PyDrocsid.database import db, select, filter_by
from PyDrocsid.embeds import send_long_embed
from PyDrocsid.logger import get_logger
from PyDrocsid.multilock import MultiLock
from PyDrocsid.prefix import get_prefix
from PyDrocsid.settings import RoleSettings
from PyDrocsid.translations import t
from PyDrocsid.util import check_role_assignable, is_teamler
from .colors import Colors
from .models import DynamicVoiceChannel, DynamicVoiceGroup, RoleVoiceLink
from .permissions import VoiceChannelPermission
from ...contributor import Contributor
from ...pubsub import send_to_changelog

tg = t.g
t = t.voice_channel

logger = get_logger(__name__)


async def gather_roles(guild: Guild, channel_id: int) -> List[Role]:
    return [
        role
        async for link in await db.stream(select(RoleVoiceLink).filter_by(voice_channel=channel_id))
        if (role := guild.get_role(link.role)) is not None
    ]


async def get_group_channel(channel: VoiceChannel) -> Tuple[Optional[DynamicVoiceGroup], Optional[DynamicVoiceChannel]]:
    dyn_channel: DynamicVoiceChannel = await db.first(select(DynamicVoiceChannel).filter_by(channel_id=channel.id))

    channel_id = dyn_channel.group_id if dyn_channel is not None else channel.id
    group = await db.first(select(DynamicVoiceGroup).filter_by(channel_id=channel_id))

    return group, dyn_channel


class VoiceChannelCog(Cog, name="Voice Channels"):
    CONTRIBUTORS = [Contributor.Defelo, Contributor.Florian, Contributor.wolflu, Contributor.TNT2k]

    def __init__(self, team_roles: list[str]):
        super().__init__()

        self.team_roles: list[str] = team_roles
        self.channel_lock = MultiLock()
        self.group_lock = MultiLock()

    async def send_voice_msg(self, channel: TextChannel, public: bool, title: str, msg: str):
        messages: List[Message] = await channel.history(limit=1).flatten()
        if messages and messages[0].author == self.bot.user:
            embeds: List[Embed] = messages[0].embeds
            if len(embeds) == 1 and embeds[0].title == title and len(embeds[0].description + msg) <= 2000:
                embed = embeds[0]
                embed.description += "\n" + msg
                await messages[0].edit(embed=embed)
                return

        embed = Embed(title=title, colour=[Colors.private, Colors.public][public], description=msg)
        await channel.send(embed=embed)

    async def on_ready(self):
        guild: Guild = self.bot.guilds[0]
        logger.info(t.updating_voice_roles)
        linked_roles: Dict[Role, Set[VoiceChannel]] = {}
        async for link in await db.stream(select(RoleVoiceLink)):
            role = guild.get_role(link.role)
            voice = guild.get_channel(link.voice_channel)
            if role is None or voice is None:
                continue

            linked_roles.setdefault(role, set()).add(voice)

            group: Optional[DynamicVoiceGroup] = await db.get(DynamicVoiceGroup, channel_id=voice.id)
            if group is None:
                continue
            async for dyn_channel in await db.stream(select(DynamicVoiceChannel).filter_by(group_id=group.id)):
                channel: Optional[VoiceChannel] = guild.get_channel(dyn_channel.channel_id)
                if channel is not None:
                    linked_roles[role].add(channel)

        for role, channels in linked_roles.items():
            members = set()
            for channel in channels:
                members.update(channel.members)
            for member in members:
                if role not in member.roles:
                    await member.add_roles(role)
            for member in role.members:
                if member not in members:
                    await member.remove_roles(role)

        async for group in await db.stream(select(DynamicVoiceGroup)):
            channel: Optional[VoiceChannel] = guild.get_channel(group.channel_id)
            if channel is None:
                continue

            for member in channel.members:
                group, dyn_channel = await get_group_channel(channel)
                async with self.group_lock[group.id if group is not None else None]:
                    await self.member_join(member, channel, group, dyn_channel)

            async for dyn_channel in await db.stream(select(DynamicVoiceChannel).filter_by(group_id=group.id)):
                channel: Optional[VoiceChannel] = guild.get_channel(dyn_channel.channel_id)
                if channel is not None and all(member.bot for member in channel.members):
                    await channel.delete()
                    if (text_channel := self.bot.get_channel(dyn_channel.text_chat_id)) is not None:
                        await text_channel.delete()
                    await db.delete(dyn_channel)
            await self.update_dynamic_voice_group(group)

        logger.info(t.voice_init_done)

    async def get_dynamic_voice_channel(
        self,
        member: Member,
        owner_required: bool,
    ) -> Tuple[DynamicVoiceGroup, DynamicVoiceChannel, VoiceChannel, Optional[TextChannel]]:
        if member.voice is None or member.voice.channel is None:
            raise CommandError(t.not_in_private_voice)

        channel: VoiceChannel = member.voice.channel
        dyn_channel: DynamicVoiceChannel = await db.get(DynamicVoiceChannel, channel_id=channel.id)
        if dyn_channel is None:
            raise CommandError(t.not_in_private_voice)
        group: DynamicVoiceGroup = await db.get(DynamicVoiceGroup, id=dyn_channel.group_id)
        if group is None or group.public:
            raise CommandError(t.not_in_private_voice)

        if owner_required and dyn_channel.owner != member.id:
            if not await VoiceChannelPermission.private_owner.check_permissions(member):
                raise CommandError(t.private_voice_owner_required)

        voice_channel: VoiceChannel = self.bot.get_channel(dyn_channel.channel_id)
        text_chat: Optional[TextChannel] = self.bot.get_channel(dyn_channel.text_chat_id)

        return group, dyn_channel, voice_channel, text_chat

    async def member_join(
        self,
        member: Member,
        channel: VoiceChannel,
        group: Optional[DynamicVoiceGroup],
        dyn_channel: Optional[DynamicVoiceChannel],
    ):
        await member.add_roles(*await gather_roles(member.guild, channel.id))

        if dyn_channel is not None:
            if group is not None:
                await member.add_roles(*await gather_roles(member.guild, group.channel_id))

            text_chat: Optional[TextChannel] = self.bot.get_channel(dyn_channel.text_chat_id)
            if text_chat is not None:
                if not group.public:
                    await channel.set_permissions(member, read_messages=True, connect=True)
                await text_chat.set_permissions(member, read_messages=True)
                await self.send_voice_msg(text_chat, group.public, t.voice_channel, t.dyn_voice_joined(member.mention))
            return

        if group is None:
            return

        if member.bot:
            await member.move_to(None)
            return
        if channel.category is not None and len(channel.category.channels) >= 49 or len(channel.guild.channels) >= 499:
            await member.move_to(None)
            return

        guild: Guild = channel.guild
        number = await db.count(filter_by(DynamicVoiceChannel, group_id=group.id)) + 1
        chan: VoiceChannel = await channel.clone(name=group.name + " " + str(number))
        category: Union[CategoryChannel, Guild] = channel.category or guild
        overwrites = {
            guild.default_role: PermissionOverwrite(read_messages=False, connect=False),
            guild.me: PermissionOverwrite(read_messages=True, connect=True),
        }
        for role_name in self.team_roles:
            if (team_role := guild.get_role(await RoleSettings.get(guild, role_name))) is not None:
                overwrites[team_role] = PermissionOverwrite(read_messages=True, connect=True)
        text_chat: TextChannel = await category.create_text_channel(chan.name, overwrites=overwrites)

        await text_chat.set_permissions(member, read_messages=True)
        await chan.edit(position=channel.position + number)
        if not group.public:
            await chan.edit(overwrites={**overwrites, member: PermissionOverwrite(read_messages=True, connect=True)})
        try:
            await member.move_to(chan)
        except HTTPException:
            await chan.delete()
            await text_chat.delete()
            return
        else:
            await DynamicVoiceChannel.create(chan.id, group.id, text_chat.id, member.id)
        await self.update_dynamic_voice_group(group)
        if not group.public:
            await self.send_voice_msg(
                text_chat,
                group.public,
                t.private_dyn_voice_help_title,
                t.private_dyn_voice_help_content(prefix=await get_prefix()),
            )
        await self.send_voice_msg(text_chat, group.public, t.voice_channel, t.dyn_voice_created(member.mention))

    async def member_leave(
        self,
        member: Member,
        channel: VoiceChannel,
        group: Optional[DynamicVoiceGroup],
        dyn_channel: Optional[DynamicVoiceChannel],
    ):
        try:
            await member.remove_roles(*await gather_roles(member.guild, channel.id))
        except NotFound:  # member left the server
            pass

        if dyn_channel is None or group is None:
            return

        try:
            await member.remove_roles(*await gather_roles(member.guild, group.channel_id))
        except NotFound:  # member left the server
            pass

        text_chat: Optional[TextChannel] = self.bot.get_channel(dyn_channel.text_chat_id)
        if text_chat is not None:
            if group.public:
                await text_chat.set_permissions(member, overwrite=None)
            await self.send_voice_msg(text_chat, group.public, t.voice_channel, t.dyn_voice_left(member.mention))

        members: List[Member] = [member for member in channel.members if not member.bot]
        if not group.public and member.id == dyn_channel.owner and len(members) > 0:
            new_owner: Member = random.choice(members)  # noqa: S311
            await DynamicVoiceChannel.change_owner(dyn_channel.channel_id, new_owner.id)
            if text_chat is not None:
                await self.send_voice_msg(
                    text_chat,
                    group.public,
                    t.voice_channel,
                    t.private_voice_owner_changed(new_owner.mention),
                )

        if len(members) > 0:
            return

        await channel.delete()
        if text_chat is not None:
            await text_chat.delete()
        await db.delete(dyn_channel)
        await self.update_dynamic_voice_group(group)

    async def on_voice_state_update(self, member: Member, before: VoiceState, after: VoiceState):
        if before.channel == after.channel:
            return

        if (channel := before.channel) is not None:
            async with self.channel_lock[channel.id]:
                group, dyn_channel = await get_group_channel(channel)
                async with self.group_lock[group.id if group is not None else None]:
                    await self.member_leave(member, channel, group, dyn_channel)
        if (channel := after.channel) is not None:
            async with self.channel_lock[channel.id]:
                group, dyn_channel = await get_group_channel(channel)
                async with self.group_lock[group.id if group is not None else None]:
                    await self.member_join(member, channel, group, dyn_channel)

    async def update_dynamic_voice_group(self, group: DynamicVoiceGroup):
        base_channel: Optional[VoiceChannel] = self.bot.get_channel(group.channel_id)
        if base_channel is None:
            await db.delete(group)
            return

        channels = []
        async for dyn_channel in await db.stream(filter_by(DynamicVoiceChannel, group_id=group.id)):
            channel: Optional[VoiceChannel] = self.bot.get_channel(dyn_channel.channel_id)
            text_chat: Optional[TextChannel] = self.bot.get_channel(dyn_channel.text_chat_id)
            if channel is not None and text_chat is not None:
                channels.append((channel, text_chat))
            else:
                await db.delete(dyn_channel)

        channels.sort(key=lambda c: c[0].position)

        for i, (channel, text_chat) in enumerate(channels):
            name = f"{group.name} {i + 1}"
            await channel.edit(name=name, position=base_channel.position + i + 1)
            await text_chat.edit(name=name)
        await base_channel.edit(position=base_channel.position)

    @commands.group(aliases=["vc"])
    @guild_only()
    async def voice(self, ctx: Context):
        """
        manage voice channels
        """

        if ctx.invoked_subcommand is None:
            raise UserInputError

    @voice.group(name="dynamic", aliases=["dyn", "d"])
    @VoiceChannelPermission.dyn_read.check
    async def voice_dynamic(self, ctx: Context):
        """
        manage dynamic voice channels
        """

        if ctx.invoked_subcommand is None:
            raise UserInputError

    @voice_dynamic.command(name="list", aliases=["l", "?"])
    async def voice_dynamic_list(self, ctx: Context):
        """
        list dynamic voice channels
        """

        out = []
        async for group in await db.stream(select(DynamicVoiceGroup)):
            cnt = await db.count(filter_by(DynamicVoiceChannel, group_id=group.id))
            channel: Optional[VoiceChannel] = ctx.guild.get_channel(group.channel_id)
            if channel is None:
                await db.delete(group)
                continue
            e = ":globe_with_meridians:" if group.public else ":lock:"
            out.append(t.group_list_entry(e, group.name, cnt))

        embed = Embed(title=t.voice_channel, colour=Colors.Voice)
        if out:
            embed.description = "\n".join(sorted(out))
        else:
            embed.colour = Colors.error
            embed.description = t.no_dyn_group
        await send_long_embed(ctx, embed)

    @voice_dynamic.command(name="add", aliases=["a", "+"])
    @VoiceChannelPermission.dyn_write.check
    async def voice_dynamic_add(self, ctx: Context, visibility: str, *, voice_channel: VoiceChannel):
        """
        create a new dynamic voice channel group
        """

        if visibility.lower() not in ["public", "private"]:
            raise CommandError(t.error_visibility)
        public = visibility.lower() == "public"

        if await db.get(DynamicVoiceChannel, channel_id=voice_channel.id) is not None:
            raise CommandError(t.dyn_group_already_exists)
        if await db.get(DynamicVoiceGroup, channel_id=voice_channel.id) is not None:
            raise CommandError(t.dyn_group_already_exists)

        name: str = re.match(r"^(.*?) ?\d*$", voice_channel.name).group(1) or voice_channel.name
        await DynamicVoiceGroup.create(name, voice_channel.id, public)
        await voice_channel.edit(name=f"New {name}")
        embed = Embed(title=t.voice_channel, colour=Colors.Voice, description=t.dyn_group_created)
        await reply(ctx, embed=embed)
        await send_to_changelog(ctx.guild, t.log_dyn_group_created(name))

    @voice_dynamic.command(name="remove", aliases=["del", "d", "r", "-"])
    @VoiceChannelPermission.dyn_write.check
    async def voice_dynamic_remove(self, ctx: Context, *, voice_channel: VoiceChannel):
        """
        remove a dynamic voice channel group
        """

        group: DynamicVoiceGroup = await db.get(DynamicVoiceGroup, channel_id=voice_channel.id)
        if group is None:
            raise CommandError(t.dyn_group_not_found)

        await db.delete(group)
        async for dync in await db.stream(filter_by(DynamicVoiceChannel, group_id=group.id)):
            channel: Optional[VoiceChannel] = self.bot.get_channel(dync.channel_id)
            text_channel: Optional[TextChannel] = self.bot.get_channel(dync.text_chat_id)
            await db.delete(dync)
            if channel is not None:
                await channel.delete()
            if text_channel is not None:
                await text_channel.delete()

        await voice_channel.edit(name=group.name)
        embed = Embed(title=t.voice_channel, colour=Colors.Voice, description=t.dyn_group_removed)
        await reply(ctx, embed=embed)
        await send_to_changelog(ctx.guild, t.log_dyn_group_removed(group.name))

    @voice.command(name="info")
    async def voice_info(self, ctx: Context, *, channel: Optional[Union[VoiceChannel, Member]] = None):
        """
        list information of a voice channel
        """

        if not isinstance(channel, VoiceChannel):
            member = channel or ctx.author
            if not member.voice:
                if not channel:
                    raise CommandError(t.not_in_voice)
                if await is_teamler(ctx.author):
                    raise CommandError(t.user_not_in_voice)
                raise CommandError(tg.permission_denied)
            channel = member.voice.channel

        dyn_channel: Optional[DynamicVoiceChannel] = await db.get(DynamicVoiceChannel, channel_id=channel.id)
        if not dyn_channel:
            raise CommandError(t.dyn_group_not_found)
        group: DynamicVoiceGroup = await db.get(DynamicVoiceGroup, id=dyn_channel.group_id)

        if not channel.permissions_for(ctx.author).connect:
            raise CommandError(tg.permission_denied)

        visibility = t.public if group.public else t.private

        embed = Embed(
            title=t.voice_info,
            timestamp=channel.created_at,
            colour=[Colors.private, Colors.public][group.public],
        )
        embed.set_footer(text=t.voice_create_date)
        embed.add_field(name=t.voice_name, value=channel.name)
        embed.add_field(name=t.voice_visibility, value=visibility)
        if not group.public:
            embed.add_field(name=t.voice_owner, value=f"<@{dyn_channel.owner}>")

        out = []
        members = set(channel.members)
        for member in members:
            out.append(f":small_orange_diamond: {member.mention}")
        for member, overwrites in channel.overwrites.items():
            if not isinstance(member, Member) or not overwrites.connect or member == self.bot.user:
                continue
            if member not in members:
                out.append(f":small_blue_diamond: {member.mention}")
        name = t.voice_members
        if len(members) < len(out):
            name += f" ({len(members)}/{len(out)})"
        else:
            name += f" ({len(out)})"
        embed.add_field(name=name, value="\n".join(out), inline=False)

        await reply(ctx, embed=embed)

    @voice.command(name="close", aliases=["c"])
    async def voice_close(self, ctx: Context):
        """
        close a private voice channel
        """

        group, dyn_channel, voice_channel, text_channel = await self.get_dynamic_voice_channel(ctx.author, True)
        await db.delete(dyn_channel)

        roles = await gather_roles(voice_channel.guild, group.channel_id)
        for member in voice_channel.members:
            await member.remove_roles(*roles)

        if text_channel is not None:
            await text_channel.delete()
        await voice_channel.delete()
        await self.update_dynamic_voice_group(group)
        if text_channel != ctx.channel:
            embed = Embed(title=t.voice_channel, colour=Colors.Voice, description=t.private_voice_closed)
            await reply(ctx, embed=embed)

    @voice.command(name="invite", usage="<member> [members...]", aliases=["i", "add", "a", "+"])
    async def voice_invite(self, ctx: Context, members: Greedy[Member]):
        """
        invite a member (or multiple members) into a private voice channel
        """

        if not members:
            raise UserInputError

        group, _, voice_channel, text_channel = await self.get_dynamic_voice_channel(ctx.author, True)
        for member in set(members):
            if self.bot.user == member:
                raise CommandError(t.cannot_add_user(member.mention))

            await text_channel.set_permissions(member, read_messages=True)
            await voice_channel.set_permissions(member, read_messages=True, connect=True)

            user_embed = Embed(
                title=t.voice_channel,
                colour=Colors.Voice,
                timestamp=datetime.utcnow(),
                description=t.user_added_to_private_voice_dm(ctx.author.mention),
            )
            user_embed.set_footer(text=str(ctx.author), icon_url=ctx.author.avatar_url)

            if ctx.author.permissions_in(voice_channel).create_instant_invite:
                try:
                    user_embed.description += f"\n{await voice_channel.create_invite(unique=False)}"
                except Forbidden:
                    pass

            response = t.user_added_to_private_voice(member.mention)
            try:
                await member.send(embed=user_embed)
            except (Forbidden, HTTPException):
                response = t.user_added_to_private_voice_no_dm(member.mention)

            if text_channel is not None:
                await self.send_voice_msg(text_channel, group.public, t.voice_channel, response)
            if text_channel != ctx.channel:
                embed = Embed(
                    title=t.voice_channel,
                    colour=Colors.Voice,
                    description=t.user_added_to_private_voice_response,
                )
                await reply(ctx, embed=embed)

    @voice.command(name="remove", usage="<member> [members...]", aliases=["r", "kick", "k", "-"])
    async def voice_remove(self, ctx: Context, members: Greedy[Member]):
        """
        remove a member (or multiple members) from a private voice channel
        """

        if not members:
            raise UserInputError

        group, _, voice_channel, text_channel = await self.get_dynamic_voice_channel(ctx.author, True)
        for member in set(members):
            if member in (ctx.author, self.bot.user):
                raise CommandError(t.cannot_remove_member(member.mention))

            await text_channel.set_permissions(member, overwrite=None)
            await voice_channel.set_permissions(member, overwrite=None)
            if await is_teamler(member):
                raise CommandError(t.member_could_not_be_kicked(member.mention))

            if member.voice is not None and member.voice.channel == voice_channel:
                await member.move_to(None)
            if text_channel is not None:
                await self.send_voice_msg(
                    text_channel,
                    group.public,
                    t.voice_channel,
                    t.user_removed_from_private_voice(member.mention),
                )
            if text_channel != ctx.channel:
                embed = Embed(
                    title=t.voice_channel,
                    colour=Colors.Voice,
                    description=t.user_removed_from_private_voice_response,
                )
                await reply(ctx, embed=embed)

    @voice.command(name="owner", aliases=["o"])
    async def voice_owner(self, ctx: Context, member: Optional[Member]):
        """
        transfer ownership of a private voice channel
        """

        change = member is not None
        group, dyn_channel, voice_channel, text_channel = await self.get_dynamic_voice_channel(ctx.author, change)

        if not change:
            embed = Embed(
                title=t.voice_channel,
                colour=Colors.Voice,
                description=t.owner_of_private_voice(f"<@{dyn_channel.owner}>"),
            )
            await reply(ctx, embed=embed)
            return

        if member not in voice_channel.members:
            raise CommandError(t.user_not_in_this_channel)
        if member.bot:
            raise CommandError(t.bot_no_owner_transfer)

        await DynamicVoiceChannel.change_owner(dyn_channel.channel_id, member.id)
        if text_channel is not None:
            await self.send_voice_msg(
                text_channel,
                group.public,
                t.voice_channel,
                t.private_voice_owner_changed(member.mention),
            )
        if text_channel != ctx.channel:
            embed = Embed(
                title=t.voice_channel,
                colour=Colors.Voice,
                description=t.private_voice_owner_changed_response,
            )
            await reply(ctx, embed=embed)

    @voice.group(name="link", aliases=["l"])
    @VoiceChannelPermission.link_read.check
    async def voice_link(self, ctx: Context):
        """
        manage links between voice channels and roles
        """

        if ctx.invoked_subcommand is None:
            raise UserInputError

    @voice_link.command(name="list", aliases=["l", "?"])
    async def voice_link_list(self, ctx: Context):
        """
        list all links between voice channels and roles
        """

        out = []
        guild: Guild = ctx.guild
        async for link in await db.stream(select(RoleVoiceLink)):
            role: Optional[Role] = guild.get_role(link.role)
            voice: Optional[VoiceChannel] = guild.get_channel(link.voice_channel)
            if role is None or voice is None:
                await db.delete(link)
            else:
                out.append(f"`{voice}` (`{voice.id}`) -> <@&{role.id}> (`{role.id}`)")

        embed = Embed(title=t.voice_channel, colour=Colors.Voice)
        if out:
            embed.description = "\n".join(out)
        else:
            embed.colour = Colors.error
            embed.description = t.no_links_created
        await send_long_embed(ctx, embed)

    @voice_link.command(name="add", aliases=["a", "+"])
    @VoiceChannelPermission.link_write.check
    async def voice_link_add(self, ctx: Context, channel: VoiceChannel, *, role: Role):
        """
        link a voice channel with a role
        """

        if await db.get(DynamicVoiceChannel, channel_id=channel.id) is not None:
            raise CommandError(t.link_on_dynamic_channel_not_created)
        if await db.get(RoleVoiceLink, role=role.id, voice_channel=channel.id) is not None:
            raise CommandError(t.link_already_exists)

        check_role_assignable(role)

        await RoleVoiceLink.create(role.id, channel.id)
        for member in channel.members:
            await member.add_roles(role)

        group: Optional[DynamicVoiceGroup] = await db.get(DynamicVoiceGroup, channel_id=channel.id)
        if group is not None:
            async for dyn_channel in await db.stream(filter_by(DynamicVoiceChannel, group_id=group.id)):
                dchannel: Optional[VoiceChannel] = self.bot.get_channel(dyn_channel.channel_id)
                if dchannel is not None:
                    for member in dchannel.members:
                        await member.add_roles(role)

        embed = Embed(
            title=t.voice_channel,
            colour=Colors.Voice,
            description=t.link_created(channel, role.id),
        )
        await reply(ctx, embed=embed)
        await send_to_changelog(ctx.guild, t.log_link_created(channel, role))

    @voice_link.command(name="remove", aliases=["del", "r", "d", "-"])
    @VoiceChannelPermission.link_write.check
    async def voice_link_remove(self, ctx: Context, channel: VoiceChannel, *, role: Role):
        """
        delete the link between a voice channel and a role
        """

        if (link := await db.get(RoleVoiceLink, role=role.id, voice_channel=channel.id)) is None:
            raise CommandError(t.link_not_found)

        await db.delete(link)
        for member in channel.members:
            await member.remove_roles(role)

        group: Optional[DynamicVoiceGroup] = await db.get(DynamicVoiceGroup, channel_id=channel.id)
        if group is not None:
            async for dyn_channel in await db.stream(filter_by(DynamicVoiceChannel, group_id=group.id)):
                dchannel: Optional[VoiceChannel] = self.bot.get_channel(dyn_channel.channel_id)
                if dchannel is not None:
                    for member in dchannel.members:
                        await member.remove_roles(role)

        embed = Embed(title=t.voice_channel, colour=Colors.Voice, description=t.link_deleted)
        await reply(ctx, embed=embed)
        await send_to_changelog(ctx.guild, t.log_link_deleted(channel, role))
