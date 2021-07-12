from io import BytesIO
from pathlib import Path
from typing import Optional

from discord import Embed, File, TextChannel, NotFound, Forbidden
from discord.ext import commands
from discord.ext.commands import Context, guild_only, UserInputError, Converter, BadArgument

from PyDrocsid.cog import Cog
from PyDrocsid.command import reply, docs, confirm
from PyDrocsid.command_edit import link_response
from PyDrocsid.config import Contributor
from PyDrocsid.database import db
from PyDrocsid.emojis import name_to_emoji
from PyDrocsid.logger import get_logger
from PyDrocsid.permission import BasePermission
from PyDrocsid.translations import t
from PyDrocsid.util import check_message_send_permissions
from .models import CustomCommand, Alias
from .permissions import CustomCommandsPermission
from ...administration.permissions.cog import PermissionsCog, PermissionLevelConverter

logger = get_logger(__name__)

tg = t.g
t = t.custom_commands


class CustomCommandConverter(Converter):
    async def convert(self, ctx: Context, argument: str) -> CustomCommand:
        if cmd := await db.get(CustomCommand, name=argument):
            return cmd
        if alias := await db.get(Alias, Alias.command, name=argument):
            return alias.command
        raise BadArgument


def create_custom_command(name: str, data: dict, permission: Optional[BasePermission]):
    content = data.get("content", "")
    file_name = None
    file_content = None
    embed = None

    if file_data := data.get("file"):
        path = Path(file_data)
        file_name = path.name
        file_content = path.read_bytes()

    if embed_data := data.get("embed"):
        embed = Embed.from_dict(embed_data)

    async def send_message(ctx: Context, channel: TextChannel):
        check_message_send_permissions(channel, check_file=bool(file_content), check_embed=bool(embed))

        if bool(data.get("requires_confirmation", permission is not None)):
            conf_embed = Embed(title=t.confirmation, description=t.confirm(name, channel.mention))
            async with confirm(ctx, conf_embed) as (result, msg):
                if not result:
                    conf_embed.description += "\n\n" + t.canceled
                    return

                conf_embed.description += "\n\n" + t.confirmed
                if msg:
                    await msg.delete(delay=5)

        if delete_command := bool(data.get("delete_command", False)):
            try:
                await ctx.message.delete()
            except (NotFound, Forbidden):
                pass

        file = File(BytesIO(file_content), filename=file_name) if file_content else None
        if ctx.channel.id == channel.id:
            if delete_command:
                await ctx.send(content, file=file, embed=embed)
            else:
                await reply(ctx, content, file=file, embed=embed)
        else:
            msg = await channel.send(content, file=file, embed=embed)
            if not delete_command:
                await link_response(ctx, msg)
                await ctx.message.add_reaction(name_to_emoji["white_check_mark"])

    async def with_channel_parameter(_, ctx: Context, channel: TextChannel):
        await send_message(ctx, channel)

    async def without_channel_parameter(_, ctx: Context):
        channel = ctx.bot.get_channel(channel_id) if (channel_id := data.get("channel")) else ctx.channel
        await send_message(ctx, channel)

    command = with_channel_parameter if data.get("channel_parameter", False) else without_channel_parameter
    if description := data.get("description"):
        command = docs(description)(command)

    if permission:
        command = permission.check(command)

    command = commands.command(name=name, aliases=data.get("aliases", []))(command)

    return command


