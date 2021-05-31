from io import BytesIO
from pathlib import Path

import yaml
from discord import Embed, File, TextChannel, Permissions
from discord.ext import commands
from discord.ext.commands import Context, CommandError

from PyDrocsid.cog import Cog
from PyDrocsid.command import reply, docs
from PyDrocsid.command_edit import link_response
from PyDrocsid.config import Contributor, Config
from PyDrocsid.emojis import name_to_emoji
from PyDrocsid.permission import BasePermissionLevel
from PyDrocsid.translations import t

tg = t.g
t = t.custom_commands


def create_custom_command(name: str, data: dict):
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
        permissions: Permissions = channel.permissions_for(channel.guild.me)
        if not permissions.send_messages:
            raise CommandError(t.could_not_send_message(channel.mention))
        if not permissions.embed_links:
            raise CommandError(t.could_not_send_embed(channel.mention))

        file = File(BytesIO(file_content), filename=file_name) if file_content else None
        if ctx.channel.id == channel.id:
            await reply(ctx, content, file=file, embed=embed)
        else:
            await link_response(ctx, await channel.send(content, file=file, embed=embed))
            await ctx.message.add_reaction(name_to_emoji["white_check_mark"])

    async def with_channel_parameter(_, ctx: Context, channel: TextChannel):
        await send_message(ctx, channel)

    async def without_channel_parameter(_, ctx: Context):
        channel = ctx.bot.get_channel(channel_id) if (channel_id := data.get("channel")) else ctx.channel
        await send_message(ctx, channel)

    command = with_channel_parameter if data.get("channel_parameter", False) else without_channel_parameter
    if description := data.get("description"):
        command = docs(description)(command)

    if permission_level_name := data.get("permission_level"):
        permission_level: BasePermissionLevel = Config.PERMISSION_LEVELS[permission_level_name.upper()]
        command = permission_level.check(command)

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
                continue

            if path.is_dir():
                path_list += path.iterdir()
                continue
            if not path.is_file():
                continue

            with path.open() as file:
                cmds |= yaml.safe_load(file)

        self.__cog_commands__ = tuple(
            create_custom_command(name, data) for name, data in cmds.items() if not data.get("disabled", False)
        )
