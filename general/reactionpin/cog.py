from typing import Optional

from discord import TextChannel, Message, Guild, Member, MessageType, HTTPException, PartialEmoji, Embed
from discord.ext import commands
from discord.ext.commands import Context, guild_only, CommandError, UserInputError

from PyDrocsid.cog import Cog
from PyDrocsid.command import make_error, reply
from PyDrocsid.database import db, select
from PyDrocsid.emojis import name_to_emoji
from PyDrocsid.events import StopEventHandling
from PyDrocsid.settings import RoleSettings
from PyDrocsid.translations import t
from .colors import Colors
from .models import ReactionPinChannel
from .permissions import ReactionPinPermission
from .settings import ReactionPinSettings
from ...contributor import Contributor
from ...pubsub import send_to_changelog

tg = t.g
t = t.reactionpin

EMOJI = name_to_emoji["pushpin"]


class ReactionPinCog(Cog, name="ReactionPin"):
    CONTRIBUTORS = [Contributor.Defelo, Contributor.wolflu]

    async def on_raw_reaction_add(self, message: Message, emoji: PartialEmoji, member: Member):
        if str(emoji) != EMOJI or member.bot or message.guild is None:
            return

        access: bool = await ReactionPinPermission.pin.check_permissions(member)
        if not (await db.exists(select(ReactionPinChannel).filter_by(channel=message.channel.id)) or access):
            return

        blocked_role = await RoleSettings.get("mute")
        if access or (member == message.author and all(r.id != blocked_role for r in member.roles)):
            if message.type != MessageType.default:
                await message.remove_reaction(emoji, member)
                await message.channel.send(embed=make_error(t.msg_not_pinned_system))
                raise StopEventHandling
            try:
                await message.pin()
            except HTTPException:
                await message.remove_reaction(emoji, member)
                await message.channel.send(embed=make_error(t.msg_not_pinned_limit))
        else:
            await message.remove_reaction(emoji, member)

        raise StopEventHandling

    async def on_raw_reaction_remove(self, message: Message, emoji: PartialEmoji, member: Member):
        if str(emoji) != EMOJI or member.bot or message.guild is None:
            return

        access: bool = await ReactionPinPermission.pin.check_permissions(member)
        is_reactionpin_channel = await db.exists(select(ReactionPinChannel).filter_by(channel=message.channel.id))
        if message.pinned and (access or (is_reactionpin_channel and member == message.author)):
            await message.unpin()
            raise StopEventHandling

    async def on_raw_reaction_clear(self, message: Message):
        if message.guild is not None and message.pinned:
            await message.unpin()
        raise StopEventHandling

    async def on_self_message(self, message: Message):
        if message.guild is None:
            return

        pin_messages_enabled = await ReactionPinSettings.keep_pin_message.get()
        if not pin_messages_enabled and message.type == MessageType.pins_add:
            await message.delete()
            raise StopEventHandling

    @commands.group(aliases=["rp"])
    @ReactionPinPermission.read.check
    @guild_only()
    async def reactionpin(self, ctx: Context):
        """
        manage ReactionPin
        """

        if ctx.subcommand_passed is not None:
            if ctx.invoked_subcommand is None:
                raise UserInputError
            return

        embed = Embed(title=t.reactionpin, colour=Colors.ReactionPin)

        if await ReactionPinSettings.keep_pin_message.get():
            embed.add_field(name=t.pin_messages, value=tg.enabled, inline=False)
        else:
            embed.add_field(name=t.pin_messages, value=tg.disabled, inline=False)

        out = []
        guild: Guild = ctx.guild
        async for channel in await db.stream(select(ReactionPinChannel)):
            text_channel: Optional[TextChannel] = guild.get_channel(channel.channel)
            if text_channel is None:
                continue
            out.append(f":small_orange_diamond: {text_channel.mention}")
        if out:
            embed.add_field(name=t.whitelisted_channels, value="\n".join(out))
        else:
            embed.colour = Colors.error
            embed.add_field(name=t.whitelisted_channels, value=t.no_whitelisted_channels)

        await reply(ctx, embed=embed)

    @reactionpin.command(name="add", aliases=["a", "+"])
    @ReactionPinPermission.write.check
    async def reactionpin_add(self, ctx: Context, channel: TextChannel):
        """
        add channel to whitelist
        """

        if await db.exists(select(ReactionPinChannel).filter_by(channel=channel.id)):
            raise CommandError(t.channel_already_whitelisted)

        await ReactionPinChannel.create(channel.id)
        embed = Embed(title=t.reactionpin, colour=Colors.ReactionPin, description=t.channel_whitelisted)
        await reply(ctx, embed=embed)
        await send_to_changelog(ctx.guild, t.log_channel_whitelisted_rp(channel.mention))

    @reactionpin.command(name="remove", aliases=["del", "r", "d", "-"])
    @ReactionPinPermission.write.check
    async def reactionpin_remove(self, ctx: Context, channel: TextChannel):
        """
        remove channel from whitelist
        """

        if not (row := await db.first(select(ReactionPinChannel).filter_by(channel=channel.id))):
            raise CommandError(t.channel_not_whitelisted)

        await db.delete(row)
        embed = Embed(title=t.reactionpin, colour=Colors.ReactionPin, description=t.channel_removed)
        await reply(ctx, embed=embed)
        await send_to_changelog(ctx.guild, t.log_channel_removed_rp(channel.mention))

    @reactionpin.command(name="pin_message", aliases=["pm"])
    @ReactionPinPermission.write.check
    async def reactionpin_pin_message(self, ctx: Context, enabled: bool):
        """
        enable/disable "pinned a message" notification
        """

        embed = Embed(title=t.reactionpin, colour=Colors.ReactionPin)
        await ReactionPinSettings.keep_pin_message.set(enabled)
        if enabled:
            embed.description = t.pin_messages_now_enabled
            await send_to_changelog(ctx.guild, t.log_pin_messages_now_enabled)
        else:
            embed.description = t.pin_messages_now_disabled
            await send_to_changelog(ctx.guild, t.log_pin_messages_now_disabled)
        await reply(ctx, embed=embed)
