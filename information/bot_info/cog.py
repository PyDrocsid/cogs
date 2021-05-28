from typing import Optional

from discord import Embed, Message, Status, Game
from discord.ext import commands, tasks
from discord.ext.commands import Context

from PyDrocsid.cog import Cog
from PyDrocsid.command import reply, docs
from PyDrocsid.config import Config
from PyDrocsid.embeds import send_long_embed
from PyDrocsid.github_api import GitHubUser, get_users, get_repo_description
from PyDrocsid.prefix import get_prefix, get_guild_context, GuildContext, GlobalPrefix
from PyDrocsid.translations import t
from .colors import Colors
from .permissions import InfoPermission
from ...contributor import Contributor

tg = t.g
t = t.bot_info


class BotInfoCog(Cog, name="Bot Information"):
    CONTRIBUTORS = [Contributor.Defelo, Contributor.ce_phox]

    def __init__(self, *, info_icon: Optional[str] = None):
        super().__init__()

        self.info_icon: Optional[str] = info_icon
        self.repo_description: str = ""
        self.github_users: Optional[dict[str, GitHubUser]] = {}
        self.current_status = 0

    async def load_github_users(self):
        self.github_users = await get_users([c for _, c in Config.CONTRIBUTORS if c]) or {}

    def format_contributor(self, contributor: Contributor, long: bool = False) -> Optional[str]:
        discord_id, github_id = contributor

        discord_mention = f"<@{discord_id}>" if discord_id else None

        github_profile = None
        if github_id in self.github_users:
            _, name, profile = self.github_users[github_id]
            github_profile = f"[[{name}]]({profile})"

        if not discord_mention and not github_profile:
            return None

        if not long:
            return discord_mention or github_profile

        return " ".join(x for x in [discord_mention, github_profile] if x)

    async def on_ready(self):
        try:
            self.status_loop.start()
        except RuntimeError:
            self.status_loop.restart()

    @tasks.loop(seconds=20)
    async def status_loop(self):
        await self.bot.change_presence(status=Status.online, activity=Game(name=t.profile_status[self.current_status]))
        self.current_status = (self.current_status + 1) % len(t.profile_status)

    async def build_info_embed(self, message: Message, authorized: bool) -> Embed:
        embed = Embed(title=Config.NAME, colour=Colors.info, description=t.bot_description)

        if self.info_icon:
            embed.set_thumbnail(url=self.info_icon)

        features = t.features
        if authorized:
            features += t.admin_features

        embed.add_field(
            name=t.features_title,
            value="\n".join(f":small_orange_diamond: {feature}" for feature in features),
            inline=False,
        )

        if not self.github_users:
            await self.load_github_users()

        embed.add_field(name=t.author_title, value=self.format_contributor(Config.AUTHOR), inline=True)

        embed.add_field(
            name=t.contributors_title,
            value=" ".join(
                f
                for c, _ in Config.CONTRIBUTORS.most_common()
                if (f := self.format_contributor(c)) and c != Config.AUTHOR
            ),
            inline=True,
        )

        embed.add_field(name=t.version_title, value=Config.VERSION, inline=True)
        embed.add_field(name=t.github_title, value=Config.REPO_LINK, inline=False)

        guild_context, guild, prefix = await get_guild_context(self.bot, message)
        if guild_context == GuildContext.PRIVATE_GLOBAL:
            embed.add_field(name=t.help_command_title, value="`help`", inline=True)
        else:
            local_prefix = await get_prefix(guild)
            global_prefix = await GlobalPrefix.get_prefix(guild.id)
            if guild_context == GuildContext.GUILD:
                command_prefix = local_prefix
            else:
                command_prefix = global_prefix + " "

            embed.add_field(
                name=t.local_prefix_title,
                value=f"`{local_prefix}` or {self.bot.user.mention}",
                inline=True,
            )
            if global_prefix:
                embed.add_field(name=t.global_prefix_title, value=f"`{global_prefix}`", inline=True)
            embed.add_field(name=t.help_command_title, value=f"`{command_prefix}help`", inline=True)

        embed.add_field(
            name=t.bugs_features_title,
            value=t.bugs_features(repo=Config.REPO_LINK),
            inline=False,
        )
        return embed

    @commands.command(aliases=["gh"])
    @docs(t.commands.github)
    async def github(self, ctx: Context):
        if not self.repo_description:
            self.repo_description = await get_repo_description(Config.REPO_OWNER, Config.REPO_NAME)

        embed = Embed(
            title=f"{Config.REPO_OWNER}/{Config.REPO_NAME}",
            description=self.repo_description,
            colour=Colors.github,
            url=Config.REPO_LINK,
        )
        embed.set_author(name="GitHub", icon_url="https://github.com/fluidicon.png")
        embed.set_thumbnail(url=Config.REPO_ICON)
        await reply(ctx, embed=embed)

    @commands.command(aliases=["v"])
    @docs(t.commands.version)
    async def version(self, ctx: Context):
        embed = Embed(title=f"{Config.NAME} v{Config.VERSION}", colour=Colors.version)
        await reply(ctx, embed=embed)

    @commands.command(aliases=["infos", "about"])
    @docs(t.commands.info)
    async def info(self, ctx: Context):
        await send_long_embed(ctx, await self.build_info_embed(ctx.message, False))

    @commands.command(aliases=["admininfos"])
    @InfoPermission.admininfo.check
    @docs(t.commands.admininfo)
    async def admininfo(self, ctx: Context):
        await send_long_embed(ctx, await self.build_info_embed(ctx.message, True))

    @commands.command(aliases=["contri", "con"])
    @docs(t.commands.contributors)
    async def contributors(self, ctx: Context):
        if not self.github_users:
            await self.load_github_users()

        await send_long_embed(
            ctx,
            Embed(
                title=t.contributors_title,
                colour=Colors.info,
                description="\n".join(
                    f":small_orange_diamond: {f}"
                    for c, cnt in [(Config.AUTHOR, 0), *Config.CONTRIBUTORS.most_common()]
                    if (f := self.format_contributor(c, long=True)) and (c != Config.AUTHOR or not cnt)
                ),
            ),
        )

    @commands.command()
    @docs(t.commands.cogs)
    async def cogs(self, ctx: Context):
        description = []
        for name, cog in sorted(self.bot.cogs.items()):
            description.append(f":small_orange_diamond: {name} (`{cog.__class__.__name__}`)")

        await send_long_embed(
            ctx,
            Embed(title=t.enabled_cogs, color=Colors.info, description="\n".join(description)),
            paginate=True,
        )

    async def on_bot_ping(self, message: Message):
        await reply(message, embed=await self.build_info_embed(message, False))
