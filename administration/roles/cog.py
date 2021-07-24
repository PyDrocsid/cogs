from typing import Optional, Union, Dict, List

from discord import Role, Embed, Member, Status, Guild, NotFound, User, Forbidden
from discord.ext import commands
from discord.ext.commands import CommandError, Context, guild_only, UserInputError, Group

from PyDrocsid.cog import Cog
from PyDrocsid.command import reply, docs
from PyDrocsid.config import Contributor, Config
from PyDrocsid.converter import UserMemberConverter
from PyDrocsid.database import db, select, filter_by
from PyDrocsid.embeds import send_long_embed
from PyDrocsid.emojis import name_to_emoji
from PyDrocsid.prefix import get_prefix
from PyDrocsid.settings import RoleSettings
from PyDrocsid.translations import t
from PyDrocsid.util import check_role_assignable
from .colors import Colors
from .models import RoleAuth, PermaRole
from .permissions import RolesPermission
from ...pubsub import send_to_changelog, send_alert

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


async def is_authorized(author: Member, target_role: Role, *, perma: bool) -> bool:
    if not perma and author.guild_permissions.manage_roles and target_role < author.top_role:
        return True

    if await RolesPermission.auth_write.check_permissions(author):
        return True

    roles = {role.id for role in author.roles} | {author.id}

    auth: RoleAuth
    async for auth in await db.stream(select(RoleAuth).filter_by(target=target_role.id)):
        if perma and not auth.perma_allowed:
            continue
        if auth.source in roles:
            return True

    return False


def status_icon(status: Status) -> str:
    return {
        Status.online: ":green_circle:",
        Status.idle: ":yellow_circle:",
        Status.dnd: ":red_circle:",
        Status.offline: ":black_circle:",
    }[status]


async def reassign(member: Member, role: Role):
    try:
        await member.add_roles(role)
    except Forbidden:
        await send_alert(
            member.guild,
            t.could_not_reassign(role.mention, member.mention, member),
        )
    else:
        await send_alert(
            member.guild,
            t.perma_reassigned(role.mention, member.mention, member, await get_prefix()),
        )


def add_role_command(roles_config: Group, name: str, title: str, check_assignable: bool):
    @roles_config.command(name=name)
    @RolesPermission.config_write.check
    @docs(t.configure_role(title.lower()))
    async def inner(_, ctx: Context, *, role: Role):
        await configure_role(ctx, name, role, check_assignable)

    return inner


