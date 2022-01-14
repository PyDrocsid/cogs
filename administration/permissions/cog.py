import asyncio
from typing import Optional

from discord import Embed, Role
from discord.ext import commands
from discord.ext.commands import guild_only, Context, Converter, BadArgument, CommandError, UserInputError

from PyDrocsid.cog import Cog
from PyDrocsid.command import reply, docs
from PyDrocsid.config import Config, get_subclasses_in_enabled_packages
from PyDrocsid.embeds import send_long_embed
from PyDrocsid.permission import BasePermissionLevel, BasePermission
from PyDrocsid.settings import RoleSettings
from PyDrocsid.translations import t
from .colors import Colors
from .permissions import PermissionsPermission
from ...contributor import Contributor
from ...pubsub import send_to_changelog

tg = t.g
t = t.permissions


def get_permissions() -> list[BasePermission]:
    permissions: list[BasePermission] = []
    for cls in get_subclasses_in_enabled_packages(BasePermission):
        permissions += [x for x in cls if not hasattr(x, "_disabled")]
    return permissions


async def list_permissions(ctx: Context, title: str, min_level: BasePermissionLevel):
    out = {}
    permissions: list[BasePermission] = get_permissions()
    levels = await asyncio.gather(*[permission.resolve() for permission in permissions])
    for permission, level in zip(permissions, levels):
        if min_level.level >= level.level:
            out.setdefault((level.level, level.description), []).append(
                f"`{permission.fullname}` - {permission.description}",
            )

    embed = Embed(title=title, colour=Colors.error)
    if not out:
        embed.description = t.no_permissions
        await reply(ctx, embed=embed)
        return

    embed.colour = Colors.Permissions
    for (_, name), lines in sorted(out.items(), reverse=True):
        embed.add_field(name=name, value="\n".join(sorted(lines)), inline=False)

    await send_long_embed(ctx, embed, paginate=True)


class PermissionLevelConverter(Converter):
    async def convert(self, ctx: Context, argument: str) -> BasePermissionLevel:
        for level in Config.PERMISSION_LEVELS:  # type: BasePermissionLevel
            if argument.lower() in level.aliases or argument == str(level.level):
                return level

        raise BadArgument(t.invalid_permission_level)


class PermissionsCog(Cog, name="Permissions"):
    CONTRIBUTORS = [Contributor.Defelo, Contributor.wolflu]

    @commands.group(aliases=["perm", "p"])
    @guild_only()
    @docs(t.commands.permissions)
    async def permissions(self, ctx: Context):
        if ctx.invoked_subcommand is None:
            raise UserInputError

    @permissions.command(name="list", aliases=["show", "l", "?"])
    @PermissionsPermission.view_all.check
    @docs(t.commands.permissions_list)
    async def permissions_list(self, ctx: Context, min_level: Optional[PermissionLevelConverter]):
        if min_level is None:
            min_level = Config.DEFAULT_PERMISSION_LEVEL

        await list_permissions(ctx, t.permissions_title, min_level)

    @permissions.command(name="my", aliases=["m", "own", "o"])
    @PermissionsPermission.view_own.check
    @docs(t.commands.permissions_my)
    async def permissions_my(self, ctx: Context):
        min_level: BasePermissionLevel = await Config.PERMISSION_LEVELS.get_permission_level(ctx.author)
        await list_permissions(ctx, t.my_permissions_title, min_level)

    @permissions.command(name="set", aliases=["s", "="])
    @PermissionsPermission.manage.check
    @docs(t.commands.permissions_set)
    async def permissions_set(self, ctx: Context, permission_name: str, level: PermissionLevelConverter):
        level: BasePermissionLevel
        for permission in get_permissions():
            if permission.fullname.lower() == permission_name.lower():
                break
        else:
            raise CommandError(t.invalid_permission)

        max_level: BasePermissionLevel = await Config.PERMISSION_LEVELS.get_permission_level(ctx.author)
        if max(level.level, (await permission.resolve()).level) > max_level.level:
            raise CommandError(t.cannot_manage_permission_level)

        await permission.set(level)

        description = permission.fullname, level.description
        embed = Embed(
            title=t.permissions_title,
            colour=Colors.Permissions,
            description=t.permission_set(*description),
        )
        await reply(ctx, embed=embed)
        await send_to_changelog(ctx.guild, t.log_permission_set(*description))

    @permissions.command(name="permission_levels", aliases=["pl"])
    @PermissionsPermission.view_all.check
    @docs(t.commands.permissions_permission_levels)
    async def permissions_permission_levels(self, ctx: Context):
        embed = Embed(title=t.permission_levels, color=Colors.Permissions)

        for level in Config.PERMISSION_LEVELS:  # type: BasePermissionLevel
            description = t.aliases(", ".join(f"`{alias}`" for alias in level.aliases))
            description += "\n" + t.level(level.level)

            granted_by: list[str] = [f"`{gp}`" for gp in level.guild_permissions]
            for role_name in level.roles:
                role: Optional[Role] = ctx.guild.get_role(await RoleSettings.get(role_name))
                if role:
                    granted_by.append(role.mention)

            if not level.level:
                granted_by = ["@everyone"]

            if granted_by:
                description += "\n" + t.granted_by + "\n" + "\n".join(f":small_orange_diamond: {x}" for x in granted_by)

            embed.add_field(name=level.description, value=description, inline=False)

        await send_long_embed(ctx, embed, paginate=True)
