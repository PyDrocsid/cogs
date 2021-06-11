from __future__ import annotations

from collections import Callable
from typing import Optional, Awaitable

from aiohttp import ClientSession
from discord import Embed, Message, Status, Game
from discord.ext import commands, tasks
from discord.ext.commands import Context

from PyDrocsid.cog import Cog
from PyDrocsid.command import reply, docs
from PyDrocsid.config import Config
from PyDrocsid.embeds import send_long_embed
from PyDrocsid.github_api import GitHubUser, get_users, get_repo_description
from PyDrocsid.prefix import get_prefix
from PyDrocsid.translations import t
from .colors import Colors
from ...contributor import Contributor

tg = t.g
t = t.bot_info


class InfoComponent:
    @staticmethod
    def author(inline: bool):
        async def inner(cog: BotInfoCog, embed: Embed):
            embed.add_field(name=t.author_title, value=cog.format_contributor(Config.AUTHOR), inline=inline)

        return inner

    @staticmethod
    def contributors(inline: bool):
        async def inner(cog: BotInfoCog, embed: Embed):
            if not cog.github_users:
                await cog.load_github_users()

            contributors = [f for c, _ in Config.CONTRIBUTORS.most_common() if (f := cog.format_contributor(c))]

            embed.add_field(name=t.cnt_contributors(cnt=len(contributors)), value=" ".join(contributors), inline=inline)

        return inner

    @staticmethod
    def version(inline: bool):
        async def inner(_, embed: Embed):
            embed.add_field(name=t.version_title, value=Config.VERSION, inline=inline)

        return inner

    @staticmethod
    def github_repo(inline: bool):
        async def inner(_, embed: Embed):
            embed.add_field(name=t.github_title, value=Config.REPO_LINK, inline=inline)

        return inner

    @staticmethod
    def prefix(inline: bool):
        async def inner(cog: BotInfoCog, embed: Embed):
            prefix: str = await get_prefix()
            embed.add_field(name=t.prefix_title, value=f"`{prefix}` or {cog.bot.user.mention}", inline=inline)

        return inner

    @staticmethod
    def help_command(inline: bool):
        async def inner(_, embed: Embed):
            prefix: str = await get_prefix()
            embed.add_field(name=t.help_command_title, value=f"`{prefix}help`", inline=inline)

        return inner

    @staticmethod
    def bugs_features(inline: bool):
        async def inner(_, embed: Embed):
            embed.add_field(
                name=t.bugs_features_title,
                value=t.bugs_features(repo=Config.REPO_LINK),
                inline=inline,
            )

        return inner

    @staticmethod
    def pydrocsid(inline: bool):
        async def inner(_, embed: Embed):
            async with ClientSession() as session, session.head("https://discord.pydrocsid.ml") as response:
                url = response.headers["location"]
            code = url.split("/")[-1]

            embed.add_field(name=t.pydrocsid, value=t.pydrocsid_info(code=code), inline=inline)

        return inner

    @staticmethod
    def enabled_cogs(inline: bool):
        async def inner(cog: BotInfoCog, embed: Embed):
            embed.add_field(name=t.enabled_cogs, value=t.cnt_cogs_enabled(cnt=len(cog.bot.cogs)), inline=inline)

        return inner


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

    @property
    def info_components(self) -> list[Callable[[BotInfoCog, Embed], Awaitable[None]]]:
        return [
            InfoComponent.author(True),
            InfoComponent.version(True),
            InfoComponent.enabled_cogs(True),
            InfoComponent.contributors(False),
            InfoComponent.github_repo(False),
            InfoComponent.pydrocsid(False),
            InfoComponent.prefix(True),
            InfoComponent.help_command(True),
            InfoComponent.bugs_features(False),
        ]

    async def build_info_embed(self) -> Embed:
        embed = Embed(title=Config.NAME or "", colour=Colors.info, description=t.bot_description or "")

        if self.info_icon:
            embed.set_thumbnail(url=self.info_icon)

        for component in self.info_components:
            await component(self, embed)

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
        await send_long_embed(ctx, await self.build_info_embed())

    @commands.command(aliases=["contri", "con"])
    @docs(t.commands.contributors)
    async def contributors(self, ctx: Context):
        if not self.github_users:
            await self.load_github_users()

        contributors = [f for c, _ in Config.CONTRIBUTORS.most_common() if (f := self.format_contributor(c, True))]

        await send_long_embed(
            ctx,
            Embed(
                title=t.cnt_contributors(cnt=len(contributors)),
                colour=Colors.info,
                description="\n".join(f":small_orange_diamond: {con}" for con in contributors),
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
        await send_long_embed(message, await self.build_info_embed())
