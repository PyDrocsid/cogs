import re
import string
from typing import Optional, Tuple

from discord import Embed, Message, PartialEmoji, Member, Forbidden, Guild, Interaction, SelectOption
from discord.ext import commands
from discord.ext.commands import Context, guild_only, CommandError
from discord.ui import View, Select
from discord.utils import utcnow

from PyDrocsid.cog import Cog
from PyDrocsid.embeds import EmbedLimits
from PyDrocsid.emojis import name_to_emoji, emoji_to_name
from PyDrocsid.events import StopEventHandling
from PyDrocsid.settings import RoleSettings
from PyDrocsid.translations import t
from PyDrocsid.redis import redis
from PyDrocsid.util import is_teamler, check_wastebasket
from .colors import Colors
from .permissions import PollsPermission
from ...contributor import Contributor

tg = t.g
t = t.polls

MAX_OPTIONS = 20  # Discord reactions limit
# TODO Remove Limit or change it

default_emojis = [name_to_emoji[f"regional_indicator_{x}"] for x in string.ascii_lowercase]


async def get_teampoll_embed(message: Message) -> Tuple[Optional[Embed], Optional[int]]:
    for embed in message.embeds:
        for i, field in enumerate(embed.fields):
            if tg.status == field.name:
                return embed, i
    return None, None