class CustomCommandsCog(Cog, name="Custom Commands"):
    CONTRIBUTORS = [Contributor.Defelo]
    DEPENDENCIES = [PermissionsCog]

    # def __init__(self):
    #     cmds = {}
    #
    #     while path_list:
    #         path = path_list.pop()
    #         if not path.exists():
    #             logger.warning(f"{path} does not exist")
    #             continue
    #
    #         if path.is_dir():
    #             path_list += path.iterdir()
    #             continue
    #         if not path.is_file():
    #             continue
    #
    #         with path.open() as file:
    #             content = yaml.safe_load(file) or {}
    #
    #         cmds |= {name: data for name, data in content.items() if not data.get("disabled", False)}
    #
    #     permission = BasePermission(
    #         "CustomCommandsPermission",
    #         {
    #             **{name: auto() for name, data in cmds.items() if not data.get("public", False)},
    #             "description": property(lambda x: f"use `{x.name}` command"),
    #         },
    #     )
    #
    #     self.__cog_commands__ = [create_custom_command(k, v, getattr(permission, k, None)) for k, v in cmds.items()]

    @commands.group(aliases=["cc"])
    @CustomCommandsPermission.read.check
    @guild_only()
    @docs(t.commands.custom_commands)
    async def custom_commands(self, ctx: Context):
        if ctx.subcommand_passed is not None:
            if ctx.invoked_subcommand is None:
                raise UserInputError
            return

        pass

    @custom_commands.command(name="add", aliases=["a", "+"])
    @CustomCommandsPermission.write.check
    @docs(t.commands.add)
    async def custom_commands_add(self, ctx: Context, name: str, disabled: bool = False):
        pass

    @custom_commands.command(name="show", aliases=["s", "view", "v", "?"])
    @docs(t.commands.show)
    async def custom_commands_show(self, ctx: Context, command: CustomCommandConverter):
        pass

    @custom_commands.command(name="test", aliases=["t"])
    @docs(t.commands.test)
    async def custom_commands_test(self, ctx: Context, command: CustomCommandConverter):
        pass

    @custom_commands.group(name="edit", aliases=["e"])
    @CustomCommandsPermission.write.check
    @docs(t.commands.edit_)
    async def custom_commands_edit(self, ctx: Context):
        if ctx.invoked_subcommand is None:
            raise UserInputError

    @custom_commands_edit.command(name="name", aliases=["n"])
    @docs(t.commands.edit.name)
    async def custom_commands_edit_name(self, ctx: Context, command: CustomCommandConverter, *, name: str):
        pass

    @custom_commands_edit.command(name="description", alises=["desc", "d"])
    @docs(t.commands.edit.description)
    async def custom_commands_edit_description(
        self,
        ctx: Context,
        command: CustomCommandConverter,
        *,
        description: str,
    ):
        pass

    @custom_commands_edit.command(name="channel_parameter_enabled", alises=["cpe"])
    @docs(t.commands.edit.channel_parameter_enabled)
    async def custom_commands_edit_channel_parameter_enabled(
        self,
        ctx: Context,
        command: CustomCommandConverter,
        enabled: bool,
    ):
        pass

    @custom_commands_edit.command(name="channel", alises=["c"])
    @docs(t.commands.edit.channel)
    async def custom_commands_edit_channel(
        self,
        ctx: Context,
        command: CustomCommandConverter,
        *,
        channel: TextChannel,
    ):
        pass

    @custom_commands_edit.command(name="delete_command", alises=["dc"])
    @docs(t.commands.edit.delete_command)
    async def custom_commands_edit_delete_command(self, ctx: Context, command: CustomCommandConverter, delete: bool):
        pass

    @custom_commands_edit.command(name="permission_level", alises=["pl"])
    @docs(t.commands.edit.permission_level)
    async def custom_commands_edit_permission_level(
        self,
        ctx: Context,
        command: CustomCommandConverter,
        level: PermissionLevelConverter,
    ):
        pass

    @custom_commands_edit.command(name="requires_confirmation", alises=["rc"])
    @docs(t.commands.edit.requires_confirmation)
    async def custom_commands_edit_requires_confirmation(
        self,
        ctx: Context,
        command: CustomCommandConverter,
        enabled: bool,
    ):
        pass

    @custom_commands_edit.command(name="data", alises=["content", "text", "t"])
    @docs(t.commands.edit.data)
    async def custom_commands_edit_data(self, ctx: Context, command: CustomCommandConverter):
        pass

    @custom_commands.command(name="disable")
    @CustomCommandsPermission.write.check
    @docs(t.commands.disable)
    async def custom_commands_disable(self, ctx: Context, command: CustomCommandConverter):
        pass

    @custom_commands.command(name="enable")
    @CustomCommandsPermission.write.check
    @docs(t.commands.enable)
    async def custom_commands_enable(self, ctx: Context, command: CustomCommandConverter):
        pass

    @custom_commands.command(name="alias")
    @CustomCommandsPermission.write.check
    @docs(t.commands.alias)
    async def custom_commands_alias(self, ctx: Context, command: CustomCommandConverter, alias: str):
        pass

    @custom_commands.command(name="unalias")
    @CustomCommandsPermission.write.check
    @docs(t.commands.unalias)
    async def custom_commands_unalias(self, ctx: Context, alias: str):
        pass

    @custom_commands.command(name="remove", aliases=["r", "del", "d", "-"])
    @CustomCommandsPermission.write.check
    @docs(t.commands.remove)
    async def custom_commands_remove(self, ctx: Context, command: CustomCommandConverter):
        pass
