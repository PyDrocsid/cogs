from typing import Optional, Union, List

from discord import Message, Embed
from discord.ext import commands
from discord.ext.commands import Command, Group, CommandError, Context

from PyDrocsid.cog import Cog, get_documentation
from PyDrocsid.command import can_run_command, docs, get_optional_permissions
from PyDrocsid.config import Contributor
from PyDrocsid.embeds import send_long_embed
from PyDrocsid.permission import BasePermission, BasePermissionLevel
from PyDrocsid.translations import t
from .colors import Colors

tg = t.g
t = t.help


async def send_help(ctx: Context, command_name: Optional[Union[str, Command]]) -> List[Message]:
    def format_command(cmd: Command) -> str:
        doc = " - " + cmd.short_doc if cmd.short_doc else ""
        return f"`{cmd.name}`{doc}"

    async def add_commands(cog_name: str, cmds: List[Command]):
        desc: List[str] = []
        for cmd in sorted(cmds, key=lambda c: c.name):
            if not cmd.hidden and await can_run_command(cmd, ctx):
                emoji = getattr(cmd._callback, "emoji", ":small_orange_diamond:")
                desc.append(emoji + " " + format_command(cmd))
        if desc:
            embed.add_field(name=cog_name, value="\n".join(desc), inline=False)

    embed = Embed(title=t.help, color=Colors.help)
    if command_name is None:
        for cog in sorted(ctx.bot.cogs.values(), key=lambda c: c.qualified_name):
            await add_commands(cog.qualified_name, cog.get_commands())
        await add_commands(t.no_category, [command for command in ctx.bot.commands if command.cog is None])

        embed.add_field(name="** **", value=t.help_usage(ctx.prefix), inline=False)

        return await send_long_embed(ctx, embed, paginate=True, max_fields=8)

    if isinstance(command_name, str):
        cog: Optional[Cog] = ctx.bot.get_cog(command_name)
        if cog is not None:
            await add_commands(cog.qualified_name, cog.get_commands())
            if doc_url := get_documentation(cog):
                embed.add_field(name=t.documentation, value=doc_url, inline=False)
            return await send_long_embed(ctx, embed)

        command: Optional[Union[Command, Group]] = ctx.bot.get_command(command_name)
        if command is None:
            raise CommandError(t.cog_or_command_not_found)
    else:
        command: Command = command_name

    if not await can_run_command(command, ctx):
        raise CommandError(tg.not_allowed)

    description = ctx.prefix
    if command.full_parent_name:
        description += command.full_parent_name + " "
    if command.aliases:
        description += "[" + "|".join([command.name] + command.aliases) + "] "
    else:
        description += command.name + " "
    description += command.signature

    embed.description = f"```css\n{description.strip()}\n```"
    embed.add_field(name=t.description, value=command.help, inline=False)

    if isinstance(command, Group):
        await add_commands(t.subcommands, command.commands)

    permissions: list[str] = []
    permission_levels: list[BasePermissionLevel] = []

    cmds = []
    cmd = command
    while cmd:
        cmds.append(cmd)
        cmd = cmd.parent

    for cmd in reversed(cmds):
        for check in cmd.checks:
            permission: Union[BasePermission, BasePermissionLevel, None] = getattr(check, "level", None)
            if isinstance(permission, BasePermission):
                permissions.append(permission.fullname)
            elif isinstance(permission, BasePermissionLevel):
                permission_levels.append(permission)

    if permissions:
        embed.add_field(
            name=t.required_permissions,
            value="\n".join(f":small_orange_diamond: `{p}`" for p in permissions),
            inline=False,
        )
    if permission_levels:
        permission_level: BasePermissionLevel = max(permission_levels, key=lambda pl: pl.level)
        if permission_level.level > 0:
            embed.add_field(
                name=t.required_permission_level,
                value=f":small_orange_diamond: **{permission_level.description}**",
                inline=False,
            )

    optional_permissions: list[str] = [permission.fullname for permission in get_optional_permissions(command)]
    if optional_permissions:
        embed.add_field(
            name=t.optional_permissions,
            value="\n".join(f":small_blue_diamond: `{p}`" for p in optional_permissions),
            inline=False,
        )

    if (doc_url := get_documentation(cmd.cog)) and not getattr(cmd.callback, "no_documentation", False):
        embed.add_field(name=t.documentation, value=doc_url, inline=False)

    return await send_long_embed(ctx, embed)


class HelpCog(Cog, name="Help"):
    CONTRIBUTORS = [Contributor.Defelo, Contributor.ce_phox]

    @commands.command()
    @docs(t.commands.help)
    async def help(self, ctx: Context, *, cog_or_command: Optional[str]):
        await send_help(ctx, cog_or_command)
