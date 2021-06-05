import random
from datetime import datetime
from pathlib import Path
from typing import Optional, Union

import yaml
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
)
from discord.ext import commands
from discord.ext.commands import guild_only, Context, UserInputError, CommandError

from PyDrocsid.cog import Cog
from PyDrocsid.command import docs, reply
from PyDrocsid.database import filter_by, db, select, delete
from PyDrocsid.embeds import send_long_embed
from PyDrocsid.emojis import name_to_emoji
from PyDrocsid.settings import RoleSettings
from PyDrocsid.translations import t
from PyDrocsid.util import send_editable_log
from .colors import Colors
from .models import DynGroup, DynChannel, DynChannelMember
from .permissions import VoiceChannelPermission
from ...contributor import Contributor
from ...pubsub import send_to_changelog

tg = t.g
t = t.voice_channel


def merge_permission_overwrites(
    overwrites: dict[Union[Member, Role], PermissionOverwrite],
    *args: tuple[Union[Member, Role], PermissionOverwrite],
) -> dict[Union[Member, Role], PermissionOverwrite]:
    out = {k: PermissionOverwrite.from_pair(*v.pair()) for k, v in overwrites.items()}
    for k, v in args:
        out.setdefault(k, PermissionOverwrite()).update(**{p: q for p, q in v if v is not None})
    return out


