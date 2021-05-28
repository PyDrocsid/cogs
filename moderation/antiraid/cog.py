from PyDrocsid.cog import Cog

from discord import Embed, Guild, User, Member, Forbidden

from discord.ext import commands
from discord.ext.commands import Context, UserInputError, guild_only, CommandError

from discord.utils import snowflake_time

from datetime import datetime

from typing import Union

from PyDrocsid.command import reply
from PyDrocsid.database import db, filter_by
from PyDrocsid.translations import t

from .colors import Colors
from .permission import AntiRaidPermission
from ..mod.models import Kick
from ...contributor import Contributor
from ...information.user_info.models import Join
from ...pubsub import send_to_changelog


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


class AntiRaidCog(Cog, name="AntiRaid"):
    CONTRIBUTORS=[Contributor.Anorak]


    def __init__(self):
        super().__init__()

        self.joinkick_enabled: bool = False

    # TODO Add join event to make joinkick work

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

        if self.joinkick_enabled:
            embed.add_field(name=t.joinkick, value=tg.enabled, inline=False)
        else:
            embed.add_field(name=t.joinkick, value=tg.disabled, inline=False)

        await reply(ctx, embed=embed)


    @antiraid.command(aliases=["tk"])
    @AntiRaidPermission.timekick.check
    async def timekick(self, ctx: Context, snowflake: int):
        """
        Kick all users who joined after the snowflake's creation time
        """

        try:
            time = snowflake_time(snowflake)
        except (OverflowError, ValueError):
            raise CommandError(t.invalid_snowflake)
        
        if time > datetime.utcnow():
            raise CommandError(t.invalid_time)

        user_embed = Embed(title=t.ongoing_raid_title, description=t.ongoing_raid_message, color=Colors.error)

        async for join in await db.stream(filter_by(Join).filter(Join.timestamp >= time).distinct(Join.member).group_by(Join.member)):
            if (member := ctx.guild.get_member(join.member)) and not member.bot:
                try:
                    await member.send(embed=user_embed)
                except Forbidden:
                    pass
                await member.kick()
                await Kick.create(member.id, str(member), ctx.author.id, t.kicked_timekick)

        embed = Embed(title=t.timekick, description=t.timekick_done(time.strftime("%d.%m.%Y %H:%M:%S")), color=Colors.AntiRaid)
        await reply(ctx, embed=embed)
        await send_to_changelog_antiraid(ctx.guild, ctx.author, Colors.AntiRaid, t.antiraid, t.timekick_done(time.strftime("%d.%m.%Y %H:%M:%S")))


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
