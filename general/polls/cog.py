import string
from argparse import ArgumentParser
from datetime import datetime
from typing import Optional, Tuple

from dateutil.relativedelta import relativedelta
from discord import Embed, Forbidden, Guild, Member, Message, PartialEmoji, NotFound
from discord.ext import commands
from discord.ext.commands import CommandError, Context, EmojiConverter, EmojiNotFound, guild_only
from discord.ui import Select, View
from discord.utils import utcnow

from PyDrocsid.database import db
from PyDrocsid.cog import Cog
from PyDrocsid.embeds import EmbedLimits
from PyDrocsid.emojis import emoji_to_name, name_to_emoji
from PyDrocsid.events import StopEventHandling
from PyDrocsid.settings import RoleSettings
from PyDrocsid.translations import t
from PyDrocsid.util import check_wastebasket, is_teamler

from .colors import Colors
from .models import Poll, PollType
from .permissions import PollsPermission
from .settings import PollsDefaultSettings
from ...contributor import Contributor


tg = t.g
t = t.polls

MAX_OPTIONS = 25  # Discord select menu limit

DEFAULT_EMOJIS = [name_to_emoji[f"regional_indicator_{x}"] for x in string.ascii_lowercase]


class PollOption:
    emoji: str = None
    option: str = None

    async def init(self, ctx: Context, line: str, number: int):
        if not line:
            raise CommandError(t.empty_option)

        emoji_candidate, *option = line.split()
        option = " ".join(option)
        try:
            self.emoji = str(await EmojiConverter().convert(ctx, emoji_candidate))
        except EmojiNotFound:
            if (unicode_emoji := emoji_candidate) in emoji_to_name:
                self.emoji = unicode_emoji
            else:
                self.emoji = DEFAULT_EMOJIS[number]
                option = f"{emoji_candidate} {option}"
        self.option = option

        return self

    def __str__(self):
        return f"{self.emoji} {self.option}" if self.option else self.emoji


def create_select_view(select_obj: Select, timeout: float = None) -> View:
    """returns a view object"""
    view = View(timeout=timeout)
    view.add_item(select_obj)

    return view


def get_percentage(poll: Poll) -> list[tuple[float, float]]:
    """returns the amount of votes and the percentage of an option"""
    values: list[float] = [sum([vote.vote_weight for vote in option.votes]) for option in poll.options]

    return [(float(value), float(round(((value / sum(values)) * 100), 2))) for value in values]


def build_wizard(skip: bool = False) -> Embed:
    """creates a help embed for setting up advanced polls"""
    if skip:
        return Embed(title=t.skip.title, description=t.skip.description, color=Colors.Polls)

    embed = Embed(title=t.wizard.title, description=t.wizard.description, color=Colors.Polls)
    embed.add_field(name=t.wizard.arg, value=t.wizard.args, inline=False)
    embed.add_field(name=t.wizard.example.name, value=t.wizard.example.value, inline=False)
    embed.add_field(name=t.wizard.skip.name, value=t.wizard.skip.value, inline=False)

    return embed


async def get_parser() -> ArgumentParser:
    """creates a parser object with options for advanced polls"""
    parser = ArgumentParser()
    parser.add_argument(
        "--type",
        "-T",
        default=PollType.STANDARD.value,
        choices=[PollType.STANDARD.value, PollType.TEAM.value],
        type=str,
    )
    parser.add_argument("--deadline", "-D", default=await PollsDefaultSettings.duration.get(), type=int)
    parser.add_argument(
        "--anonymous", "-A", default=await PollsDefaultSettings.anonymous.get(), type=bool, choices=[True, False]
    )
    parser.add_argument(
        "--choices", "-C", default=await PollsDefaultSettings.max_choices.get() or MAX_OPTIONS, type=int
    )
    parser.add_argument("--fair", "-F", default=await PollsDefaultSettings.fair.get(), type=bool, choices=[True, False])

    return parser


def calc_end_time(duration: Optional[float]) -> Optional[datetime]:
    """returns the time when a poll should be closed"""
    return utcnow() + relativedelta(hours=int(duration)) if duration else None


async def handle_deleted_messages(bot, message_id: int):
    """if a message containing a poll gets deleted, this function deletes the interaction message (both direction)"""
    deleted_embed: Poll | None = await db.get(Poll, message_id=message_id)
    deleted_interaction: Poll | None = await db.get(Poll, interaction_message_id=message_id)

    if not deleted_embed and not deleted_interaction:
        return

    poll = deleted_embed or deleted_interaction
    channel = await bot.fetch_channel(poll.channel_id)
    try:
        if deleted_interaction:
            msg: Message | None = await channel.fetch_message(poll.message_id)
        else:
            msg: Message | None = await channel.fetch_message(poll.interaction_message_id)
    except NotFound:
        msg = None

    if msg:
        await poll.remove()
        await msg.delete()


