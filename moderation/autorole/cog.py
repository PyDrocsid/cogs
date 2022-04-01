from typing import Optional

from discord import Embed, Member, Role
from discord.ext import commands
from discord.ext.commands import CommandError, Context, UserInputError, guild_only

from PyDrocsid.cog import Cog
from PyDrocsid.config import Contributor
from PyDrocsid.embeds import send_long_embed
from PyDrocsid.emojis import name_to_emoji
from PyDrocsid.translations import t
from PyDrocsid.util import check_role_assignable

from .colors import Colors
from .models import AutoRole
from .permissions import AutoRolePermission
from ...pubsub import send_to_changelog

tg = t.g
t = t.autorole


class AutoRoleCog(Cog, name="AutoRole"):
    CONTRIBUTORS = [Contributor.Defelo]

    async def on_member_join(self, member: Member):
        roles: list[Role] = []
        invalid: list[Role] = []

        role: Role
        for role in map(member.guild.get_role, await AutoRole.all()):
            if not role:
                continue

            try:
                check_role_assignable(role)
            except CommandError:
                invalid.append(role)
            else:
                roles.append(role)

        await member.add_roles(*roles)

        if invalid:
            raise PermissionError(
                member.guild,
                t.cannot_assign(cnt=len(invalid), member=member, roles=", ".join(role.mention for role in invalid)),
            )

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
        await send_long_embed(ctx, embed)

    @autorole.command(name="add", aliases=["a", "+"])
    @AutoRolePermission.write.check
    async def autorole_add(self, ctx: Context, *, role: Role):
        """
        add a role
        """

        if await AutoRole.exists(role.id):
            raise CommandError(t.ar_already_set)

        check_role_assignable(role)

        await AutoRole.add(role.id)
        await ctx.message.add_reaction(name_to_emoji["white_check_mark"])
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
        await ctx.message.add_reaction(name_to_emoji["white_check_mark"])
        await send_to_changelog(ctx.guild, t.log_ar_removed(role))
