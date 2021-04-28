from typing import Optional, Tuple, Dict, Set

from discord import Message, Role, PartialEmoji, TextChannel, Member, NotFound, Embed, HTTPException, Forbidden
from discord.ext import commands
from discord.ext.commands import guild_only, Context, CommandError, UserInputError

from PyDrocsid.cog import Cog
from PyDrocsid.database import db, select
from PyDrocsid.emoji_converter import EmojiConverter
from PyDrocsid.events import StopEventHandling
from PyDrocsid.logger import get_logger
from PyDrocsid.translations import t
from PyDrocsid.util import send_long_embed, reply, check_role_assignable, docs
from .colors import Colors
from .models import ReactionRole
from .permissions import ReactionRolePermission
from ...contributor import Contributor
from ...pubsub import send_to_changelog

tg = t.g
t = t.reactionrole

logger = get_logger(__name__)


async def get_role(message: Message, emoji: PartialEmoji) -> tuple[Optional[Role], Optional[ReactionRole]]:
    link: Optional[ReactionRole] = await ReactionRole.get(message.channel.id, message.id, str(emoji))
    if link is None:
        return None, None

    role: Optional[Role] = message.guild.get_role(link.role_id)
    if role is None:
        await db.delete(link)
        return None, None

    return role, link


class ReactionRoleCog(Cog, name="ReactionRole"):
    CONTRIBUTORS = [Contributor.Defelo, Contributor.wolflu]

    async def on_raw_reaction_add(self, message: Message, emoji: PartialEmoji, member: Member):
        if member.bot or message.guild is None:
            return

        role, link = await get_role(message, emoji)
        if not role or not link:
            return

        try:
            if link.reverse:
                await member.remove_roles(role)
            else:
                await member.add_roles(role)
        except (Forbidden, HTTPException):
            logger.exception(
                f"could not manage role {role} ({role.id}) on {member} ({member.id}) "
                f"(channel: {message.channel.id}, msg: {message.id}, emoji: {emoji})",
            )

        if link.auto_remove:
            try:
                await message.remove_reaction(emoji, member)
            except (HTTPException, Forbidden, NotFound):
                logger.exception(
                    f"could not remove emoji {emoji} from {message.channel.id}/{message.id} "
                    f"(member: {member} ({member.id}), role: {role} ({role.id}))",
                )

        raise StopEventHandling

    async def on_raw_reaction_remove(self, message: Message, emoji: PartialEmoji, member: Member):
        if member.bot or message.guild is None:
            return

        role, link = await get_role(message, emoji)
        if not role or not link or link.auto_remove:
            return

        try:
            if link.reverse:
                await member.add_roles(role)
            else:
                await member.remove_roles(role)
        except (Forbidden, HTTPException):
            logger.exception(
                f"could not manage role {role} ({role.id}) on {member} ({member.id}) "
                f"(channel: {message.channel.id}, msg: {message.id}, emoji: {emoji})",
            )

        raise StopEventHandling

    @commands.group(aliases=["rr"])
    @ReactionRolePermission.read.check
    @guild_only()
    @docs(t.commands.reactionrole)
    async def reactionrole(self, ctx: Context):
        if ctx.subcommand_passed is not None:
            if ctx.invoked_subcommand is None:
                raise UserInputError
            return

        embed = Embed(title=t.reactionrole, colour=Colors.ReactionRole)
        channels: Dict[TextChannel, Dict[Message, Set[str]]] = {}
        message_cache: Dict[Tuple[int, int], Message] = {}
        async for link in await db.stream(select(ReactionRole)):  # type: ReactionRole
            channel: Optional[TextChannel] = ctx.guild.get_channel(link.channel_id)
            if channel is None:
                await db.delete(link)
                continue

            key = link.channel_id, link.message_id
            if key not in message_cache:
                try:
                    message_cache[key] = await channel.fetch_message(link.message_id)
                except HTTPException:
                    await db.delete(link)
                    continue
            msg = message_cache[key]

            if ctx.guild.get_role(link.role_id) is None:
                await db.delete(link)
                continue

            channels.setdefault(channel, {}).setdefault(msg, set())
            channels[channel][msg].add(link.emoji)

        if not channels:
            embed.colour = Colors.error
            embed.description = t.no_reactionrole_links
        else:
            out = []
            for channel, messages in channels.items():
                value = channel.mention + "\n"
                for msg, emojis in messages.items():
                    value += f"[{msg.id}]({msg.jump_url}): {' '.join(emojis)}\n"
                out.append(value)
            embed.description = "\n".join(out)

        await send_long_embed(ctx, embed)

    @reactionrole.command(name="list", aliases=["l", "?"])
    @docs(t.commands.reactionrole_list)
    async def reactionrole_list(self, ctx: Context, msg: Message):
        embed = Embed(title=t.reactionrole, colour=Colors.ReactionRole)
        out = []
        link: ReactionRole
        async for link in await db.stream(select(ReactionRole).filter_by(channel_id=msg.channel.id, message_id=msg.id)):
            channel: Optional[TextChannel] = ctx.guild.get_channel(link.channel_id)
            if channel is None:
                await db.delete(link)
                continue

            try:
                await channel.fetch_message(link.message_id)
            except HTTPException:
                await db.delete(link)
                continue

            role: Optional[Role] = ctx.guild.get_role(link.role_id)
            if role is None:
                await db.delete(link)
                continue

            flags = [t.reverse] * link.reverse + [t.auto_remove] * link.auto_remove
            out.append(t.rr_link(link.emoji, role.mention) + f" ({', '.join(flags)})" * bool(flags))

        if not out:
            embed.colour = Colors.error
            embed.description = t.no_reactionrole_links_for_msg
        else:
            embed.description = "\n".join(out)

        await send_long_embed(ctx, embed)

    @reactionrole.command(name="add", aliases=["a", "+"])
    @ReactionRolePermission.write.check
    @docs(t.commands.reactionrole_add)
    async def reactionrole_add(
        self,
        ctx: Context,
        msg: Message,
        emoji: EmojiConverter,
        role: Role,
        reverse: bool,
        auto_remove: bool,
    ):
        emoji: PartialEmoji

        if await ReactionRole.get(msg.channel.id, msg.id, str(emoji)):
            raise CommandError(t.rr_link_already_exists)
        if not msg.channel.permissions_for(msg.guild.me).add_reactions:
            raise CommandError(t.rr_link_not_created_no_permissions)

        check_role_assignable(role)

        await ReactionRole.create(msg.channel.id, msg.id, str(emoji), role.id, reverse, auto_remove)
        await msg.add_reaction(emoji)
        embed = Embed(title=t.reactionrole, colour=Colors.ReactionRole, description=t.rr_link_created)
        await reply(ctx, embed=embed)
        await send_to_changelog(ctx.guild, t.log_rr_link_created(emoji, role.id, msg.jump_url, msg.channel.mention))

    @reactionrole.command(name="remove", aliases=["r", "del", "d", "-"])
    @ReactionRolePermission.write.check
    @docs(t.commands.reactionrole_remove)
    async def reactionrole_remove(self, ctx: Context, msg: Message, emoji: EmojiConverter):
        emoji: PartialEmoji

        if not (link := await ReactionRole.get(msg.channel.id, msg.id, str(emoji))):
            raise CommandError(t.rr_link_not_found)

        await db.delete(link)
        for reaction in msg.reactions:
            if str(emoji) == str(reaction.emoji):
                await reaction.clear()
        embed = Embed(title=t.reactionrole, colour=Colors.ReactionRole, description=t.rr_link_removed)
        await reply(ctx, embed=embed)
        await send_to_changelog(
            ctx.guild,
            t.log_rr_link_removed(emoji, link.role_id, msg.jump_url, msg.channel.mention),
        )
