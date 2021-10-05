from PyDrocsid.cog import Cog
from PyDrocsid.redis import redis

from discord import Embed, Guild, User, Member, Forbidden, Message, Channel

from discord.ext import commands
from discord.ext.commands import Context, UserInputError, guild_only, CommandError

from discord.utils import snowflake_time, time_snowflake

from datetime import datetime

from typing import Union, Optional

from PyDrocsid.command import reply
from PyDrocsid.database import db, filter_by
from PyDrocsid.translations import t
from PyDrocsid.emojis import name_to_emoji

from .colors import Colors
from .permission import AntiRaidPermission
from .settings import AntiRaidSettings
from ..mod.models import Kick
from ..mod import ModCog
from ...information.user_info import UserInfoCog
from ...contributor import Contributor
from ...pubsub import send_to_changelog
from ...information.user_info.models import Join


tg = t.g
t = t.antiraid


async def send_to_changelog_antiraid(
    guild: Guild,
    executing_teamler: Union[Member, User],
    color: int,
    title: str,
    message: str,
):
    embed = Embed(title=title, color=color, timestamp=datetime.utcnow(), description=message)
    embed.set_footer(text=str(executing_teamler), icon_url=executing_teamler.avatar_url)

    await send_to_changelog(guild, embed)

async def send_alert(guild: Guild, text=None, embed=None):
    alert_channel: Channel = guild.get_channel(AntiRaidSettings.alert_channel.get())
    
    if not alert_channel:
        return
    
    return await alert_channel.send(content=text, embed=embed)

async def cleanup_redis(current_time: datetime):
    key = "antiraid:"
    
    p = redit.pipeline()
    if await redis.exists(key + "recent_joins"):
        p.zremrangebyrank(key + "recent_joins", 0, current_time.timestamp() - await AntiRaidSettings.timespan.get())
    if await redis.exists(key + "raid_alerts":):
        p.zremrangebyrank(key + "raid_alerts", 0, current_time.timestamp() - await AntiRaidSettings.keep_alerts.get())
    await p.execute()


