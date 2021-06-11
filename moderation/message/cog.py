from typing import Optional

from discord import TextChannel, Message, HTTPException, Forbidden, Permissions, Embed, Member, File
from discord.ext import commands
from discord.ext.commands import guild_only, Context, CommandError, UserInputError

from PyDrocsid.cog import Cog
from PyDrocsid.command import docs, reply
from PyDrocsid.converter import Color
from PyDrocsid.translations import t
from PyDrocsid.util import read_normal_message, read_complete_message, check_message_send_permissions
from .colors import Colors
from .permissions import MessagePermission
from ...contributor import Contributor

tg = t.g
t = t.message


class MessageCog(Cog, name="Message Commands"):
    CONTRIBUTORS = [Contributor.Defelo, Contributor.wolflu, Contributor.LoC]

    async def get_message_cancel(self, channel: TextChannel, member: Member) -> tuple[Optional[str], list[File]]:
        content, files = await read_normal_message(self.bot, channel, member)
        if content == t.cancel:
            embed = Embed(title=t.messages, colour=Colors.MessageCommands, description=t.msg_send_cancel)
            await channel.send(embed=embed)
            return None, []

        return content, files

    @commands.group()
    @MessagePermission.send.check
    @guild_only()
    @docs(t.commands.send)
    async def send(self, ctx: Context):
        if ctx.invoked_subcommand is None:
            raise UserInputError

    @send.command(name="text", aliases=["t"])
    @docs(t.commands.send_text)
    async def send_text(self, ctx: Context, channel: TextChannel):
        check_message_send_permissions(channel)

        embed = Embed(
            title=t.messages,
            colour=Colors.MessageCommands,
            description=t.send_message(t.cancel),
        )
        await reply(ctx, embed=embed)
        content, files = await self.get_message_cancel(ctx.channel, ctx.author)

        if content is None:
            return

        try:
            await channel.send(content=content, files=files)
        except (HTTPException, Forbidden):
            raise CommandError(t.msg_could_not_be_sent)
        else:
            embed.description = t.msg_sent
            await reply(ctx, embed=embed)

    @send.command(name="embed", aliases=["e"])
    @docs(t.commands.send_embed)
    async def send_embed(self, ctx: Context, channel: TextChannel, color: Optional[Color] = None):
        check_message_send_permissions(channel, check_embed=True)

        embed = Embed(
            title=t.messages,
            colour=Colors.MessageCommands,
            description=t.send_embed_title(t.cancel),
        )
        await reply(ctx, embed=embed)
        title, _ = await self.get_message_cancel(ctx.channel, ctx.author)
        if title is None:
            return
        if len(title) > 256:
            raise CommandError(t.title_too_long)

        embed.description = t.send_embed_content(t.cancel)
        await reply(ctx, embed=embed)
        content, files = await self.get_message_cancel(ctx.channel, ctx.author)

        if content is None:
            return

        send_embed = Embed(title=title, description=content)

        if files and any(files[0].filename.lower().endswith(ext) for ext in ["jpg", "jpeg", "png", "gif"]):
            send_embed.set_image(url="attachment://" + files[0].filename)

        if color is not None:
            send_embed.colour = color

        try:
            await channel.send(embed=send_embed, files=files)
        except (HTTPException, Forbidden):
            raise CommandError(t.msg_could_not_be_sent)
        else:
            embed.description = t.msg_sent
            await reply(ctx, embed=embed)

    @send.command(name="copy", aliases=["c"])
    @docs(t.commands.send_copy)
    async def send_copy(self, ctx: Context, channel: TextChannel, message: Message):
        content, files, embed = await read_complete_message(message)
        try:
            await channel.send(content=content, embed=embed, files=files)
        except (HTTPException, Forbidden):
            raise CommandError(t.msg_could_not_be_sent)
        else:
            embed = Embed(title=t.messages, colour=Colors.MessageCommands, description=t.msg_sent)
            await reply(ctx, embed=embed)

    @commands.group()
    @MessagePermission.edit.check
    @guild_only()
    @docs(t.commands.edit)
    async def edit(self, ctx: Context):
        if ctx.invoked_subcommand is None:
            raise UserInputError

    @edit.command(name="text", aliases=["t"])
    @docs(t.commands.edit_text)
    async def edit_text(self, ctx: Context, message: Message):
        if message.author != self.bot.user:
            raise CommandError(t.could_not_edit)
        check_message_send_permissions(message.channel, check_send=False)

        embed = Embed(
            title=t.messages,
            colour=Colors.MessageCommands,
            description=t.send_new_message(t.cancel),
        )
        await reply(ctx, embed=embed)
        content, files = await self.get_message_cancel(ctx.channel, ctx.author)

        if content is None:
            return

        if files:
            raise CommandError(t.cannot_edit_files)

        await message.edit(content=content, embed=None)
        embed.description = t.msg_edited
        await reply(ctx, embed=embed)

    @edit.command(name="embed", aliases=["e"])
    @docs(t.commands.edit_embed)
    async def edit_embed(self, ctx: Context, message: Message, color: Optional[Color] = None):
        if message.author != self.bot.user:
            raise CommandError(t.could_not_edit)
        check_message_send_permissions(message.channel, check_send=False, check_embed=True)

        embed = Embed(
            title=t.messages,
            colour=Colors.MessageCommands,
            description=t.send_embed_title(t.cancel),
        )
        await reply(ctx, embed=embed)
        title, _ = await self.get_message_cancel(ctx.channel, ctx.author)

        if title is None:
            return
        if len(title) > 256:
            raise CommandError(t.title_too_long)

        embed.description = t.send_embed_content(t.cancel)
        await reply(ctx, embed=embed)
        content, _ = await self.get_message_cancel(ctx.channel, ctx.author)

        if content is None:
            return

        send_embed = Embed(title=title, description=content)

        if color is not None:
            send_embed.colour = color

        await message.edit(content=None, files=[], embed=send_embed)
        embed.description = t.msg_edited
        await reply(ctx, embed=embed)

    @edit.command(name="copy", aliases=["c"])
    @docs(t.commands.edit_copy)
    async def edit_copy(self, ctx: Context, message: Message, source: Message):
        if message.author != self.bot.user:
            raise CommandError(t.could_not_edit)

        content, files, embed = await read_complete_message(source)
        if files:
            raise CommandError(t.cannot_edit_files)
        await message.edit(content=content, embed=embed)
        embed = Embed(title=t.messages, colour=Colors.MessageCommands, description=t.msg_edited)
        await reply(ctx, embed=embed)

    @commands.command()
    @MessagePermission.delete.check
    @guild_only()
    @docs(t.commands.delete)
    async def delete(self, ctx: Context, message: Message):
        if message.guild is None:
            raise CommandError(t.cannot_delete_dm)

        channel: TextChannel = message.channel
        permissions: Permissions = channel.permissions_for(message.guild.me)
        if message.author != self.bot.user and not permissions.manage_messages:
            raise CommandError(t.could_not_delete)

        await message.delete()
        embed = Embed(title=t.messages, colour=Colors.MessageCommands, description=t.msg_deleted)
        await reply(ctx, embed=embed)
