import asyncio
from asyncio import Task
from typing import Optional, Dict

from discord import Role, Member, Guild, Forbidden, HTTPException, Embed
from discord.ext import commands
from discord.ext.commands import guild_only, Context, CommandError, UserInputError

from PyDrocsid.cog import Cog
from PyDrocsid.command import reply
from PyDrocsid.translations import t
from .colors import Colors
from .permissions import AutoModPermission
from .settings import AutoModSettings, AutoKickMode
from ...contributor import Contributor
from ...pubsub import send_to_changelog, log_auto_kick, revoke_verification, send_alert

tg = t.g
t = t.automod

pending_kicks: set[int] = set()


async def kick(member: Member) -> bool:
    if not member.guild.me.guild_permissions.kick_members:
        await send_alert(member.guild, t.cannot_kick(member.mention, member.id))
        return False

    if member.top_role >= member.guild.me.top_role or member.id == member.guild.owner_id:
        return False

    try:
        embed = Embed(
            title=t.autokick,
            description=t.autokicked(member.guild.name),
            colour=Colors.AutoMod,
        )
        await member.send(embed=embed)
    except (Forbidden, HTTPException):
        pass

    pending_kicks.add(member.id)
    await member.kick(reason=t.log_autokicked)
    await log_auto_kick(member)
    await revoke_verification(member)
    return True


async def kick_delay(member: Member, delay: int, role: Role, reverse: bool):
    await asyncio.sleep(delay)
    if reverse != (role in member.roles):
        return

    if (member := member.guild.get_member(member.id)) is not None:
        await kick(member)


