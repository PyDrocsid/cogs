import base64
import binascii
import json
import re
import string
from typing import Optional

import requests
from aiohttp import ClientSession
from discord import Embed, TextChannel, NotFound, Forbidden, HTTPException, AllowedMentions
from discord.ext import commands
from discord.ext.commands import Context, guild_only, UserInputError, Converter, BadArgument, CommandError, Command
from urllib3.exceptions import LocationParseError

from PyDrocsid.async_thread import run_in_thread
from PyDrocsid.cog import Cog
from PyDrocsid.command import reply, docs, confirm, no_documentation
from PyDrocsid.command_edit import link_response
from PyDrocsid.config import Contributor, Config
from PyDrocsid.database import db, filter_by, select
from PyDrocsid.embeds import send_long_embed
from PyDrocsid.emojis import name_to_emoji
from PyDrocsid.logger import get_logger
from PyDrocsid.permission import BasePermissionLevel
from PyDrocsid.redis import redis
from PyDrocsid.translations import t
from PyDrocsid.util import check_message_send_permissions
from .colors import Colors
from .models import CustomCommand, Alias
from .permissions import CustomCommandsPermission
from ...administration.permissions.cog import PermissionsCog, PermissionLevelConverter
from ...pubsub import send_to_changelog

logger = get_logger(__name__)

tg = t.g
t = t.custom_commands

DISCOHOOK_EMPTY_MESSAGE = (
    "[https://discohook.org/]"
    "(https://discohook.org/?data=eyJtZXNzYWdlcyI6W3siZGF0YSI6eyJjb250ZW50IjpudWxsLCJlbWJlZHMiOm51bGx9fV19)"
)


def warning(text: str) -> Embed:
    return Embed(title=t.warning, description=text, color=Colors.warning)


class CustomCommandConverter(Converter):
    @staticmethod
    async def _get_command(argument: str) -> CustomCommand:
        if cmd := await db.get(CustomCommand, CustomCommand.aliases, name=argument):
            return cmd
        if alias := await db.get(Alias, [Alias.command, CustomCommand.aliases], name=argument):
            return alias.command
        raise BadArgument

    async def convert(self, ctx: Context, argument: str) -> CustomCommand:
        cmd = await CustomCommandConverter._get_command(argument)
        if (await Config.PERMISSION_LEVELS.get_permission_level(ctx.author)).level < cmd.permission_level:
            raise CommandError(t.not_allowed)

        return cmd


async def send_custom_command_message(
    ctx: Context,
    custom_command: CustomCommand,
    channel: TextChannel,
    test: bool = False,
):
    if test and channel != ctx.channel:
        raise ValueError

    messages = json.loads(custom_command.data)

    check_message_send_permissions(channel, check_embed=any(msg.get("embeds") for msg in messages))

    if custom_command.requires_confirmation and not test:
        conf_embed = Embed(title=t.confirmation, description=t.confirm(custom_command.name, channel.mention))
        async with confirm(ctx, conf_embed) as (result, msg):
            if not result:
                conf_embed.description += "\n\n" + t.canceled
                return

            conf_embed.description += "\n\n" + t.confirmed
            if msg:
                await msg.delete(delay=5)

    if custom_command.delete_command and not test:
        try:
            await ctx.message.delete()
        except (NotFound, Forbidden):
            pass

    for msg in messages:
        content = msg.get("content")
        embed: Optional[dict]
        for embed_data in msg.get("embeds") or [None]:
            embed = None
            if embed_data is not None:
                embed: Embed = type("", (), {"to_dict": lambda _: embed_data})()
            elif not content:
                if test:
                    await reply(ctx, embed=warning(t.empty_message(ctx.prefix, custom_command.name)))
                break

            async def _send_message():
                if test:
                    allowed_mentions = AllowedMentions(everyone=False, users=False, roles=False)
                    await reply(ctx, content, embed=embed, allowed_mentions=allowed_mentions)
                elif ctx.channel.id == channel.id:
                    if custom_command.delete_command:
                        await ctx.send(content, embed=embed)
                    else:
                        await reply(ctx, content, embed=embed)
                else:
                    msg = await channel.send(content, embed=embed)
                    if not custom_command.delete_command:
                        await link_response(ctx, msg)
                        await ctx.message.add_reaction(name_to_emoji["white_check_mark"])

            try:
                await _send_message()
            except HTTPException:
                # embed could be empty

                if test and not content:
                    await reply(ctx, embed=warning(t.empty_message(ctx.prefix, custom_command.name)))
                else:
                    embed = None
                    try:
                        await _send_message()
                    except HTTPException:
                        raise CommandError(t.could_not_send_message)
                    else:
                        if test:
                            await reply(ctx, embed=warning(t.empty_embed(ctx.prefix, custom_command.name)))

            content = None