class PollsCog(Cog, name="Polls"):
    CONTRIBUTORS = [
        Contributor.MaxiHuHe04,
        Contributor.Defelo,
        Contributor.TNT2k,
        Contributor.wolflu,
        Contributor.Tert0,
    ]

    def __init__(self, team_roles: list[str]):
        self.team_roles: list[str] = team_roles

    async def send_poll(
        self,
        ctx: Context,
        title: str,
        args: str,
        field: Optional[Tuple[str, str]] = None,
        allow_delete: bool = True,
        team_poll: bool = False,
    ):
        question, *options = [line.replace("\x00", "\n") for line in args.replace("\\\n", "\x00").split("\n") if line]

        if not options:
            raise CommandError(t.missing_options)
        if len(options) > MAX_OPTIONS - allow_delete:
            raise CommandError(t.too_many_options(MAX_OPTIONS - allow_delete))

        options = [PollOption(ctx, line, i) for i, line in enumerate(options)]

        if any(len(str(option)) > EmbedLimits.FIELD_VALUE for option in options):
            raise CommandError(t.option_too_long(EmbedLimits.FIELD_VALUE))

        embed = Embed(title=title, description=question, color=Colors.Polls, timestamp=utcnow())
        embed.set_author(name=str(ctx.author), icon_url=ctx.author.display_avatar.url)

        if allow_delete:
            embed.set_footer(text=t.created_by(ctx.author, ctx.author.id), icon_url=ctx.author.display_avatar.url)

        if len(set(map(lambda x: x.emoji, options))) < len(options):
            raise CommandError(t.option_duplicated)

        if field:
            embed.add_field(name=field[0], value=field[1], inline=False)

        view = View(timeout=None)

        vote_select = Select(placeholder=t.poll_select_placeholder, max_values=len(options))

        for i, option in enumerate(options):
            vote_select.add_option(label=option.option, description=t.votes(0, cnt=0), emoji=option.emoji)

        for option in options:
            if len([item for item in options if item.option == option.option]) > 1:
                raise CommandError("cant have to items with same name")  # TODO Translation

        async def poll_vote(interaction: Interaction):
            def get_option_by_label(label: str, select: Select) -> SelectOption:
                for option in select.options:
                    if option.label == label:
                        return option

            def get_redis_key(message: Message, member: Member, option: SelectOption) -> str:
                return f"poll_vote:{message.id}:{member.id}:{vote_select.options.index(option)}"

            def get_team_poll_redis_key(message: Message, member: Member) -> str:
                return f"team_poll_vote:{message.id}:{member.id}"

            if interaction.data["component_type"] != 3:  # Component Type 3 is the Select
                return
            if interaction.data.get("values") is None:
                return
            values = interaction.data["values"]
            for value in values:
                selected_option = get_option_by_label(value, vote_select)

                redis_key: str = get_redis_key(interaction.message, interaction.user, selected_option)
                team_poll_redis_key: str = get_team_poll_redis_key(interaction.message, interaction.user)
                vote_value = 1
                if await redis.exists(redis_key):
                    vote_value = -1
                    await redis.delete(redis_key)

                vote_count: int = int(re.match(r"[\-]?[0-9]+", selected_option.description).group(0))
                selected_option.description = t.votes(vote_count + vote_value, cnt=vote_count + vote_value)
                if vote_value == 1:
                    await redis.set(redis_key, 1)
                    if team_poll:
                        await redis.sadd(team_poll_redis_key, vote_select.options.index(selected_option))
                elif vote_value == -1:
                    if team_poll:
                        await redis.srem(team_poll_redis_key, vote_select.options.index(selected_option))

            if team_poll:
                _, index = await get_teampoll_embed(interaction.message)
                value = await self.get_reacted_teamlers(interaction.message)
                embed.set_field_at(index, name=tg.status, value=value, inline=False)

            await interaction.message.edit(content="** **", embed=embed, view=view)

        vote_select.callback = poll_vote
        view.add_item(vote_select)

        poll: Message = await ctx.send(content="** **", embed=embed, view=view)  # TODO Remove Content from Message
        # Content will get sent as WorkARound for https://github.com/Pycord-Development/pycord/issues/192

        try:
            if allow_delete:
                await poll.add_reaction(name_to_emoji["wastebasket"])
        except Forbidden:
            raise CommandError(t.could_not_add_reactions(ctx.channel.mention))

    async def get_reacted_teamlers(self, message: Optional[Message] = None) -> str:
        guild: Guild = self.bot.guilds[0]

        def get_team_poll_redis_key(member: Member) -> str:
            return f"team_poll_vote:{message.id}:{member.id}"

        teamlers: set[Member] = set()
        for role_name in self.team_roles:
            if not (team_role := guild.get_role(await RoleSettings.get(role_name))):
                continue

            teamlers.update(member for member in team_role.members if not member.bot)

        if message:
            teamlers = {
                teamler for teamler in teamlers if len(await redis.smembers(get_team_poll_redis_key(teamler))) < 1
            }

        teamlers: list[Member] = list(teamlers)

        if not teamlers:
            return t.teampoll_all_voted

        teamlers.sort(key=lambda m: str(m).lower())

        *teamlers, last = (x.mention for x in teamlers)
        teamlers: list[str]
        return t.teamlers_missing(teamlers=", ".join(teamlers), last=last, cnt=len(teamlers) + 1)

    async def on_raw_reaction_add(self, message: Message, emoji: PartialEmoji, member: Member):
        if member.bot or message.guild is None:
            return

        if await check_wastebasket(message, member, emoji, t.created_by, PollsPermission.delete):
            await message.delete()
            raise StopEventHandling

        embed, index = await get_teampoll_embed(message)
        if embed is None:
            return

        if not await is_teamler(member):
            try:
                await message.remove_reaction(emoji, member)
            except Forbidden:
                pass
            raise StopEventHandling

        for reaction in message.reactions:
            if reaction.emoji == emoji.name:
                break
        else:
            return

        if not reaction.me:
            return

        value = await self.get_reacted_teamlers(message)
        embed.set_field_at(index, name=tg.status, value=value, inline=False)
        await message.edit(embed=embed)

    async def on_raw_reaction_remove(self, message: Message, _, member: Member):
        if member.bot or message.guild is None:
            return
        embed, index = await get_teampoll_embed(message)
        if embed is not None:
            user_reacted = False
            for reaction in message.reactions:
                if reaction.me and member in await reaction.users().flatten():
                    user_reacted = True
                    break
            if not user_reacted and await is_teamler(member):
                value = await self.get_reacted_teamlers(message)
                embed.set_field_at(index, name=tg.status, value=value, inline=False)
                await message.edit(embed=embed)
                return

    @commands.command(usage=t.poll_usage, aliases=["vote"])
    @guild_only()
    async def poll(self, ctx: Context, *, args: str):
        """
        Starts a poll. Multiline options can be specified using a `\\` at the end of a line
        """

        await self.send_poll(ctx, t.poll, args)

    @commands.command(usage=t.poll_usage, aliases=["teamvote", "tp"])
    @PollsPermission.team_poll.check
    @guild_only()
    async def teampoll(self, ctx: Context, *, args: str):
        """
        Starts a poll and shows, which teamler has not voted yet.
         Multiline options can be specified using a `\\` at the end of a line
        """

        await self.send_poll(
            ctx,
            t.team_poll,
            args,
            field=(tg.status, await self.get_reacted_teamlers()),
            allow_delete=False,
            team_poll=True,
        )

    @commands.command(aliases=["yn"])
    @guild_only()
    async def yesno(self, ctx: Context, message: Optional[Message] = None, text: Optional[str] = None):
        """
        adds thumbsup and thumbsdown reactions to the message
        """

        if message is None or message.guild is None or text:
            message = ctx.message

        if message.author != ctx.author and not await is_teamler(ctx.author):
            raise CommandError(t.foreign_message)

        try:
            await message.add_reaction(name_to_emoji["thumbsup"])
            await message.add_reaction(name_to_emoji["thumbsdown"])
        except Forbidden:
            raise CommandError(t.could_not_add_reactions(message.channel.mention))

        if message != ctx.message:
            try:
                await ctx.message.add_reaction(name_to_emoji["white_check_mark"])
            except Forbidden:
                pass

    @commands.command(aliases=["tyn"])
    @PollsPermission.team_poll.check
    @guild_only()
    async def team_yesno(self, ctx: Context, *, text: str):
        """
        Starts a yes/no poll and shows, which teamler has not voted yet.
        """

        await self.send_poll(
            ctx,
            t.team_poll,
            f"""{text}
            {name_to_emoji["+1"]} {t.yes}
            {name_to_emoji["-1"]} {t.no}""",
            field=(tg.status, await self.get_reacted_teamlers()),
            allow_delete=False,
            team_poll=True,
        )


class PollOption:
    def __init__(self, ctx: Context, line: str, number: int):
        if not line:
            raise CommandError(t.empty_option)

        emoji_candidate, *text = line.lstrip().split(" ")
        text = " ".join(text)

        custom_emoji_match = re.fullmatch(r"<a?:[a-zA-Z0-9_]+:(\d+)>", emoji_candidate)
        if custom_emoji := ctx.bot.get_emoji(int(custom_emoji_match.group(1))) if custom_emoji_match else None:
            self.emoji = custom_emoji
            self.option = text.strip()
        elif (unicode_emoji := emoji_candidate) in emoji_to_name:
            self.emoji = unicode_emoji
            self.option = text.strip()
        elif (match := re.match(r"^:([^: ]+):$", emoji_candidate)) and (
            unicode_emoji := name_to_emoji.get(match.group(1).replace(":", ""))
        ):
            self.emoji = unicode_emoji
            self.option = text.strip()
        else:
            self.emoji = default_emojis[number]
            self.option = line

        if name_to_emoji["wastebasket"] == self.emoji:
            raise CommandError(t.can_not_use_wastebucket_as_option)

    def __str__(self):
        return f"{self.emoji} {self.option}" if self.option else self.emoji
