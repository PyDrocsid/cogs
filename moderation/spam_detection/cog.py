import time
from datetime import timedelta

from discord import Embed, Forbidden, HTTPException, Member, VoiceState
from discord.ext import commands
from discord.ext.commands import Context, UserInputError, guild_only

from PyDrocsid.cog import Cog
from PyDrocsid.command import CommandError, docs, reply
from PyDrocsid.redis import redis
from PyDrocsid.translations import t

from .colors import Colors
from .permissions import SpamDetectionPermission
from .settings import SpamDetectionSettings
from ...contributor import Contributor
from ...pubsub import send_alert, send_to_changelog


tg = t.g
t = t.spam_detection


async def _send_changes(ctx: Context, amount: int, change_type: str, description):
    description = description(amount, change_type) if amount > 0 else t.hop_detection_disabled(change_type)
    embed = Embed(title=t.channel_hopping, description=description, colour=Colors.SpamDetection)

    await reply(ctx, embed=embed)
    await send_to_changelog(ctx.guild, description)


class SpamDetectionCog(Cog, name="Spam Detection"):
    CONTRIBUTORS = [Contributor.ce_phox, Contributor.Defelo, Contributor.NekoFanatic]

    async def on_voice_state_update(self, member: Member, before: VoiceState, after: VoiceState):
        """
        Checks for channel-hopping
        """

        if await SpamDetectionPermission.bypass.check_permissions(member):
            return

        if before.channel == after.channel:
            return

        alert: int = await SpamDetectionSettings.max_hops_alert.get()
        warning: int = await SpamDetectionSettings.max_hops_warning.get()
        mute: int = await SpamDetectionSettings.max_hops_temp_mute.get()
        duration: int = await SpamDetectionSettings.temp_mute_duration.get()
        if alert == 0 and warning == 0 and mute == 0:
            return

        ts = time.time()
        await redis.zremrangebyscore(key := f"channel_hops:user={member.id}", min="-inf", max=ts - 60)
        await redis.zadd(key, {str(ts): ts})
        await redis.expire(key, 60)
        hops: int = await redis.zcount(key, "-inf", "inf")

        if hops >= alert > 0 and not await redis.exists(key := f"channel_hops_alert_sent:user={member.id}"):
            await redis.setex(key, 10, 1)
            embed = Embed(
                title=t.channel_hopping, color=Colors.SpamDetection, description=t.hops_in_last_minute(cnt=hops)
            )
            embed.add_field(name=tg.member, value=member.mention)
            embed.add_field(name=t.member_id, value=str(member.id))
            embed.set_author(name=str(member), icon_url=member.display_avatar.url)
            if after.channel:
                embed.add_field(name=t.current_channel, value=after.channel.name)
            await send_alert(member.guild, embed)

        if hops >= warning > 0 and not await redis.exists(key := f"channel_hops_warning_sent:user={member.id}"):
            await redis.setex(key, 10, 1)
            embed = Embed(title=t.channel_hopping_warning_sent, color=Colors.SpamDetection)
            try:
                await member.send(embed=embed)
            except (HTTPException, Forbidden):
                pass

        if hops >= mute > 0 and not await redis.exists(key := f"channel_hops_mute:user={member.id}"):
            try:
                await member.timeout_for(duration=timedelta(seconds=duration), reason=t.reason)
            except Forbidden:
                await send_alert(member.guild, t.cant_mute(member.mention, member.id))
            await redis.setex(key, 10, 1)

    @commands.group(aliases=["spam", "sd"])
    @SpamDetectionPermission.read.check
    @guild_only()
    @docs(t.commands.spam_detection)
    async def spam_detection(self, ctx: Context):

        if ctx.subcommand_passed is not None:
            if ctx.invoked_subcommand is None:
                raise UserInputError
            return

        embed = Embed(title=t.spam_detection, color=Colors.SpamDetection)

        if (alert := await SpamDetectionSettings.max_hops_alert.get()) <= 0:
            embed.add_field(name=t.channel_hopping_alert, value=tg.disabled, inline=False)
        else:
            embed.add_field(name=t.channel_hopping_alert, value=t.max_x_hops(cnt=alert), inline=False)
        if (dm_warning := await SpamDetectionSettings.max_hops_warning.get()) <= 0:
            embed.add_field(name=t.channel_hopping_warning, value=tg.disabled, inline=False)
        else:
            embed.add_field(name=t.channel_hopping_warning, value=t.max_x_hops(cnt=dm_warning), inline=False)
        if (mute_hops := await SpamDetectionSettings.max_hops_temp_mute.get()) <= 0:
            embed.add_field(name=t.channel_hopping_mute, value=tg.disabled, inline=False)
        else:
            embed.add_field(name=t.channel_hopping_mute, value=t.max_x_hops(cnt=mute_hops), inline=False)
        mute_duration = await SpamDetectionSettings.temp_mute_duration.get()
        embed.add_field(name=t.mute_duration, value=t.seconds_muted(cnt=mute_duration), inline=False)

        await reply(ctx, embed=embed)

    @spam_detection.group(name="channel_hopping", aliases=["ch"])
    @SpamDetectionPermission.write.check
    @docs(t.commands.channel_hopping)
    async def channel_hopping(self, ctx: Context):

        if not ctx.subcommand_passed or not ctx.invoked_subcommand:
            raise UserInputError

    @channel_hopping.command(name="alert", aliases=["a"])
    @docs(t.commands.alert)
    async def alert(self, ctx: Context, amount: int):

        await SpamDetectionSettings.max_hops_alert.set(max(amount, 0))
        await _send_changes(ctx, amount, t.change_types.alerts, t.hop_amount_set)

    @channel_hopping.command(name="warning", aliases=["warn"])
    @docs(t.commands.warning)
    async def warning(self, ctx: Context, amount: int):

        await SpamDetectionSettings.max_hops_warning.set(max(amount, 0))
        await _send_changes(ctx, amount, t.change_types.warnings, t.hop_amount_set)

    @channel_hopping.group(name="mute", aliases=["m"])
    @docs(t.commands.temp_mute)
    async def mute(self, ctx: Context):

        if not ctx.subcommand_passed or not ctx.invoked_subcommand:
            raise UserInputError

    @mute.command(name="hops", aliases=["h"])
    @docs(t.commands.temp_mute_hops)
    async def hops(self, ctx: Context, amount: int):

        await SpamDetectionSettings.max_hops_temp_mute.set(max(amount, 0))
        await _send_changes(ctx, amount, t.change_types.mutes, t.hop_amount_set)

    @mute.command(name="duration", aliases=["d"])
    @docs(t.commands.temp_mute_duration)
    async def duration(self, ctx: Context, seconds: int):
        if seconds not in range(1, 28 * 24 * 60 * 60):
            raise CommandError(tg.invalid_duration)

        await SpamDetectionSettings.temp_mute_duration.set(seconds)
        await _send_changes(ctx, seconds, t.change_types.mutes, t.mute_time_set)