def create_custom_command(custom_command: CustomCommand):
    async def with_channel_parameter(_, ctx: Context, channel: TextChannel):
        await send_custom_command_message(ctx, custom_command, channel)

    async def without_channel_parameter(_, ctx: Context):
        channel = ctx.bot.get_channel(custom_command.channel_id) or ctx.channel
        await send_custom_command_message(ctx, custom_command, channel)

    command = with_channel_parameter if custom_command.channel_parameter else without_channel_parameter
    if description := custom_command.description:
        command = docs(description)(command)

    level: BasePermissionLevel
    for level in Config.PERMISSION_LEVELS:
        if level.level == custom_command.permission_level:
            command = level.check(command)
            break

    command = no_documentation(command)
    command = commands.command(name=custom_command.name, aliases=custom_command.alias_names)(command)

    return command


async def load_discohook(url: str) -> str:
    if not re.match(r"^https://share.discohook.app/go/[a-zA-Z\d]+$", url):
        raise CommandError(t.invalid_url_instructions(DISCOHOOK_EMPTY_MESSAGE))

    try:
        url = await run_in_thread(lambda: requests.head(url, allow_redirects=True).url)
    except (KeyError, AttributeError, requests.RequestException, UnicodeError, ConnectionError, LocationParseError):
        raise CommandError(t.invalid_url)

    if not (match := re.match(r"^https://discohook.org/\?data=([a-zA-Z\d\-_]+)$", url)):
        raise CommandError(t.invalid_url)

    try:
        messages = [msg["data"] for msg in json.loads(base64.urlsafe_b64decode(match.group(1) + "=="))["messages"]]
    except (binascii.Error, json.JSONDecodeError, KeyError):
        raise CommandError(t.invalid_url)

    if not isinstance(messages, list):
        raise CommandError(t.invalid_url)

    for msg in messages:
        if not isinstance(msg.get("content") or "", str):
            raise CommandError(t.invalid_url)

        for embed in msg.get("embeds") or []:
            if not isinstance(embed, dict):
                raise CommandError(t.invalid_url)

    return json.dumps(messages)


async def create_discohook_url(command: CustomCommand) -> Optional[str]:
    if url := await redis.get(key := f"custom_command_discohook_url:{command.id}"):
        return url

    data = json.dumps({"messages": [{"data": msg} for msg in json.loads(command.data)]})
    url = "https://discohook.org/?data=" + base64.urlsafe_b64encode(data.encode()).decode().rstrip("=")
    async with ClientSession() as session, session.post(
        "https://share.discohook.app/create",
        json={"url": url},
    ) as response:
        url: Optional[str] = (await response.json()).get("url")
        if not response.ok or not url:
            return None

    await redis.setex(key, 24 * 60 * 60, url)

    return url


def test_name(name: str):
    if not name:
        raise UserInputError
    if len(name) > 32:
        raise CommandError(t.invalid_length)

    valid_chars = set(string.ascii_letters + string.digits + string.punctuation) - {"`"}
    if set(name) - valid_chars:
        raise CommandError(t.invalid_chars)


