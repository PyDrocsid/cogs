import random
from pathlib import Path
from typing import Optional, Union

import yaml
from PyDrocsid.settings import RoleSettings
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
    Message,
)
from discord.ext import commands
from discord.ext.commands import guild_only, Context, UserInputError, CommandError

from PyDrocsid.cog import Cog
from PyDrocsid.command import docs, reply
from PyDrocsid.database import filter_by, db, select
from PyDrocsid.embeds import send_long_embed, EmbedLimits
from PyDrocsid.translations import t
from .colors import Colors
from .models import DynGroup, DynChannel
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

        with Path(__file__).parent.joinpath("names.yml").open() as file:
            self.names: list[str] = yaml.safe_load(file)

    async def get_channel_name(self) -> str:
        return random.choice(self.names)  # noqa: S311

    async def send_voice_msg(self, channel: DynChannel, title: str, msg: str):
        text_channel: Optional[TextChannel] = self.bot.get_channel(channel.text_id)
        if not text_channel:
            return

        color = int([Colors.unlocked, Colors.locked][channel.locked])
        messages: list[Message] = await text_channel.history(limit=1).flatten()
        if messages and messages[0].author == self.bot.user and len(messages[0].embeds) == 1:
            e: Embed = messages[0].embeds[0]
            desc_ok = len(e.description) + len(msg) + 1 <= EmbedLimits.DESCRIPTION
            total_ok = len(e) + len(msg) + 1 <= EmbedLimits.TOTAL
            if e.title == title and (color == e.colour or color == e.colour.value) and desc_ok and total_ok:
                e.description += "\n" + msg
                await messages[0].edit(embed=e)
                return

        embed = Embed(title=title, color=color, description=msg)
        await text_channel.send(embed=embed)

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

        if voice_channel.members:
            return

        if text_channel:
            await text_channel.delete()

        if not all(
            c.members
            for chnl in channel.group.channels
            if chnl.channel_id != channel.channel_id and (c := self.bot.get_channel(chnl.channel_id))
        ):
            await voice_channel.delete()

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
