from typing import Optional

from discord import Embed, Forbidden, Guild, Member, Role, TextChannel
from discord.ext import commands
from discord.ext.commands import CommandError, Context, UserInputError, guild_only

from PyDrocsid.cog import Cog
from PyDrocsid.config import Contributor
from PyDrocsid.database import db, filter_by, select
from PyDrocsid.embeds import send_long_embed
from PyDrocsid.emojis import name_to_emoji
from PyDrocsid.translations import t
from PyDrocsid.util import check_message_send_permissions

from .colors import Colors
from .models import RoleNotification
from .permissions import RoleNotificationsPermission
from ...pubsub import send_alert, send_to_changelog

tg = t.g
t = t.role_notifications


class RoleNotificationsCog(Cog, name="Role Notifications"):
    CONTRIBUTORS = [Contributor.Defelo]

    async def on_member_role_add(self, member: Member, role: Role):
        link: RoleNotification
        async for link in await db.stream(filter_by(RoleNotification, role_id=role.id)):
            channel: Optional[TextChannel] = self.bot.get_channel(link.channel_id)
            if channel is None:
                continue

            role_name = role.mention if link.ping_role else f"`@{role}`"
            user_name = member.mention if link.ping_user else f"`@{member}`"
            try:
                await channel.send(t.rn_role_added(role_name, user_name))
            except Forbidden:
                await send_alert(member.guild, t.cannot_send(channel.mention))

    async def on_member_role_remove(self, member: Member, role: Role):
        link: RoleNotification
        async for link in await db.stream(filter_by(RoleNotification, role_id=role.id)):
            channel: Optional[TextChannel] = self.bot.get_channel(link.channel_id)
            if channel is None:
                continue

            role_name = role.mention if link.ping_role else f"`@{role}`"
            user_name = member.mention if link.ping_user else f"`@{member}`"
            try:
                await channel.send(t.rn_role_removed(role_name, user_name))
            except Forbidden:
                await send_alert(member.guild, t.cannot_send(channel.mention))

    @commands.group(aliases=["rn"])
    @RoleNotificationsPermission.read.check
    @guild_only()
    async def role_notifications(self, ctx: Context):
        """
        manage role notifications
        """

        if ctx.subcommand_passed is not None:
            if ctx.invoked_subcommand is None:
                raise UserInputError
            return

        embed = Embed(title=t.rn_links, color=Colors.RoleNotifications)
        out = []
        guild: Guild = ctx.guild
        link: RoleNotification
        async for link in await db.stream(select(RoleNotification)):
            if guild.get_channel(link.channel_id) is None or guild.get_role(link.role_id) is None:
                await db.delete(link)
                continue

            flags = [t.rn_ping_role] * link.ping_role + [t.rn_ping_user] * link.ping_user
            out.append(f"<@&{link.role_id}> -> <#{link.channel_id}>" + (" (" + ", ".join(flags) + ")") * bool(flags))

        if not out:
            embed.description = t.rn_no_links
            embed.colour = Colors.error
        else:
            embed.description = "\n".join(out)
        await send_long_embed(ctx, embed)

    @role_notifications.command(name="add", aliases=["a", "+"])
    @RoleNotificationsPermission.write.check
    async def role_notifications_add(
        self, ctx: Context, role: Role, channel: TextChannel, ping_role: bool, ping_user: bool
    ):
        """
        add a role notification link
        """

        check_message_send_permissions(channel)

        if await db.exists(filter_by(RoleNotification, role_id=role.id, channel_id=channel.id)):
            raise CommandError(t.link_already_exists)

        await RoleNotification.create(role.id, channel.id, ping_role, ping_user)
        await ctx.message.add_reaction(name_to_emoji["white_check_mark"])
        await send_to_changelog(ctx.guild, t.log_rn_created(role, channel.mention))

    @role_notifications.command(name="remove", aliases=["del", "r", "d", "-"])
    @RoleNotificationsPermission.write.check
    async def role_notifications_remove(self, ctx: Context, role: Role, channel: TextChannel):
        """
        remove a role notification link
        """

        link: Optional[RoleNotification] = await db.get(RoleNotification, role_id=role.id, channel_id=channel.id)
        if link is None:
            raise CommandError(t.link_not_found)

        name: str = role.name if (role := ctx.guild.get_role(link.role_id)) else "deleted-role"

        await db.delete(link)
        await ctx.message.add_reaction(name_to_emoji["white_check_mark"])
        await send_to_changelog(ctx.guild, t.log_rn_removed(name, channel.mention))