class CustomCommandsCog(Cog, name="Custom Commands"):
    CONTRIBUTORS = [Contributor.Defelo]
    DEPENDENCIES = [PermissionsCog]

    def __init__(self):
        self.__cog_commands__ = list(self.__cog_commands__)

    async def on_ready(self):
        custom_command: CustomCommand
        async for custom_command in await db.stream(filter_by(CustomCommand, CustomCommand.aliases, disabled=False)):
            self.load_command(custom_command)

    def load_command(self, command: CustomCommand):
        if command.disabled:
            return

        cmd = create_custom_command(command)
        cmd.cog = self
        self.bot.add_command(cmd)
        self.__cog_commands__.append(cmd)

    def unload_command(self, command: CustomCommand):
        self.bot.remove_command(command.name)
        self.__cog_commands__ = [x for x in self.__cog_commands__ if x.name != command.name]

    def reload_command(self, command: CustomCommand):
        self.unload_command(command)
        self.load_command(command)

    async def test_command_already_exists(self, name: str):
        cmd: Command
        for cmd in self.bot.commands:
            if name in [cmd.name, *cmd.aliases]:
                raise CommandError(t.already_exists)

        if await db.exists(filter_by(CustomCommand, name=name)):
            raise CommandError(t.already_exists)
        if await db.exists(filter_by(Alias, name=name)):
            raise CommandError(t.already_exists)

    @commands.group(aliases=["cc"])
    @CustomCommandsPermission.read.check
    @guild_only()
    @docs(t.commands.custom_commands)
    async def custom_commands(self, ctx: Context):
        if ctx.subcommand_passed is not None:
            if ctx.invoked_subcommand is None:
                raise UserInputError
            return

        permission_level: int = (await Config.PERMISSION_LEVELS.get_permission_level(ctx.author)).level
        embed = Embed(title=t.custom_commands, colour=Colors.CustomCommands)
        out = []
        custom_command: CustomCommand
        async for custom_command in await db.stream(select(CustomCommand, CustomCommand.aliases)):
            if permission_level < custom_command.permission_level:
                continue

            emoji = ":small_orange_diamond:" if not custom_command.disabled else ":small_blue_diamond:"
            names = ", ".join(f"`{name}`" for name in [custom_command.name, *custom_command.alias_names])
            out.append(f"{emoji} {names}")

        if not out:
            embed.description = t.no_custom_commands
            embed.colour = Colors.error
        else:
            embed.description = "\n".join(out)

        await send_long_embed(ctx, embed=embed)

    @custom_commands.command(name="add", aliases=["+"])
    @CustomCommandsPermission.write.check
    @docs(t.commands.add(DISCOHOOK_EMPTY_MESSAGE))
    async def custom_commands_add(self, ctx: Context, name: str, discohook_url: str, public: bool = True):
        test_name(name)
        await self.test_command_already_exists(name)

        permission_level: BasePermissionLevel
        if public:
            permission_level = Config.PERMISSION_LEVELS.PUBLIC
        else:
            permission_level = await Config.PERMISSION_LEVELS.get_permission_level(ctx.author)

        command = await CustomCommand.create(name, await load_discohook(discohook_url), False, permission_level)
        self.load_command(command)

        await send_to_changelog(ctx.guild, t.log.created(name))
        await ctx.message.add_reaction(name_to_emoji["white_check_mark"])

    @custom_commands.command(name="show", aliases=["s", "view", "v", "?"])
    @docs(t.commands.show)
    async def custom_commands_show(self, ctx: Context, command: CustomCommandConverter):
        command: CustomCommand

        embed = Embed(title=t.custom_command, colour=Colors.CustomCommands)

        if url := await create_discohook_url(command):
            embed.add_field(name=t.message, value=url, inline=False)

        embed.add_field(name=tg.status, value=tg.disabled if command.disabled else tg.enabled)
        embed.add_field(name=t.name, value=command.name)
        if command.aliases:
            embed.add_field(name=t.aliases, value=", ".join(f"`{alias}`" for alias in command.alias_names))
        if command.description:
            embed.add_field(name=t.description, value=command.description, inline=False)

        embed.add_field(name=t.channel_parameter, value=tg.enabled if command.channel_parameter else tg.disabled)
        if (channel := ctx.guild.get_channel(command.channel_id)) and not command.channel_parameter:
            embed.add_field(name=t.channel, value=channel.mention)

        embed.add_field(
            name=t.requires_confirmation,
            value=tg.enabled if command.requires_confirmation else tg.disabled,
        )
        embed.add_field(name=t.delete_command, value=tg.enabled if command.delete_command else tg.disabled)

        level: BasePermissionLevel
        for level in Config.PERMISSION_LEVELS:
            if level.level == command.permission_level:
                embed.add_field(
                    name=t.required_permission_level,
                    value=f":small_orange_diamond: **{level.description}**",
                    inline=False,
                )
                break

        await send_long_embed(ctx, embed=embed)

    @custom_commands.command(name="test", aliases=["t"])
    @docs(t.commands.test)
    async def custom_commands_test(self, ctx: Context, command: CustomCommandConverter):
        command: CustomCommand

        await send_custom_command_message(ctx, command, ctx.channel, test=True)

    @custom_commands.group(name="edit", aliases=["e"])
    @CustomCommandsPermission.write.check
    @docs(t.commands.edit_)
    async def custom_commands_edit(self, ctx: Context):
        if ctx.invoked_subcommand is None:
            raise UserInputError

    @custom_commands_edit.command(name="enabled", aliases=["e"])
    @docs(t.commands.edit.enabled)
    async def custom_commands_edit_enabled(self, ctx: Context, command: CustomCommandConverter, enabled: bool):
        command: CustomCommand

        if not command.disabled and enabled:
            raise CommandError(t.already_enabled)
        if command.disabled and not enabled:
            raise CommandError(t.already_disabled)

        command.disabled = not enabled
        if enabled:
            self.load_command(command)
            await send_to_changelog(ctx.guild, t.log.enabled(command.name))
        else:
            self.unload_command(command)
            await send_to_changelog(ctx.guild, t.log.disabled(command.name))

        await ctx.message.add_reaction(name_to_emoji["white_check_mark"])

    @custom_commands_edit.command(name="name", aliases=["n"])
    @docs(t.commands.edit.name)
    async def custom_commands_edit_name(self, ctx: Context, command: CustomCommandConverter, *, name: str):
        command: CustomCommand

        test_name(name)
        await self.test_command_already_exists(name)

        old_name: str = command.name

        self.unload_command(command)
        command.name = name
        self.load_command(command)
        await send_to_changelog(ctx.guild, t.log.renamed(old_name, name))
        await ctx.message.add_reaction(name_to_emoji["white_check_mark"])

    @custom_commands_edit.command(name="description", aliases=["desc", "d"])
    @docs(t.commands.edit.description)
    async def custom_commands_edit_description(
        self,
        ctx: Context,
        command: CustomCommandConverter,
        *,
        description: str = None,
    ):
        command: CustomCommand

        if description and len(description) > 256:
            raise CommandError(t.invalid_length_description)

        command.description = description
        self.reload_command(command)
        if description:
            await send_to_changelog(ctx.guild, t.log.description.set(command.name, description))
        else:
            await send_to_changelog(ctx.guild, t.log.description.unset(command.name))
        await ctx.message.add_reaction(name_to_emoji["white_check_mark"])

    @custom_commands_edit.command(name="channel_parameter", aliases=["cp"])
    @docs(t.commands.edit.channel_parameter_enabled)
    async def custom_commands_edit_channel_parameter(
        self,
        ctx: Context,
        command: CustomCommandConverter,
        enabled: bool,
    ):
        command: CustomCommand

        if command.channel_parameter and enabled:
            raise CommandError(t.parameter_already_enabled)
        if not command.channel_parameter and not enabled:
            raise CommandError(t.parameter_already_disabled)

        command.channel_parameter = enabled
        self.reload_command(command)
        if enabled:
            await send_to_changelog(ctx.guild, t.log.channel_parameter.enabled(command.name))
        else:
            await send_to_changelog(ctx.guild, t.log.channel_parameter.disabled(command.name))
        await ctx.message.add_reaction(name_to_emoji["white_check_mark"])

    @custom_commands_edit.command(name="channel", aliases=["c"])
    @docs(t.commands.edit.channel)
    async def custom_commands_edit_channel(
        self,
        ctx: Context,
        command: CustomCommandConverter,
        *,
        channel: TextChannel = None,
    ):
        command: CustomCommand

        if command.channel_parameter:
            raise CommandError(t.channel_parameter_enabled)

        command.channel_id = channel and channel.id
        self.reload_command(command)
        if channel:
            await send_to_changelog(ctx.guild, t.log.channel.set(command.name, channel.mention))
        else:
            await send_to_changelog(ctx.guild, t.log.channel.unset(command.name))
        await ctx.message.add_reaction(name_to_emoji["white_check_mark"])

    @custom_commands_edit.command(name="delete_command", aliases=["dc"])
    @docs(t.commands.edit.delete_command)
    async def custom_commands_edit_delete_command(self, ctx: Context, command: CustomCommandConverter, delete: bool):
        command: CustomCommand

        if command.delete_command and delete:
            raise CommandError(t.already_enabled)
        if not command.delete_command and not delete:
            raise CommandError(t.already_disabled)

        command.delete_command = delete
        self.reload_command(command)
        if delete:
            await send_to_changelog(ctx.guild, t.log.delete_command.enabled(command.name))
        else:
            await send_to_changelog(ctx.guild, t.log.delete_command.disabled(command.name))
        await ctx.message.add_reaction(name_to_emoji["white_check_mark"])

    @custom_commands_edit.command(name="permission_level", aliases=["pl"])
    @docs(t.commands.edit.permission_level)
    async def custom_commands_edit_permission_level(
        self,
        ctx: Context,
        command: CustomCommandConverter,
        level: PermissionLevelConverter,
    ):
        command: CustomCommand
        level: BasePermissionLevel

        if not await level.check_permissions(ctx.author):
            raise CommandError(t.not_allowed_permission_level)

        command.permission_level = level.level
        self.reload_command(command)
        await send_to_changelog(ctx.guild, t.log.permission_level(command.name, level.description))
        await ctx.message.add_reaction(name_to_emoji["white_check_mark"])

    @custom_commands_edit.command(name="requires_confirmation", aliases=["rc"])
    @docs(t.commands.edit.requires_confirmation)
    async def custom_commands_edit_requires_confirmation(
        self,
        ctx: Context,
        command: CustomCommandConverter,
        enabled: bool,
    ):
        command: CustomCommand

        if command.requires_confirmation and enabled:
            raise CommandError(t.already_enabled)
        if not command.requires_confirmation and not enabled:
            raise CommandError(t.already_disabled)

        command.requires_confirmation = enabled
        self.reload_command(command)
        if enabled:
            await send_to_changelog(ctx.guild, t.log.requires_confirmation.enabled(command.name))
        else:
            await send_to_changelog(ctx.guild, t.log.requires_confirmation.disabled(command.name))
        await ctx.message.add_reaction(name_to_emoji["white_check_mark"])

    @custom_commands_edit.command(name="text", aliases=["t", "content", "data"])
    @docs(t.commands.edit.data(DISCOHOOK_EMPTY_MESSAGE))
    async def custom_commands_edit_data(self, ctx: Context, command: CustomCommandConverter, discohook_url: str):
        command: CustomCommand

        command.data = await load_discohook(discohook_url)
        self.reload_command(command)
        await redis.delete(f"custom_command_discohook_url:{command.id}")
        await send_to_changelog(ctx.guild, t.log.data(command.name))
        await ctx.message.add_reaction(name_to_emoji["white_check_mark"])

    @custom_commands.command(name="alias", aliases=["a"])
    @CustomCommandsPermission.write.check
    @docs(t.commands.alias)
    async def custom_commands_alias(self, ctx: Context, command: CustomCommandConverter, alias: str):
        command: CustomCommand

        test_name(alias)
        await self.test_command_already_exists(alias)

        await command.add_alias(alias)
        self.reload_command(command)
        await send_to_changelog(ctx.guild, t.log.alias(alias, command.name))
        await ctx.message.add_reaction(name_to_emoji["white_check_mark"])

    @custom_commands.command(name="unalias", aliases=["u"])
    @CustomCommandsPermission.write.check
    @docs(t.commands.unalias)
    async def custom_commands_unalias(self, ctx: Context, alias: str):
        row: Optional[Alias] = await db.get(Alias, [Alias.command, CustomCommand.aliases], name=alias)
        if not row:
            raise CommandError(t.alias_not_found)

        command: CustomCommand = row.command
        await db.delete(row)
        command.aliases.remove(row)
        self.reload_command(command)
        await send_to_changelog(ctx.guild, t.log.unalias(alias, command.name))
        await ctx.message.add_reaction(name_to_emoji["white_check_mark"])

    @custom_commands.command(name="remove", aliases=["r", "del", "d", "-"])
    @CustomCommandsPermission.write.check
    @docs(t.commands.remove)
    async def custom_commands_remove(self, ctx: Context, command: CustomCommandConverter):
        command: CustomCommand

        await db.delete(command)
        self.unload_command(command)
        await send_to_changelog(ctx.guild, t.log.deleted(command.name))
        await ctx.message.add_reaction(name_to_emoji["white_check_mark"])