class AutoModCog(Cog, name="AutoMod"):
    CONTRIBUTORS = [Contributor.Defelo, Contributor.wolflu]

    def __init__(self):
        super().__init__()

        self.kick_tasks: Dict[Member, Task] = {}

    async def get_autokick_role(self) -> Optional[Role]:
        guild: Guild = self.bot.guilds[0]
        return guild.get_role(await AutoModSettings.autokick_role.get())

    async def get_instantkick_role(self) -> Optional[Role]:
        guild: Guild = self.bot.guilds[0]
        return guild.get_role(await AutoModSettings.instantkick_role.get())

    def cancel_task(self, member: Member):
        if member in self.kick_tasks:
            self.kick_tasks.pop(member).cancel()

    async def on_member_join(self, member: Member):
        if member.bot:
            return

        mode: int = await AutoModSettings.autokick_mode.get()
        role: Optional[Role] = await self.get_autokick_role()
        if mode == 0 or role is None:
            return

        delay: int = await AutoModSettings.autokick_delay.get()
        self.kick_tasks[member] = asyncio.create_task(kick_delay(member, delay, role, mode == 2))
        self.kick_tasks[member].add_done_callback(lambda _: self.cancel_task(member))

    async def on_member_remove(self, member: Member):
        if member.id in pending_kicks:
            pending_kicks.remove(member.id)
            return

        self.cancel_task(member)

    async def on_member_role_add(self, member: Member, role: Role):
        if member.bot:
            return

        if role == await self.get_instantkick_role():
            if not await kick(member):
                try:
                    await member.remove_roles(role)
                except Forbidden:
                    pass
            return

        mode: int = await AutoModSettings.autokick_mode.get()
        if mode == 1 and role == await self.get_autokick_role():
            self.cancel_task(member)

    async def on_member_role_remove(self, member: Member, role: Role):
        if member.bot:
            return

        mode: int = await AutoModSettings.autokick_mode.get()
        if mode == 2 and role == await self.get_autokick_role():
            self.cancel_task(member)

    @commands.group(aliases=["ak"])
    @AutoModPermission.autokick_read.check
    @guild_only()
    async def autokick(self, ctx: Context):
        """
        manage autokick
        """

        if ctx.subcommand_passed is not None:
            if ctx.invoked_subcommand is None:
                raise UserInputError
            return

        embed = Embed(title=t.autokick, colour=Colors.error)
        mode: int = await AutoModSettings.autokick_mode.get()
        role: Optional[Role] = await self.get_autokick_role()
        if mode == AutoKickMode.off or role is None:
            embed.add_field(name=tg.status, value=t.autokick_disabled, inline=False)
            await reply(ctx, embed=embed)
            return

        embed.add_field(name=tg.status, value=t.autokick_mode[mode - 1], inline=False)
        embed.colour = Colors.AutoMod
        delay: int = await AutoModSettings.autokick_delay.get()
        embed.add_field(name=tg.delay, value=t.x_seconds(cnt=delay), inline=False)
        embed.add_field(name=tg.role, value=role.mention, inline=False)

        await reply(ctx, embed=embed)

    @autokick.command(name="mode", aliases=["m"])
    @AutoModPermission.autokick_write.check
    async def autokick_mode(self, ctx: Context, mode: str):
        """
        configure autokick mode

        `off` - disable autokick
        `normal` - kick members without a specific role
        `reverse` - kick members with a specific role
        """

        mode: str = mode.lower()
        if not hasattr(AutoKickMode, mode):
            raise UserInputError

        mode: int = getattr(AutoKickMode, mode)
        await AutoModSettings.autokick_mode.set(mode)
        embed = Embed(title=t.autokick, description=t.autokick_mode_configured[mode], colour=Colors.AutoMod)
        await reply(ctx, embed=embed)
        await send_to_changelog(ctx.guild, t.autokick_mode_configured[mode])

    @autokick.command(name="delay", aliases=["d"])
    @AutoModPermission.autokick_write.check
    async def autokick_delay(self, ctx: Context, seconds: int):
        """
        configure autokick delay (in seconds)
        """

        if not 0 < seconds < 300:
            raise CommandError(tg.invalid_duration)

        await AutoModSettings.autokick_delay.set(seconds)
        embed = Embed(title=t.autokick, description=t.autokick_delay_configured, colour=Colors.AutoMod)
        await reply(ctx, embed=embed)
        await send_to_changelog(ctx.guild, t.log_autokick_delay_configured(cnt=seconds))

    @autokick.command(name="role", aliases=["r"])
    @AutoModPermission.autokick_write.check
    async def autokick_role(self, ctx: Context, *, role: Role):
        """
        configure autokick role
        """

        await AutoModSettings.autokick_role.set(role.id)
        embed = Embed(title=t.autokick, description=t.autokick_role_configured, colour=Colors.AutoMod)
        await reply(ctx, embed=embed)
        await send_to_changelog(ctx.guild, t.log_autokick_role_configured(role.mention, role.id))

    @commands.group(aliases=["ik"])
    @AutoModPermission.instantkick_read.check
    @guild_only()
    async def instantkick(self, ctx: Context):
        """
        manage instantkick
        """

        if ctx.subcommand_passed is not None:
            if ctx.invoked_subcommand is None:
                raise UserInputError
            return

        embed = Embed(title=t.instantkick, colour=Colors.error)
        role: Optional[Role] = await self.get_instantkick_role()
        if role is None:
            embed.add_field(name=tg.status, value=t.instantkick_disabled)
            await reply(ctx, embed=embed)
            return

        embed.add_field(name=tg.status, value=t.instantkick_enabled, inline=False)
        embed.colour = Colors.AutoMod
        embed.add_field(name=tg.role, value=role.mention, inline=False)

        await reply(ctx, embed=embed)

    @instantkick.command(name="disable", aliases=["d", "off"])
    @AutoModPermission.instantkick_write.check
    async def instantkick_disable(self, ctx: Context):
        """
        disable instantkick
        """

        await AutoModSettings.instantkick_role.reset()
        embed = Embed(title=t.instantkick, description=t.instantkick_set_disabled, colour=Colors.AutoMod)
        await reply(ctx, embed=embed)
        await send_to_changelog(ctx.guild, t.instantkick_set_disabled)

    @instantkick.command(name="role", aliases=["r"])
    @AutoModPermission.instantkick_write.check
    async def instantkick_role(self, ctx: Context, *, role: Role):
        """
        configure instantkick role
        """

        if role >= ctx.me.top_role:
            raise CommandError(t.instantkick_cannot_kick)

        await AutoModSettings.instantkick_role.set(role.id)
        embed = Embed(title=t.instantkick, description=t.instantkick_role_configured, colour=Colors.AutoMod)
        await reply(ctx, embed=embed)
        await send_to_changelog(ctx.guild, t.log_instantkick_role_configured(role.mention, role.id))