class AntiRaidCog(Cog, name="AntiRaid"):
    CONTRIBUTORS = [Contributor.Anorak]
    DEPENDENCIES = [UserInfoCog, ModCog]

    def __init__(self):
        super().__init__()

    async def on_member_join(self, member):
        await cleanup_redis()

        if member.bot:
            return

        key = "antiraid:"

        if await redis.exists(key + "joinkick_enabled"):
            user_embed = Embed(title=t.ongoing_raid_title, description=t.ongoing_raid_message, color=Colors.error)

            try:
                await member.send(embed=user_embed)
            except Forbidden:
                pass
            await member.kick()
            await Kick.create(member.id, str(member), None, t.kicked_joinkick)
            # TODO Maybe save teamler who enabled autokick
            # TODO maybe send a message to changelog
        elif await redis.zscore(key + "recent_joins", member.id) is not None:
            await redis.zadd(key + "recent_joins", member.joined_at.timestamp(), member.id)

            if await redis.zcard(key + "recent_joins") > await AntiRaidSettings.threshold.get() and not await redis.exists(key + "alert_cooldown"):
                embed = Embed(title=t.antiraid, description=t.possible_raid, color=Colors.error)
                alert_message: Message = await send_alert(ctx.guild, embed=embed)
                # TODO Custom emoji?
                # TODO Set values in translations
                await alert_message.add_reaction(name_to_emoji["closed_lock"])
    
                p = redis.pipeline()
                p.setex(key + "alert_cooldown", await AntiRaidSettings.alert_cooldown.get(), 1)
                p.zadd(key + "raid_alerts", alert_message.created_at.timestamp(), alert_message.id)
                await p.execute()

    # TODO Add on_raw_reaction_add

    @commands.group(aliases=["ard"])
    @AntiRaidPermission.read.check
    @guild_only()
    async def antiraid(self, ctx: Context):
        """
        Manage the anti raid system
        """

        if ctx.subcommand_passed is not None:
            if ctx.invoked_subcommand is None:
                raise UserInputError
            return

        embed = Embed(title=t.antiraid, color=Colors.AntiRaid)

        embed.add_field(name=t.timespan, value=str(await AntiRaidSettings.timespan.get()), inline=False)
        embed.add_field(name=t.threshold, value=str(await AntiRaidSettings.threshold.get()), inline=False)
        embed.add_field(name=t.alert_cooldown, value=str(await AntiRaidSettings.alert_cooldown.get()), inline=False)

        if self.joinkick_enabled:
            embed.add_field(name=t.joinkick, value=tg.enabled, inline=False)
        else:
            embed.add_field(name=t.joinkick, value=tg.disabled, inline=False)

        await reply(ctx, embed=embed)

    @antiraid.command(aliases=["tk"])
    @AntiRaidPermission.timekick.check
    async def timekick(self, ctx: Context, snowflake: int):
        """
        Kick all users who joined since the snowflake's creation time
        """

        try:
            time = snowflake_time(snowflake)
        except (OverflowError, ValueError):
            raise CommandError(t.invalid_snowflake)

        if time > datetime.utcnow():
            raise CommandError(t.invalid_time)

        user_embed = Embed(title=t.ongoing_raid_title, description=t.ongoing_raid_message, color=Colors.error)

        async for join in await db.stream(
            filter_by(Join).filter(Join.timestamp >= time).distinct(Join.member).group_by(Join.member),
        ):
            if (member := ctx.guild.get_member(join.member)) and not member.bot:
                try:
                    await member.send(embed=user_embed)
                except Forbidden:
                    pass
                await member.kick()
                await Kick.create(member.id, str(member), ctx.author.id, t.kicked_timekick)

        embed = Embed(
            title=t.timekick,
            description=t.timekick_done(time.strftime("%d.%m.%Y %H:%M:%S")),
            color=Colors.AntiRaid,
        )
        await reply(ctx, embed=embed)
        await send_to_changelog_antiraid(
            ctx.guild,
            ctx.author,
            Colors.AntiRaid,
            t.antiraid,
            t.timekick_done(time.strftime("%d.%m.%Y %H:%M:%S")),
        )

    @antiraid.group(aliases=["jk"])
    @AntiRaidPermission.joinkick.check
    async def joinkick(self, ctx: Context):
        """
        Instantly kick all users who join the server
        """

        if ctx.subcommand_passed is not None:
            if ctx.invoked_subcommand is None:
                raise UserInputError
            return

        embed = Embed(title=t.joinkick, color=Colors.error)

        if self.joinkick_enabled:
            embed.add_field(name=tg.status, value=tg.enabled, inline=False)
        else:
            embed.add_field(name=tg.status, value=tg.disabled, inline=False)

        await reply(ctx, embed=embed)

    @joinkick.command(name="enable", aliases=["e", "on"])
    async def joinkick_enable(self, ctx):
        """
        Enable joinkick
        """

        self.joinkick_enabled = True

        embed = Embed(title=t.antiraid, description=t.joinkick_set_enabled, color=Colors.AntiRaid)
        await reply(ctx, embed=embed)
        await send_to_changelog_antiraid(ctx.guild, ctx.author, Colors.AntiRaid, t.joinkick, t.joinkick_set_enabled)

    @joinkick.command(name="disable", aliases=["d", "off"])
    async def joinkick_disable(self, ctx):
        """
        Disable joinkick
        """

        self.joinkick_enabled = False

        embed = Embed(title=t.antiraid, description=t.joinkick_set_disabled, color=Colors.AntiRaid)
        await reply(ctx, embed=embed)
        await send_to_changelog_antiraid(ctx.guild, ctx.author, Colors.AntiRaid, t.joinkick, t.joinkick_set_disabled)

    @antiraid.command(aliases=["time"])
    async def timespan(self, ctx, time: int):
        """
        Set the timespan for the raid detection
        """
        
        if time <= 0:
            raise UserInputError(tg.invalid_duration)
        
        await AntiRaidSettings.timespan.set(time)
        
        embed = Embed(title=t.antiraid, description=t.time_configured, color=Colors.AntiRaid)
        await reply(ctx, embed=embed)
        await send_to_changelog_antiraid(ctx.guild, ctx.author, Colors.AntiRaid, t.antiraid, t.log_time_configured(time))

    @antiraid.command()
    async def threshold(self, ctx, thr: int):
        """
        Set the number of joins in the timespan to trigger raid alarm
        """
        
        if thr < 0:
            raise UserInputError(t.invalid_threshold)
        
        await AntiRaidSettings.threshold.set(thr)
        
        embed = Embed(title=t.antiraid, description=t.threshold_configured, color=Colors.AntiRaid)
        await reply(ctx, embed=embed)
        await send_to_changelog_antiraid(ctx.guild, ctx.author, Colors.AntiRaid, t.antiraid, t.log_threshold_configured(thr))

    @antiraid.command()
    async def alert_cooldown(self, ctx, res:int):
        """
        Set the minimum time between two raid alarms
        """
        
        if res < 0:
            raise UserInputError(tg.invalid_duration)
        
        await AntiRaidSettings.alert_cooldown.set(res)
        
        embed = Embed(title=t.antiraid, description=t.alert_cooldown_configured, color=Colors.AntiRaid)
        await reply(ctx, embed=embed)
        await send_to_changelog_antiraid(ctx.guild, ctx.author, Colors.AntiRaid, t.antiraid, t.log_alert_cooldown_configured(res))
