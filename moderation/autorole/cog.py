from typing import Optional

from discord import Member, Embed, Role
from discord.ext import commands
from discord.ext.commands import guild_only, Context, UserInputError, CommandError

from PyDrocsid.cog import Cog
from PyDrocsid.config import Contributor
from PyDrocsid.translations import t
from PyDrocsid.util import reply
from .colors import Colors
from .models import AutoRole
from .permissions import AutoRolePermission
from ...pubsub import send_to_changelog

tg = t.g
t = t.autorole


class AutoRoleCog(Cog, name="AutoRole"):
    CONTRIBUTORS = [Contributor.Defelo]
    PERMISSIONS = AutoRolePermission

    async def on_member_join(self, member: Member):
        await member.add_roles(*filter(lambda r: r, map(member.guild.get_role, await AutoRole.all())))

    @commands.group(aliases=["ar"])
    @AutoRolePermission.read.check
    @guild_only()
    async def autorole(self, ctx: Context):
        """
        configure autorole
        """

        if ctx.subcommand_passed is not None:
            if ctx.invoked_subcommand is None:
                raise UserInputError
            return

        embed = Embed(title=t.autorole, colour=Colors.AutoRole)
        out = []
        for role_id in await AutoRole.all():
            role: Optional[Role] = ctx.guild.get_role(role_id)
            if role is None:
                await AutoRole.remove(role_id)
            else:
                out.append(f":small_orange_diamond: {role.mention}")
        if not out:
            embed.description = t.no_autorole
            embed.colour = Colors.error
        else:
            embed.description = "\n".join(out)
        await ctx.send(embed=embed)

    @autorole.command(name="add", aliases=["a", "+"])
    @AutoRolePermission.write.check
    async def autorole_add(self, ctx: Context, *, role: Role):
        """
        add a role
        """

        if await AutoRole.exists(role.id):
            raise CommandError(t.ar_already_set)

        if role >= ctx.me.top_role:
            raise CommandError(t.role_not_added_too_high(role, ctx.me.top_role))
        if role.managed:
            raise CommandError(t.role_not_added_managed_role(role))

        await AutoRole.add(role.id)
        await reply(ctx, t.ar_added)
        await send_to_changelog(ctx.guild, t.log_ar_added(role))

    @autorole.command(name="remove", aliases=["r", "del", "d", "-"])
    @AutoRolePermission.write.check
    async def autorole_remove(self, ctx: Context, *, role: Role):
        """
        remove a role
        """

        if not await AutoRole.exists(role.id):
            raise CommandError(t.ar_not_set)

        await AutoRole.remove(role.id)
        await reply(ctx, t.ar_removed)
        await send_to_changelog(ctx.guild, t.log_ar_removed(role))