class VoiceChannelCog(Cog, name="Voice Channels"):
    CONTRIBUTORS = [Contributor.Defelo, Contributor.Florian, Contributor.wolflu, Contributor.TNT2k]

    def __init__(self, team_roles: list[str]):
        self.team_roles: list[str] = team_roles
        self._owners: dict[int, Member] = {}

        with Path(__file__).parent.joinpath("names.yml").open() as file:
            self.names: list[str] = yaml.safe_load(file)

    async def get_channel_name(self) -> str:
        return random.choice(self.names)  # noqa: S311

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
        text_channel: Optional[TextChannel] = self.bot.get_channel(channel.text_id)
        if not text_channel:
            return

        color = int([Colors.unlocked, Colors.locked][channel.locked])
        await send_editable_log(
            text_channel,
            title,
            "",
            datetime.utcnow().strftime("%d.%m.%Y %H:%M:%S"),
            msg,
            colour=color,
            force_new_embed=force_new_embed,
            force_new_field=True,
        )

    async def fix_owner(self, channel: DynChannel) -> Optional[Member]:
        voice_channel: VoiceChannel = self.bot.get_channel(channel.channel_id)

        in_voice = {m.id for m in voice_channel.members}
        for m in channel.members:
            if m.member_id in in_voice:
                channel.owner_id = m.id
                return await self.update_owner(channel, voice_channel.guild.get_member(m.member_id))

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
        if await VoiceChannelPermission.private_owner.check_permissions(member):
            return

        if await self.get_owner(channel) == member:
            return

        raise CommandError(t.private_voice_owner_required)

    async def member_join(self, member: Member, voice_channel: VoiceChannel):
        guild: Guild = voice_channel.guild
        category: Union[CategoryChannel, Guild] = voice_channel.category or guild

        channel: Optional[DynChannel] = await db.get(
            DynChannel,
            DynChannel.group,
            DynGroup.channels,
            DynChannel.members,
            channel_id=voice_channel.id,
        )
        if not channel:
            return

        text_channel: Optional[TextChannel] = self.bot.get_channel(channel.text_id)
        if not text_channel:
            overwrites = {
                guild.default_role: PermissionOverwrite(read_messages=False, connect=False),
                guild.me: PermissionOverwrite(read_messages=True, manage_channels=True),
            }
            for role_name in self.team_roles:
                if (team_role := guild.get_role(await RoleSettings.get(role_name))) is not None:
                    overwrites[team_role] = PermissionOverwrite(read_messages=True)
            text_channel = await category.create_text_channel(voice_channel.name, overwrites=overwrites)
            channel.text_id = text_channel.id
            await self.send_voice_msg(channel, t.voice_channel, t.dyn_voice_created(member.mention))

        await text_channel.set_permissions(member, overwrite=PermissionOverwrite(read_messages=True))
        await self.send_voice_msg(channel, t.voice_channel, t.dyn_voice_joined(member.mention))

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
            channel.owner_id = channel_member.id
            update_owner = True
        if update_owner or channel.owner_override == member.id:
            await self.update_owner(channel, await self.fetch_owner(channel))

        if all(c.members for chnl in channel.group.channels if (c := self.bot.get_channel(chnl.channel_id))):
            overwrites = voice_channel.overwrites
            if channel.locked:
                overwrites = merge_permission_overwrites(
                    {k: v for k, v in overwrites.items() if not isinstance(k, Member) or k == guild.me},
                    (guild.default_role, PermissionOverwrite(view_channel=True, connect=True)),
                )
            new_channel = await category.create_voice_channel(await self.get_channel_name(), overwrites=overwrites)
            await DynChannel.create(new_channel.id, channel.group_id)

    async def member_leave(self, member: Member, voice_channel: VoiceChannel):
        channel: Optional[DynChannel] = await db.get(
            DynChannel,
            DynChannel.group,
            DynGroup.channels,
            DynChannel.members,
            channel_id=voice_channel.id,
        )
        if not channel:
            return

        text_channel: Optional[TextChannel] = self.bot.get_channel(channel.text_id)

        if text_channel and not channel.locked:
            await text_channel.set_permissions(member, overwrite=None)
        await self.send_voice_msg(channel, t.voice_channel, t.dyn_voice_left(member.mention))

        owner: Optional[DynChannelMember] = await db.get(DynChannelMember, id=channel.owner_id)
        if owner and owner.member_id == member.id or channel.owner_override == member.id:
            await self.fix_owner(channel)

        if voice_channel.members:
            return

        if text_channel:
            channel.owner_id = None
            channel.owner_override = None
            await db.exec(delete(DynChannelMember).filter_by(channel_id=voice_channel.id))
            channel.members.clear()
            await text_channel.delete()

        if not all(
            c.members
            for chnl in channel.group.channels
            if chnl.channel_id != channel.channel_id and (c := self.bot.get_channel(chnl.channel_id))
        ):
            await voice_channel.delete()
            await db.delete(channel)

    async def on_voice_state_update(self, member: Member, before: VoiceState, after: VoiceState):
        if before.channel == after.channel:
            return

        if (channel := before.channel) is not None:
            await self.member_leave(member, channel)
        if (channel := after.channel) is not None:
            await self.member_join(member, channel)

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
            channels: list[tuple[VoiceChannel, Optional[TextChannel]]] = []
            for channel in group.channels:
                voice_channel: Optional[VoiceChannel] = ctx.guild.get_channel(channel.channel_id)
                text_channel: Optional[TextChannel] = ctx.guild.get_channel(channel.text_id)
                if not voice_channel:
                    await db.delete(channel)
                    continue
                channels.append((voice_channel, text_channel))

            if not channels:
                await db.delete(group)
                continue

            embed.add_field(
                name=t.cnt_channels(cnt=len(channels)),
                value="\n".join(
                    f":small_orange_diamond: {vc.mention} {txt.mention if txt else ''}" for vc, txt in channels
                ),
            )

        if not embed.fields:
            embed.colour = Colors.error
            embed.description = t.no_dyn_group
        await send_long_embed(ctx, embed, paginate=True)

    @voice_dynamic.command(name="add", aliases=["a", "+"])
    @VoiceChannelPermission.dyn_write.check
    @docs(t.commands.voice_dynamic_add)
    async def voice_dynamic_add(self, ctx: Context, *, voice_channel: VoiceChannel):
        if await db.exists(filter_by(DynChannel, channel_id=voice_channel.id)):
            raise CommandError(t.dyn_group_already_exists)

        await voice_channel.edit(name=await self.get_channel_name())
        await DynGroup.create(voice_channel.id)
        embed = Embed(title=t.voice_channel, colour=Colors.Voice, description=t.dyn_group_created)
        await reply(ctx, embed=embed)
        await send_to_changelog(ctx.guild, t.log_dyn_group_created)

    @voice_dynamic.command(name="remove", aliases=["del", "d", "r", "-"])
    @VoiceChannelPermission.dyn_write.check
    @docs(t.commands.voice_dynamic_remove)
    async def voice_dynamic_remove(self, ctx: Context, *, voice_channel: VoiceChannel):
        channel: Optional[DynChannel] = await db.get(
            DynChannel,
            DynChannel.group,
            DynGroup.channels,
            DynChannel.members,
            channel_id=voice_channel.id,
        )
        if not channel:
            raise CommandError(t.dyn_group_not_found)

        for c in channel.group.channels:
            if (x := self.bot.get_channel(c.channel_id)) and c.channel_id != voice_channel.id:
                await x.delete()
            if x := self.bot.get_channel(c.text_id):
                await x.delete()

        await db.delete(channel.group)
        embed = Embed(title=t.voice_channel, colour=Colors.Voice, description=t.dyn_group_removed)
        await reply(ctx, embed=embed)
        await send_to_changelog(ctx.guild, t.log_dyn_group_removed)

    @voice.command(name="owner", aliases=["o"])
    @docs(t.commands.voice_owner)
    async def voice_owner(self, ctx: Context, member: Member):
        if ctx.author.voice is None or ctx.author.voice.channel is None:
            raise CommandError(t.not_in_voice)

        voice_channel: VoiceChannel = ctx.author.voice.channel
        channel: Optional[DynChannel] = await db.get(DynChannel, channel_id=voice_channel.id)
        if not channel:
            raise CommandError(t.not_in_voice)

        await self.check_authorization(channel, ctx.author)

        if member not in voice_channel.members:
            raise CommandError(t.user_not_in_this_channel)
        if member.bot:
            raise CommandError(t.bot_no_owner_transfer)

        if await self.get_owner(channel) == member:
            raise CommandError(t.already_owner(member.mention))

        channel.owner_override = member.id
        await self.update_owner(channel, member)
        await ctx.message.add_reaction(name_to_emoji["white_check_mark"])