async def check_poll_time(poll: Poll) -> bool:
    """checks if a poll has ended"""
    if not poll.end_time:
        await poll.remove()
        return False

    elif poll.end_time < utcnow():
        return False

    return True


async def close_poll(bot, poll: Poll):
    """deletes the interaction message and edits the footer of the poll embed"""
    try:
        channel = await bot.fetch_channel(poll.channel_id)
        embed_message = await channel.fetch_message(poll.message_id)
        interaction_message = await channel.fetch_message(poll.interaction_message_id)
    except NotFound:
        poll.active = False
        return

    await interaction_message.delete()
    embed = embed_message.embeds[0]
    embed.set_footer(text=t.footer_closed)

    await embed_message.edit(embed=embed)
    await embed_message.unpin()

    poll.active = False


async def get_staff(guild: Guild, team_roles: list[str]) -> set[Member]:
    """gets a list of all team members"""
    teamlers: set[Member] = set()
    for role_name in team_roles:
        if not (team_role := guild.get_role(await RoleSettings.get(role_name))):
            continue

        teamlers.update(member for member in team_role.members if not member.bot)

    if not teamlers:
        raise CommandError(t.error.no_teamlers)

    return teamlers


async def edit_poll_embed(embed: Embed, poll: Poll, missing: list[Member] = None) -> Embed:
    """edits the poll embed, updating the votes and percentages"""
    calc = get_percentage(poll)
    for index, field in enumerate(embed.fields):
        if field.name == tg.status:
            missing.sort(key=lambda m: str(m).lower())
            *teamlers, last = (x.mention for x in missing)
            teamlers: list[str]
            embed.set_field_at(
                index,
                name=field.name,
                value=t.teamlers_missing(teamlers=", ".join(teamlers), last=last, cnt=len(teamlers) + 1),
            )
        else:
            weight: float | int = calc[index][0] if not calc[index][0].is_integer() else int(calc[index][0])
            percentage: float | int = calc[index][1] if not calc[index][1].is_integer() else int(calc[index][1])
            embed.set_field_at(index, name=t.option.field.name(weight, percentage), value=field.value, inline=False)

    return embed


async def get_teampoll_embed(message: Message) -> Tuple[Optional[Embed], Optional[int]]:
    for embed in message.embeds:
        for i, field in enumerate(embed.fields):
            if tg.status == field.name:
                return embed, i
    return None, None


async def send_poll(
    ctx: Context, title: str, args: str, field: Optional[Tuple[str, str]] = None, allow_delete: bool = True
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

    if len({x.emoji for x in options}) < len(options):
        raise CommandError(t.option_duplicated)

    for option in options:
        embed.add_field(name="** **", value=str(option), inline=False)

    if field:
        embed.add_field(name=field[0], value=field[1], inline=False)

    poll: Message = await ctx.send(embed=embed)

    try:
        for option in options:
            await poll.add_reaction(option.emoji)
        if allow_delete:
            await poll.add_reaction(name_to_emoji["wastebasket"])
    except Forbidden:
        raise CommandError(t.could_not_add_reactions(ctx.channel.mention))


class PollsCog(Cog, name="Polls"):
    CONTRIBUTORS = [Contributor.MaxiHuHe04, Contributor.Defelo, Contributor.TNT2k, Contributor.wolflu]

    def __init__(self, team_roles: list[str]):
        self.team_roles: list[str] = team_roles

    async def get_reacted_teamlers(self, message: Optional[Message] = None) -> str:
        guild: Guild = self.bot.guilds[0]

        teamlers: set[Member] = set()
        for role_name in self.team_roles:
            if not (team_role := guild.get_role(await RoleSettings.get(role_name))):
                continue

            teamlers.update(member for member in team_role.members if not member.bot)

        if message:
            for reaction in message.reactions:
                if reaction.me:
                    teamlers.difference_update(await reaction.users().flatten())

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

        await send_poll(ctx, t.poll, args)

    @commands.command(usage=t.poll_usage, aliases=["teamvote", "tp"])
    @PollsPermission.team_poll.check
    @guild_only()
    async def teampoll(self, ctx: Context, *, args: str):
        """
        Starts a poll and shows, which teamler has not voted yet.
         Multiline options can be specified using a `\\` at the end of a line
        """

        await send_poll(
            ctx, t.team_poll, args, field=(tg.status, await self.get_reacted_teamlers()), allow_delete=False
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

        embed = Embed(title=t.team_poll, description=text, color=Colors.Polls, timestamp=utcnow())
        embed.set_author(name=str(ctx.author), icon_url=ctx.author.display_avatar.url)

        embed.add_field(name=tg.status, value=await self.get_reacted_teamlers(), inline=False)

        message: Message = await ctx.send(embed=embed)
        try:
            await message.add_reaction(name_to_emoji["+1"])
            await message.add_reaction(name_to_emoji["-1"])
        except Forbidden:
            raise CommandError(t.could_not_add_reactions(message.channel.mention))
