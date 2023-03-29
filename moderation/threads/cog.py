import asyncio
from datetime import datetime
from typing import Optional

from discord import Embed, Forbidden, Role, TextChannel, Thread
from discord.ext import commands
from discord.ext.commands import Context, guild_only
from discord.utils import format_dt, snowflake_time

from PyDrocsid.cog import Cog
from PyDrocsid.command import docs
from PyDrocsid.embeds import send_long_embed
from PyDrocsid.redis import redis
from PyDrocsid.settings import RoleSettings
from PyDrocsid.translations import t

from .colors import Colors
from .permissions import ThreadsPermission
from ...contributor import Contributor
from ...pubsub import send_alert


tg = t.g
t = t.threads


class ThreadsCog(Cog, name="Thread Utils"):
    CONTRIBUTORS = [Contributor.Defelo]

    async def on_thread_create(self, thread: Thread):
        await self.on_thread_join(thread)

    async def on_thread_join(self, thread: Thread):
        if await redis.exists(key := f"thread_created:{thread.id}"):
            return
        await redis.setex(key, 24 * 3600, "1")

        role: Optional[Role] = thread.guild.get_role(await RoleSettings.get("thread_auto_join"))
        if not role:
            return

        try:
            await asyncio.sleep(1)
            msg = await thread.send(role.mention)
            await msg.delete()
        except Forbidden:
            await send_alert(thread.guild, t.new_thread_alert(thread.mention, thread.parent.mention))

    @commands.command(aliases=["t"])
    @ThreadsPermission.list.check
    @guild_only()
    @docs(t.commands.threads)
    async def threads(self, ctx: Context):

        await ctx.trigger_typing()

        async def get_threads(channel: TextChannel) -> list[tuple[Thread, bool]]:
            out_ = channel.threads.copy()
            out_ += await channel.archived_threads(limit=None).flatten()
            if channel.permissions_for(ctx.guild.me).manage_threads and not channel.is_news():
                out_ += await channel.archived_threads(limit=None, private=True).flatten()
            return [
                (thread_, any(member.id == ctx.author.id for member in await thread_.fetch_members()))
                for thread_ in out_
            ]

        def last_timestamp(thread: Thread) -> datetime:
            return snowflake_time(thread.last_message_id)

        threads = [
            *{
                thread
                for threads in await asyncio.gather(
                    *[
                        get_threads(channel)
                        for channel in ctx.guild.text_channels
                        if channel.permissions_for(ctx.guild.me).read_message_history
                        and channel.permissions_for(ctx.author).view_channel
                    ]
                )
                for thread in threads
            }
        ]
        threads.sort(key=lambda x: last_timestamp(x[0]), reverse=True)

        out = []
        thread: Thread
        for thread, joined in threads:
            if not thread.permissions_for(ctx.author).view_channel:
                continue

            line = f":small_{'blue' if thread.archived else 'orange'}_diamond: "
            line += ":white_check_mark: " if joined else ":x: "
            if thread.archived:
                line += f"[#{thread.name}](https://discord.com/channels/{thread.guild.id}/{thread.id})"
            else:
                line += f"{thread.mention}"
            line += f" ({thread.parent.mention}, {format_dt(last_timestamp(thread), style='R')})"
            out.append(line)

        embed = Embed(title=t.threads, description="\n".join(out), color=Colors.Threads)
        if not out:
            embed.description = t.no_threads
            embed.colour = Colors.error

        await send_long_embed(ctx, embed, paginate=True)
