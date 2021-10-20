from typing import Optional

from discord import Member, TextChannel, Role, Guild, HTTPException, Forbidden, Embed
from discord.ext import commands
from discord.ext.commands import guild_only, Context, CommandError, UserInputError

from PyDrocsid.cog import Cog
from PyDrocsid.command import reply
from PyDrocsid.converter import Color
from PyDrocsid.database import db, select
from PyDrocsid.embeds import send_long_embed
from PyDrocsid.translations import t
from PyDrocsid.util import read_normal_message, attachment_to_file
from .colors import Colors
from .models import NewsAuthorization
from .permissions import NewsPermission
from ...contributor import Contributor
from ...pubsub import send_to_changelog

tg = t.g
t = t.news


class NewsCog(Cog, name="News"):
    CONTRIBUTORS = [Contributor.Defelo, Contributor.wolflu]

    @commands.group()
    @guild_only()
    async def news(self, ctx: Context):
        """
        manage news channels
        """

        if ctx.invoked_subcommand is None:
            raise UserInputError

    @news.group(name="auth", aliases=["a"])
    @NewsPermission.read.check
    async def news_auth(self, ctx: Context):
        """
        manage authorized users and channels
        """

        if ctx.invoked_subcommand is None:
            raise UserInputError

    @news_auth.command(name="list", aliases=["l", "?"])
    async def news_auth_list(self, ctx: Context):
        """
        list authorized users and channels
        """

        out = []
        guild: Guild = ctx.guild
        async for authorization in await db.stream(select(NewsAuthorization)):
            text_channel: Optional[TextChannel] = guild.get_channel(authorization.channel_id)
            member: Optional[Member] = guild.get_member(authorization.user_id)
            if text_channel is None or member is None:
                await db.delete(authorization)
                continue
            line = f":small_orange_diamond: {member.mention} -> {text_channel.mention}"
            if authorization.notification_role_id is not None:
                role: Optional[Role] = guild.get_role(authorization.notification_role_id)
                if role is None:
                    await db.delete(authorization)
                    continue
                line += f" ({role.mention})"
            out.append(line)
        embed = Embed(title=t.news, colour=Colors.News)
        if out:
            embed.description = "\n".join(out)
        else:
            embed.colour = Colors.error
            embed.description = t.no_news_authorizations
        await send_long_embed(ctx, embed)

    @news_auth.command(name="add", aliases=["a", "+"])
    @NewsPermission.write.check
    async def news_auth_add(self, ctx: Context, user: Member, channel: TextChannel, notification_role: Optional[Role]):
        """
        authorize a new user to send news to a specific channel
        """

        if await db.exists(select(NewsAuthorization).filter_by(user_id=user.id, channel_id=channel.id)):
            raise CommandError(t.news_already_authorized)
        if not channel.permissions_for(channel.guild.me).send_messages:
            raise CommandError(t.news_not_added_no_permissions)

        role_id = notification_role.id if notification_role is not None else None

        await NewsAuthorization.create(user.id, channel.id, role_id)
        embed = Embed(title=t.news, colour=Colors.News, description=t.news_authorized)
        await reply(ctx, embed=embed)
        await send_to_changelog(ctx.guild, t.log_news_authorized(user.mention, channel.mention))

    @news_auth.command(name="remove", aliases=["del", "r", "d", "-"])
    @NewsPermission.write.check
    async def news_auth_remove(self, ctx: Context, user: Member, channel: TextChannel):
        """
        remove user authorization
        """

        authorization: Optional[NewsAuthorization] = await db.first(
            select(NewsAuthorization).filter_by(user_id=user.id, channel_id=channel.id),
        )
        if authorization is None:
            raise CommandError(t.news_not_authorized)

        await db.delete(authorization)
        embed = Embed(title=t.news, colour=Colors.News, description=t.news_unauthorized)
        await reply(ctx, embed=embed)
        await send_to_changelog(ctx.guild, t.log_news_unauthorized(user.mention, channel.mention))

    @news.command(name="send", aliases=["s"])
    async def news_send(
        self,
        ctx: Context,
        channel: TextChannel,
        color: Optional[Color] = None,
        *,
        message: Optional[str],
    ):
        """
        send a news message
        """

        authorization: Optional[NewsAuthorization] = await db.first(
            select(NewsAuthorization).filter_by(user_id=ctx.author.id, channel_id=channel.id),
        )
        if authorization is None:
            raise CommandError(t.news_you_are_not_authorized)

        if message is None:
            message = ""

        embed = Embed(title=t.news, colour=Colors.News, description="")
        if not message and not ctx.message.attachments:
            embed.description = t.send_message
            await reply(ctx, embed=embed)
            message, files = await read_normal_message(self.bot, ctx.channel, ctx.author)
        else:
            files = [await attachment_to_file(attachment) for attachment in ctx.message.attachments]

        content = ""
        send_embed = Embed(title=t.news, description=message, colour=Colors.News)
        send_embed.set_footer(text=t.sent_by(ctx.author, ctx.author.id), icon_url=ctx.author.display_avatar.url)

        if authorization.notification_role_id is not None:
            role: Optional[Role] = ctx.guild.get_role(authorization.notification_role_id)
            if role is not None:
                content = role.mention

        send_embed.colour = color if color is not None else Colors.News

        if files and any(files[0].filename.lower().endswith(ext) for ext in ["jpg", "jpeg", "png", "gif"]):
            send_embed.set_image(url="attachment://" + files[0].filename)

        try:
            await channel.send(content=content, embed=send_embed, files=files)
        except (HTTPException, Forbidden):
            raise CommandError(t.msg_could_not_be_sent)
        else:
            embed.description = t.msg_sent
            await reply(ctx, embed=embed)
