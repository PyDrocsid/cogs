from typing import List

from discord import Embed, Guild, Member, Status
from discord.ext import commands
from discord.ext.commands import Context, UserInputError, guild_only

from PyDrocsid.cog import Cog
from PyDrocsid.command import docs, reply
from PyDrocsid.embeds import send_long_embed
from PyDrocsid.translations import t

from .colors import Colors
from ...contributor import Contributor


tg = t.g
t = t.server_info


class ServerInfoCog(Cog, name="Server Information"):
    CONTRIBUTORS = [Contributor.Defelo]

    async def get_users(self, guild: Guild) -> list[tuple[str, list[Member]]]:
        return []

    async def get_additional_fields(self, guild: Guild) -> list[tuple[str, str]]:
        return []

    @commands.group()
    @guild_only()
    @docs(t.commands.server)
    async def server(self, ctx: Context):
        if ctx.subcommand_passed is not None:
            if ctx.invoked_subcommand is None:
                raise UserInputError
            return

        guild: Guild = ctx.guild
        embed = Embed(title=guild.name, description=t.info_description, color=Colors.ServerInformation)
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        created = guild.created_at.date()
        embed.add_field(name=t.creation_date, value=f"{created.day}.{created.month}.{created.year}")
        online_count = sum([m.status != Status.offline for m in guild.members])
        embed.add_field(name=t.cnt_members(cnt=guild.member_count), value=t.cnt_online(online_count))
        embed.add_field(name=t.owner, value=guild.owner.mention)

        for title, users in await self.get_users(guild):
            embed.add_field(name=title, value="\n".join(":small_orange_diamond: " + m.mention for m in users))

        bots = [m for m in guild.members if m.bot]
        bots_online = sum([m.status != Status.offline for m in bots])
        embed.add_field(name=t.cnt_bots(cnt=len(bots)), value=t.cnt_online(bots_online))

        for name, value in await self.get_additional_fields(guild):
            embed.add_field(name=name, value=value)

        await send_long_embed(ctx, embed)

    @server.command(name="bots")
    @docs(t.commands.bots)
    async def server_bots(self, ctx: Context):
        guild: Guild = ctx.guild
        online: List[Member] = []
        offline: List[Member] = []
        for member in guild.members:  # type: Member
            if member.bot:
                [offline, online][member.status != Status.offline].append(member)

        cnt = len(online) + len(offline)
        embed = Embed(title=t.cnt_bots(cnt=cnt), color=Colors.ServerInformation)

        if not cnt:
            embed.colour = Colors.error
            embed.description = t.no_bots
            await reply(ctx, embed=embed)
            return

        if cnt := len(online):
            embed.add_field(
                name=t.online(cnt=cnt), value="\n".join(":small_orange_diamond: " + m.mention for m in online)
            )
        if cnt := len(offline):
            embed.add_field(
                name=t.offline(cnt=cnt), value="\n".join(":small_blue_diamond: " + m.mention for m in offline)
            )

        await send_long_embed(ctx, embed=embed)
