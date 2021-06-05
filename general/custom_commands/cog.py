from enum import auto
from io import BytesIO
from pathlib import Path
from typing import Optional

import yaml
from PyDrocsid.logger import get_logger
from discord import Embed, File, TextChannel, NotFound, Forbidden
from discord.ext import commands
from discord.ext.commands import Context

from PyDrocsid.cog import Cog
from PyDrocsid.command import reply, docs, confirm
from PyDrocsid.command_edit import link_response
from PyDrocsid.config import Contributor
from PyDrocsid.emojis import name_to_emoji
from PyDrocsid.permission import BasePermission
from PyDrocsid.translations import t
from PyDrocsid.util import check_message_send_permissions

logger = get_logger(__name__)

tg = t.g
t = t.custom_commands


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

    def __init__(self, *command_files: str):
        cmds = {}

        path_list = list(map(Path, command_files))

        while path_list:
            path = path_list.pop()
            if not path.exists():
                logger.warning(f"{path} does not exist")
                continue

            if path.is_dir():
                path_list += path.iterdir()
                continue
            if not path.is_file():
                continue

            with path.open() as file:
                content = yaml.safe_load(file) or {}

            cmds |= {name: data for name, data in content.items() if not data.get("disabled", False)}

        permission = BasePermission(
            "CustomCommandsPermission",
            {
                **{name: auto() for name, data in cmds.items() if not data.get("public", False)},
                "description": property(lambda x: f"use `{x.name}` command"),
            },
        )

        self.__cog_commands__ = [create_custom_command(k, v, getattr(permission, k, None)) for k, v in cmds.items()]
