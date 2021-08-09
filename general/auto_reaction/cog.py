import re
from typing import Optional

from PyDrocsid.emojis import emoji_to_name
from PyDrocsid.cog import Cog
from PyDrocsid.command import docs
from PyDrocsid.database import db, select
from PyDrocsid.emojis import name_to_emoji
from PyDrocsid.translations import t
from discord import Message, TextChannel, Forbidden
from discord.ext import commands
from discord.ext.commands import Context, guild_only, UserInputError

from .models import AutoReactionChannel, AutoReaction, AutoReactionLink
from .permission import AutoReactionPermission
from ...contributor import Contributor
from ...pubsub import send_to_changelog

tg = t.g
t = t.auto_reaction


class AutoreactionCog(Cog, name="Autoreaction"):
    CONTRIBUTORS = [Contributor.Florian, Contributor.Defelo]

    @commands.group(aliases=["aur"])
    @AutoReactionPermission.read.check
    @guild_only()
    @docs(t.commands.auto_reaction)
    async def auto_reaction(self, ctx: Context):
        if ctx.invoked_subcommand is None:
            raise UserInputError

    @auto_reaction.command(name="add", aliases=["a", "+"])
    @AutoReactionPermission.write.check
    @docs(t.commands.auto_reaction_add)
    async def autoreaction_add(self, ctx: Context, channel: TextChannel, reactions: str):

        channel_exists: Optional[AutoReactionChannel] = (
                await db.get(AutoReactionChannel, channel=channel.id) is not None
        )
        if not channel_exists:
            await AutoReactionChannel.create(channel.id)

        db_channel: Optional[AutoReactionChannel] = await db.get(AutoReactionChannel, channel=channel.id)
        for reaction in reactions:
            if not reaction.strip() or reaction not in emoji_to_name:
                continue
            reaction_exists: Optional[AutoReaction] = await db.get(AutoReaction, reaction=reaction) is not None
            if not reaction_exists:
                await AutoReaction.create(reaction)
            db_reaction: Optional[AutoReaction] = await db.get(AutoReaction, reaction=reaction)
            await AutoReactionLink.create(db_channel.id, db_reaction.id)
            await ctx.message.add_reaction(name_to_emoji["white_check_mark"])

    async def on_message(self, message: Message):
        channel = message.channel
        db_channel: Optional[AutoReactionChannel] = await db.get(AutoReactionChannel, channel=channel.id)
        if db_channel:
            async for link_reaction in await db.stream(select(AutoReactionLink).filter_by(channel_id=db_channel.id)):
                auto_reaction = await db.get(AutoReaction, id=link_reaction.autoreaction_id)
                try:
                    await message.add_reaction(auto_reaction.reaction)
                except Forbidden:
                    await send_to_changelog(message.guild, t.no_permissions(message.channel))

    @auto_reaction.command(name="remove", aliases=["r", "-"])
    @AutoReactionPermission.write.check
    @docs(t.commands.auto_reaction_remove)
    async def autoreaction_remove(self, ctx: Context, channel: TextChannel, reactions: str):
        db_channel = await db.get(AutoReactionChannel, channel=channel.id)
        for reaction in reactions:
            reaction_db: Optional[AutoReaction] = await db.get(AutoReaction, reaction=reaction)
            if reaction_db and db_channel:
                auto_reaction_link = await db.get(AutoReactionLink, autoreaction_id=reaction_db.id,
                                                  channel_id=db_channel.id)
                if auto_reaction_link:
                    await db.delete(auto_reaction_link)
                    await ctx.message.add_reaction(name_to_emoji["white_check_mark"])
