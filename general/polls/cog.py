import re
import string
from typing import Optional, Tuple

from discord import Embed, Forbidden, Guild, Member, Message, PartialEmoji, Role, SelectOption
from discord.ext import commands
from discord.ext.commands import CommandError, Context, UserInputError, guild_only
from discord.ui import Select, View
from discord.utils import utcnow

from PyDrocsid.cog import Cog
from PyDrocsid.command import add_reactions, docs
from PyDrocsid.database import db
from PyDrocsid.embeds import EmbedLimits, send_long_embed
from PyDrocsid.emojis import emoji_to_name, name_to_emoji
from PyDrocsid.events import StopEventHandling
from PyDrocsid.settings import RoleSettings
from PyDrocsid.translations import t
from PyDrocsid.util import check_wastebasket, is_teamler

from .colors import Colors
from .models import RoleWeight
from .permissions import PollsPermission
from .settings import PollsDefaultSettings
from ...contributor import Contributor
from ...pubsub import send_to_changelog


tg = t.g
t = t.polls

MAX_OPTIONS = 25  # Discord select menu limit

default_emojis = [name_to_emoji[f"regional_indicator_{x}"] for x in string.ascii_lowercase]


async def get_teampoll_embed(message: Message) -> Tuple[Optional[Embed], Optional[int]]:
    for embed in message.embeds:
        for i, field in enumerate(embed.fields):
            if tg.status == field.name:
                return embed, i
    return None, None


async def send_poll(
    ctx: Context,
    title: str,
    args: str,
    max_choices: int = None,
    field: Optional[Tuple[str, str]] = None,
    allow_delete: bool = True,
):
    question, *options = [line.replace("\x00", "\n") for line in args.replace("\\\n", "\x00").split("\n") if line]

    if not options:
        raise CommandError(t.missing_options)
    if len(options) > MAX_OPTIONS:
        raise CommandError(t.too_many_options(MAX_OPTIONS))

    options = [PollOption(ctx, line, i) for i, line in enumerate(options)]

    if any(len(str(option)) > EmbedLimits.FIELD_VALUE for option in options):
        raise CommandError(t.option_too_long(EmbedLimits.FIELD_VALUE))

    embed = Embed(title=title, description=question, color=Colors.Polls, timestamp=utcnow())
    embed.set_author(name=str(ctx.author), icon_url=ctx.author.display_avatar.url)
    if allow_delete:
        embed.set_footer(text=t.created_by(ctx.author, ctx.author.id), icon_url=ctx.author.display_avatar.url)

    if len(set(map(lambda x: x.emoji, options))) < len(options):
        raise CommandError(t.option_duplicated)

    for option in options:
        embed.add_field(name="** **", value=str(option), inline=False)

    if field:
        embed.add_field(name=field[0], value=field[1], inline=False)

    if not max_choices:
        place = t.select.place
        max_value = len(options)
    else:
        place: str = t.select.placeholder(max_choices)
        max_value = len(options) if max_choices >= len(options) else max_choices

    select = Select(
        placeholder=place,
        max_values=max_value,
        options=[
            SelectOption(label=t.select.label(index + 1), emoji=option.emoji, description=option.option)
            for index, option in enumerate(options)
        ],
    )

    view = View()
    view.add_item(select)
    await ctx.send(embed=embed, view=view)