class RolesCog(Cog, name="Roles"):
    CONTRIBUTORS = [Contributor.Defelo]

    def __init__(self):
        super().__init__()

        self.removed_perma_roles: set[tuple[int, int]] = set()

    async def on_member_role_remove(self, member: Member, role: Role):
        if (member.id, role.id) in self.removed_perma_roles:
            self.removed_perma_roles.remove((member.id, role.id))
            return

        if not await db.exists(filter_by(PermaRole, member_id=member.id, role_id=role.id)):
            return

        await reassign(member, role)

    async def on_member_join(self, member: Member):
        guild: Guild = member.guild

        perma_role: PermaRole
        async for perma_role in await db.stream(filter_by(PermaRole, member_id=member.id)):
            if not (role := guild.get_role(perma_role.role_id)):
                await db.delete(perma_role)
                continue

            await reassign(member, role)

    async def on_ready(self):
        guild: Guild = self.bot.guilds[0]

        async for perma_role in await db.stream(select(PermaRole)):
            if not (role := guild.get_role(perma_role.role_id)):
                await db.delete(perma_role)
                continue
            if not (member := guild.get_member(perma_role.member_id)):
                continue
            if role in member.roles:
                continue

            await reassign(member, role)

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

    for i, (name, (title, check_assignable)) in enumerate(Config.ROLES.items()):
        set_cmd = add_role_command(roles_config, name, title, check_assignable)
        exec(f"rc_set_{i} = set_cmd")  # noqa: S102

    @roles.group(name="auth")
    @RolesPermission.auth_read.check
    @docs(t.commands.roles_auth)
    async def roles_auth(self, ctx: Context):
        if len(ctx.message.content.lstrip(ctx.prefix).split()) > 2:
            if ctx.invoked_subcommand is None:
                raise UserInputError
            return

        embed = Embed(title=t.role_auth, colour=Colors.Roles)
        members: Dict[Member, List[tuple[Role, bool]]] = {}
        roles: Dict[Role, List[tuple[Role, bool]]] = {}
        auth: RoleAuth
        async for auth in await db.stream(select(RoleAuth)):
            source: Optional[Union[Member, Role]] = ctx.guild.get_member(auth.source) or ctx.guild.get_role(auth.source)
            target: Optional[Role] = ctx.guild.get_role(auth.target)
            if source is None or target is None:
                await db.delete(auth)
            else:
                [members, roles][isinstance(source, Role)].setdefault(source, []).append((target, auth.perma_allowed))
        if not members and not roles:
            embed.description = t.no_role_auth
            embed.colour = Colors.error
            await reply(ctx, embed=embed)
            return

        def make_field(auths: Dict[Union[Member, Role], List[tuple[Role, bool]]]) -> List[str]:
            out = []
            for src, targets in sorted(auths.items(), key=lambda a: a[0].name):
                line = f":small_orange_diamond: {src.mention} -> "
                line += ", ".join(role.mention + " :shield:" * perma for role, perma in targets)
                out.append(line)

            return out

        if roles:
            embed.add_field(name=t.role_auths, value="\n".join(make_field(roles)), inline=False)
        if members:
            embed.add_field(name=t.user_auths, value="\n".join(make_field(members)), inline=False)
        await reply(ctx, embed=embed)

    @roles_auth.command(name="add", aliases=["a", "+"])
    @RolesPermission.auth_write.check
    @docs(t.commands.roles_auth_add)
    async def roles_auth_add(self, ctx: Context, source: Union[Member, Role], target: Role, allow_perma: bool):
        if await RoleAuth.check(source.id, target.id):
            raise CommandError(t.role_auth_already_exists)
        if isinstance(source, Member) and source.bot:
            raise CommandError(t.no_auth_for_bots)

        check_role_assignable(target)

        await RoleAuth.add(source.id, target.id, allow_perma)
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

        if not await is_authorized(ctx.author, role, perma=False):
            raise CommandError(t.role_not_authorized)

        check_role_assignable(role)

        await member.add_roles(role)
        await ctx.message.add_reaction(name_to_emoji["white_check_mark"])

    @roles.command(name="remove", aliases=["r", "del", "d", "-"])
    @docs(t.commands.roles_remove)
    async def roles_remove(self, ctx: Context, member: Member, *, role: Role):
        if role not in member.roles:
            raise CommandError(t.role_not_assigned)

        if not await is_authorized(ctx.author, role, perma=False):
            raise CommandError(t.role_not_authorized)

        check_role_assignable(role)

        if await db.exists(filter_by(PermaRole, member_id=member.id, role_id=role.id)):
            raise CommandError(t.cannot_remove_perma(await get_prefix()))

        await member.remove_roles(role)
        await ctx.message.add_reaction(name_to_emoji["white_check_mark"])

    @roles.command(name="perma_add", aliases=["pa", "++"])
    @docs(t.commands.roles_perma_add)
    async def roles_perma_add(self, ctx: Context, member: UserMemberConverter, *, role: Role):
        member: Union[User, Member]

        if not await is_authorized(ctx.author, role, perma=True):
            raise CommandError(t.role_not_authorized)

        check_role_assignable(role)

        if await db.exists(filter_by(PermaRole, member_id=member.id, role_id=role.id)):
            raise CommandError(t.role_already_assigned)

        self.removed_perma_roles.discard((member.id, role.id))
        await PermaRole.add(member.id, role.id)
        if isinstance(member, Member):
            await member.add_roles(role)
        await send_to_changelog(ctx.guild, t.added_perma_role(role.mention, member.mention, member))
        await ctx.message.add_reaction(name_to_emoji["white_check_mark"])

    @roles.command(name="perma_remove", aliases=["pr", "perma_delete", "pd", "--"])
    @docs(t.commands.roles_perma_remove)
    async def roles_perma_remove(self, ctx: Context, member: UserMemberConverter, *, role: Role):
        member: Union[User, Member]

        if not await is_authorized(ctx.author, role, perma=True):
            raise CommandError(t.role_not_authorized)

        check_role_assignable(role)

        if not (row := await db.get(PermaRole, member_id=member.id, role_id=role.id)):
            raise CommandError(t.role_not_assigned)

        await db.delete(row)
        if isinstance(member, Member):
            self.removed_perma_roles.add((member.id, role.id))
            await member.remove_roles(role)
        await send_to_changelog(ctx.guild, t.removed_perma_role(role.mention, member.mention, member))
        await ctx.message.add_reaction(name_to_emoji["white_check_mark"])

    @roles.command(name="perma_unset", aliases=["pu", "~~"])
    @docs(t.commands.roles_perma_unset)
    async def roles_perma_unset(self, ctx: Context, member: UserMemberConverter, *, role: Role):
        member: Union[User, Member]

        if not await is_authorized(ctx.author, role, perma=True):
            raise CommandError(t.role_not_authorized)

        if not (row := await db.get(PermaRole, member_id=member.id, role_id=role.id)):
            raise CommandError(t.role_not_assigned)

        await db.delete(row)
        await send_to_changelog(ctx.guild, t.removed_perma_role(role.mention, member.mention, member))
        await ctx.message.add_reaction(name_to_emoji["white_check_mark"])

    @roles.command(name="list", aliases=["l", "?"])
    @RolesPermission.list_members.check
    @docs(t.commands.roles_list)
    async def roles_list(self, ctx: Context, *, role: Role):
        member_ids: set[int] = {member.id for member in role.members}
        perma: dict[int, str] = {}

        perma_role: PermaRole
        async for perma_role in await db.stream(filter_by(PermaRole, role_id=role.id)):
            try:
                user = await self.bot.fetch_user(perma_role.member_id)
            except NotFound:
                continue

            member_ids.add(user.id)
            perma[user.id] = str(user)

        members: list[Member] = []
        for member_id in [*member_ids]:
            if not (member := ctx.guild.get_member(member_id)):
                continue

            members.append(member)
            member_ids.remove(member_id)

        members.sort(
            key=lambda m: ([Status.online, Status.idle, Status.dnd, Status.offline].index(m.status), str(m), m.id),
        )

        out = []
        for member in members:
            out.append(f"{status_icon(member.status)} {member.mention} (@{member})")
            if member.id in perma:
                out[-1] += " :shield:"
                if role not in member.roles:
                    out[-1] += " :warning:"

        for member_id, member_name in perma.items():
            if member_id not in member_ids:
                continue

            out.append(f":grey_question: <@{member_id}> (@{member_name}) :shield:")

        if out:
            embed = Embed(title=t.member_list_cnt(len(out)), colour=0x256BE6, description="\n".join(out))
        else:
            embed = Embed(title=t.member_list, colour=0xCF0606, description=t.no_members)
        await send_long_embed(ctx, embed, paginate=True)

    @roles.command(name="perma_list", aliases=["pl", "ll", "??"])
    @RolesPermission.list_members.check
    @docs(t.commands.roles_perma_list)
    async def roles_perma_list(self, ctx: Context):
        guild: Guild = ctx.guild

        role_users: dict[Role, list[User]] = {}
        perma_role: PermaRole
        async for perma_role in await db.stream(select(PermaRole)):
            if not (role := guild.get_role(perma_role.role_id)):
                await db.delete(perma_role)
                continue

            try:
                user = await self.bot.fetch_user(perma_role.member_id)
            except NotFound:
                await db.delete(perma_role)
                continue

            role_users.setdefault(role, []).append(user)

        embed = Embed(title=t.perma_roles, color=Colors.Roles)
        if not role_users:
            embed.colour = Colors.error
            embed.description = t.no_perma_roles
            await reply(ctx, embed=embed)
            return

        for role, users in role_users.items():
            lines = []
            for user in users:
                member: Optional[Member] = guild.get_member(user.id)
                if not member:
                    lines.append(f":small_blue_diamond: {user.mention} ({user})")
                elif role not in member.roles:
                    lines.append(f":small_blue_diamond: {user.mention} ({user}) :warning:")
                else:
                    lines.append(f":small_orange_diamond: {user.mention} ({user})")

            embed.add_field(name=f"@{role} ({role.id})", value="\n".join(lines), inline=False)

        await send_long_embed(ctx, embed, paginate=True)
