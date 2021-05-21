from typing import Optional, Union, Dict, List

from discord import Role, Embed, Member
from discord.ext import commands
from discord.ext.commands import CommandError, Context, guild_only, UserInputError

from PyDrocsid.cog import Cog
from PyDrocsid.command import reply, docs
from PyDrocsid.config import Contributor, Config
from PyDrocsid.database import db, select
from PyDrocsid.embeds import send_long_embed
from PyDrocsid.emojis import name_to_emoji
from PyDrocsid.settings import RoleSettings
from PyDrocsid.translations import t
from PyDrocsid.util import check_role_assignable
from .colors import Colors
from .models import RoleAuth
from .permissions import RolesPermission
from ...pubsub import send_to_changelog

tg = t.g
t = t.roles


async def configure_role(ctx: Context, role_name: str, role: Role, check_assignable: bool = False):
    if check_assignable:
        check_role_assignable(role)

    await RoleSettings.set(role_name, role.id)
    await reply(ctx, t.role_set)
    await send_to_changelog(
        ctx.guild,
        t.log_role_set(Config.ROLES[role_name][0], role.name, role.id),
    )


async def is_authorized(author: Member, target_role: Role) -> bool:
    roles = {role.id for role in author.roles} | {author.id}

    auth: RoleAuth
    async for auth in await db.stream(select(RoleAuth).filter_by(target=target_role.id)):
        if auth.source in roles:
            return True

    return False


class RolesCog(Cog, name="Roles"):
    CONTRIBUTORS = [Contributor.Defelo]

    def __init__(self):
        super().__init__()

        def set_role(role_name: str, assignable: bool):
            @RolesPermission.config_write.check
            async def inner(ctx: Context, *, role: Role):
                await configure_role(ctx, role_name, role, assignable)

            return inner

        for name, (title, check_assignable) in Config.ROLES.items():
            self.roles_config.command(name=name, help=t.configure_role(title.lower()))(
                set_role(name, check_assignable),
            )

    @commands.group(aliases=["r"])
    @guild_only()
    @docs(t.commands.roles)
    async def roles(self, ctx: Context):
        if ctx.invoked_subcommand is None:
            raise UserInputError

    @roles.group(name="config", aliases=["conf", "c", "set", "s"])
    @RolesPermission.config_read.check
    @docs(t.commands.roles_config)
    async def roles_config(self, ctx: Context):
        if len(ctx.message.content.lstrip(ctx.prefix).split()) > 2:
            if ctx.invoked_subcommand is None:
                raise UserInputError
            return

        embed = Embed(title=t.roles, color=Colors.Roles)
        for name, (title, _) in Config.ROLES.items():
            role = ctx.guild.get_role(await RoleSettings.get(name))
            val = role.mention if role is not None else t.role_not_set
            embed.add_field(name=title, value=val, inline=True)
        await reply(ctx, embed=embed)

    @roles.group(name="auth")
    @RolesPermission.auth_read.check
    @docs(t.commands.roles_auth)
    async def roles_auth(self, ctx: Context):
        if len(ctx.message.content.lstrip(ctx.prefix).split()) > 2:
            if ctx.invoked_subcommand is None:
                raise UserInputError
            return

        embed = Embed(title=t.role_auth, colour=Colors.Roles)
        members: Dict[Member, List[Role]] = {}
        roles: Dict[Role, List[Role]] = {}
        auth: RoleAuth
        async for auth in await db.stream(select(RoleAuth)):
            source: Optional[Union[Member, Role]] = ctx.guild.get_member(auth.source) or ctx.guild.get_role(auth.source)
            target: Optional[Role] = ctx.guild.get_role(auth.target)
            if source is None or target is None:
                await db.delete(auth)
            else:
                [members, roles][isinstance(source, Role)].setdefault(source, []).append(target)
        if not members and not roles:
            embed.description = t.no_role_auth
            embed.colour = Colors.error
            await reply(ctx, embed=embed)
            return

        def make_field(auths: Dict[Union[Member, Role], List[Role]]) -> List[str]:
            return [
                f":small_orange_diamond: {src.mention} -> " + ", ".join(x.mention for x in targets)
                for src, targets in sorted(auths.items(), key=lambda a: a[0].name)
            ]

        if roles:
            embed.add_field(name=t.role_auths, value="\n".join(make_field(roles)), inline=False)
        if members:
            embed.add_field(name=t.user_auths, value="\n".join(make_field(members)), inline=False)
        await reply(ctx, embed=embed)

    @roles_auth.command(name="add", aliases=["a", "+"])
    @RolesPermission.auth_write.check
    @docs(t.commands.roles_auth_add)
    async def roles_auth_add(self, ctx: Context, source: Union[Member, Role], target: Role):
        if await RoleAuth.check(source.id, target.id):
            raise CommandError(t.role_auth_already_exists)
        if isinstance(source, Member) and source.bot:
            raise CommandError(t.no_auth_for_bots)

        check_role_assignable(target)

        await RoleAuth.add(source.id, target.id)
        await reply(ctx, t.role_auth_created)
        await send_to_changelog(ctx.guild, t.log_role_auth_created(source, target))

    @roles_auth.command(name="remove", aliases=["r", "del", "d", "-"])
    @RolesPermission.auth_write.check
    @docs(t.commands.roles_auth_remove)
    async def roles_auth_remove(self, ctx: Context, source: Union[Member, Role], target: Role):
        if not (auth := await db.first(select(RoleAuth).filter_by(source=source.id, target=target.id))):
            raise CommandError(t.role_auth_not_found)

        await db.delete(auth)
        await reply(ctx, t.role_auth_removed)
        await send_to_changelog(ctx.guild, t.log_role_auth_removed(source, target))

    @roles.command(name="add", aliases=["a", "+"])
    @docs(t.commands.roles_add)
    async def roles_add(self, ctx: Context, member: Member, *, role: Role):
        if role in member.roles:
            raise CommandError(t.role_already_assigned)

        if not await is_authorized(ctx.author, role):
            raise CommandError(t.role_not_authorized)

        check_role_assignable(role)

        await member.add_roles(role)
        await ctx.message.add_reaction(name_to_emoji["white_check_mark"])

    @roles.command(name="remove", aliases=["r", "del", "d", "-"])
    @docs(t.commands.roles_remove)
    async def roles_remove(self, ctx: Context, member: Member, *, role: Role):
        if role not in member.roles:
            raise CommandError(t.role_not_assigned)

        if not await is_authorized(ctx.author, role):
            raise CommandError(t.role_not_authorized)

        check_role_assignable(role)

        await member.remove_roles(role)
        await ctx.message.add_reaction(name_to_emoji["white_check_mark"])

    @roles.command(name="list", aliases=["l", "?"])
    @RolesPermission.list_members.check
    @docs(t.commands.roles_list)
    async def roles_list(self, ctx: Context, *, role: Role):
        out = [t.member_list_line(member.mention, f"@{member}") for member in role.members]
        if out:
            embed = Embed(title=t.member_list_cnt(len(out)), colour=0x256BE6, description="\n".join(out))
        else:
            embed = Embed(title=t.member_list, colour=0xCF0606, description=t.no_members)
        await send_long_embed(ctx, embed, paginate=True)