class PollsCog(Cog, name="Polls"):
    CONTRIBUTORS = [
        Contributor.MaxiHuHe04,
        Contributor.Defelo,
        Contributor.TNT2k,
        Contributor.wolflu,
        Contributor.NekoFanatic,
    ]

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

    @commands.group(name="poll", aliases=["vote"])
    @guild_only()
    @docs(t.commands.poll.poll)
    async def poll(self, ctx: Context):
        if not ctx.subcommand_passed:
            raise UserInputError

    @poll.command(name="quick", usage=t.poll_usage, aliases=["q"])
    @docs(t.commands.poll.quick)
    async def quick(self, ctx: Context, *, args: str):

        await send_poll(ctx, t.poll, args, await PollsDefaultSettings.max_choices.get())

    @poll.group(name="settings", aliases=["s"])
    @PollsPermission.read.check
    @docs(t.commands.poll.settings.settings)
    async def settings(self, ctx: Context):
        if ctx.subcommand_passed is not None:
            if ctx.invoked_subcommand is None:
                raise UserInputError
            return

        embed = Embed(title=t.poll_config.title, color=Colors.Polls)
        time: int = await PollsDefaultSettings.duration.get()
        embed.add_field(
            name=t.poll_config.duration.name,
            value=t.poll_config.duration.time(time) if not time <= 0 else t.poll_config.duration.unlimited,
            inline=False,
        )
        choice: int = await PollsDefaultSettings.max_choices.get()
        embed.add_field(
            name=t.poll_config.choices.name,
            value=t.poll_config.choices.amount(choice) if not choice <= 0 else t.poll_config.choices.unlimited,
            inline=False,
        )
        hide: bool = await PollsDefaultSettings.hidden.get()
        embed.add_field(name=t.poll_config.hidden.name, value=str(hide), inline=False)
        anonymous: bool = await PollsDefaultSettings.anonymous.get()
        embed.add_field(name=t.poll_config.anonymous.name, value=str(anonymous), inline=False)
        roles = await RoleWeight.get()
        everyone: int = await PollsDefaultSettings.everyone_power.get()
        base: str = t.poll_config.roles.ev_row(ctx.guild.default_role, everyone)
        if roles:
            base += "".join([t.poll_config.roles.row(role.role_id, role.weight) for role in roles])
        embed.add_field(name=t.poll_config.roles.name, value=base, inline=False)

        await send_long_embed(ctx, embed, paginate=False)

    @settings.command(name="roles_weights", aliases=["rw"])
    @PollsPermission.write.check
    @docs(t.commands.poll.settings.roles_weights)
    async def roles_weights(self, ctx: Context, role: Role, weight: float = None):
        element = await db.get(RoleWeight, role_id=role.id)

        if not weight and not element:
            raise CommandError(t.error.cant_set_weight)

        if weight and weight < 0.1:
            raise CommandError(t.error.weight_too_small)

        if element and weight:
            element.weight = weight
            msg: str = t.role_weight.set(role.id, weight)
        elif weight and not element:
            await RoleWeight.create(role.id, weight)
            msg: str = t.role_weight.set(role.id, weight)
        else:
            await element.remove()
            msg: str = t.role_weight.reset(role.id)

        await add_reactions(ctx.message, "white_check_mark")
        await send_to_changelog(ctx.guild, msg)

    @settings.command(name="duration", aliases=["d"])
    @PollsPermission.write.check
    @docs(t.commands.poll.settings.duration)
    async def duration(self, ctx: Context, hours: int = None):
        if not hours:
            hours = 0
            msg: str = t.duration.reset()
        else:
            msg: str = t.duration.set(hours)

        await PollsDefaultSettings.duration.set(hours)
        await add_reactions(ctx.message, "white_check_mark")
        await send_to_changelog(ctx.guild, msg)

    @settings.command(name="votes", aliases=["v", "choices", "c"])
    @PollsPermission.write.check
    @docs(t.commands.poll.settings.votes)
    async def votes(self, ctx: Context, votes: int = None):
        if not votes:
            votes = 0
            msg: str = t.votes.reset
        else:
            msg: str = t.votes.set(votes)

        if not 0 < votes < 25:
            votes = 0

        await PollsDefaultSettings.max_choices.set(votes)
        await add_reactions(ctx.message, "white_check_mark")
        await send_to_changelog(ctx.guild, msg)

    @settings.command(name="hidden", aliases=["h"])
    @PollsPermission.write.check
    @docs(t.commands.poll.settings.hidden)
    async def hidden(self, ctx: Context, status: bool):
        if status:
            msg: str = t.hidden.hidden
        else:
            msg: str = t.hidden.not_hidden

        await PollsDefaultSettings.hidden.set(status)
        await add_reactions(ctx.message, "white_check_mark")
        await send_to_changelog(ctx.guild, msg)

    @settings.command(name="anonymous", aliases=["a"])
    @PollsPermission.write.check
    @docs(t.commands.poll.settings.anonymous)
    async def anonymous(self, ctx: Context, status: bool):
        if status:
            msg: str = t.anonymous.is_on
        else:
            msg: str = t.anonymous.is_off

        await PollsDefaultSettings.anonymous.set(status)
        await add_reactions(ctx.message, "white_check_mark")
        await send_to_changelog(ctx.guild, msg)

    @settings.command(name="everyone", aliases=["e"])
    @PollsPermission.write.check
    @docs(t.commands.poll.settings.everyone)
    async def everyone(self, ctx: Context, weight: float = None):
        if weight and weight < 0.1:
            raise CommandError(t.error.weight_too_small)

        if not weight:
            await PollsDefaultSettings.everyone_power.set(1.0)
            msg: str = t.weight_everyone.reset
        else:
            await PollsDefaultSettings.everyone_power.set(weight)
            msg: str = t.weight_everyone.set(weight)

        await add_reactions(ctx.message, "white_check_mark")
        await send_to_changelog(ctx.guild, msg)

    @commands.command(usage=t.poll_usage, aliases=["teamvote", "tp"])
    @PollsPermission.team_poll.check
    @guild_only()
    async def teampoll(self, ctx: Context, *, args: str):
        """
        Starts a poll and shows, which teamler has not voted yet.
         Multiline options can be specified using a `\\` at the end of a line
        """

        await send_poll(
            ctx,
            t.team_poll,
            args,
            await PollsDefaultSettings.max_choices.get(),
            field=(tg.status, await self.get_reacted_teamlers()),
            allow_delete=False,
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
