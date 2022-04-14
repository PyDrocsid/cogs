import re
import string
from argparse import ArgumentParser, Namespace
from datetime import datetime
from typing import Optional, Tuple, Union

from dateutil.relativedelta import relativedelta
from discord import Embed, Forbidden, Guild, Member, Message, Role, SelectOption
from discord.ext import commands
from discord.ext.commands import CommandError, Context, UserInputError, guild_only
from discord.ui import Select, View
from discord.utils import utcnow

from PyDrocsid.cog import Cog
from PyDrocsid.command import add_reactions, docs
from PyDrocsid.database import db, db_wrapper, filter_by
from PyDrocsid.embeds import EmbedLimits, send_long_embed
from PyDrocsid.emojis import emoji_to_name, name_to_emoji
from PyDrocsid.settings import RoleSettings
from PyDrocsid.translations import t
from PyDrocsid.util import is_teamler

from .colors import Colors
from .models import RoleWeight, TeamYesNo, YesNoUser
from .permissions import PollsPermission
from .settings import PollsDefaultSettings
from ...contributor import Contributor
from ...pubsub import send_to_changelog


tg = t.g
t = t.polls

MAX_OPTIONS = 25  # Discord select menu limit

default_emojis = [name_to_emoji[f"regional_indicator_{x}"] for x in string.ascii_lowercase]


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


def create_select_view(select: Select, timeout: float = None) -> View:
    view = View(timeout=timeout)
    view.add_item(select)

    return view


def get_percentage(values: list[float]) -> list[tuple[float, float]]:
    together = sum(values)

    return [(value, round(((value / together) * 100), 2)) for value in values]


def build_wizard(skip: bool = False) -> Embed:
    if skip:
        return Embed(title=t.skip.title, description=t.skip.description, color=Colors.Polls)

    embed = Embed(title=t.wizard.title, description=t.wizard.description, color=Colors.Polls)
    embed.add_field(name=t.wizard.arg, value=t.wizard.args, inline=False)
    embed.add_field(name=t.wizard.example.name, value=t.wizard.example.value, inline=False)
    embed.add_field(name=t.wizard.skip.name, value=t.wizard.skip.value, inline=False)

    return embed


async def get_parser() -> ArgumentParser:
    parser = ArgumentParser()
    parser.add_argument("--type", "-T", default="standard", choices=["standard", "team"], type=str)
    parser.add_argument("--deadline", "-D", default=await PollsDefaultSettings.duration.get(), type=int)
    parser.add_argument(
        "--anonymous", "-A", default=await PollsDefaultSettings.anonymous.get(), type=bool, choices=[True, False]
    )
    parser.add_argument("--choices", "-C", default=await PollsDefaultSettings.max_choices.get(), type=int)

    return parser


async def get_teampoll_embed(message: Message) -> Tuple[Optional[str], Optional[Embed], Optional[int]]:
    for embed in message.embeds:
        for i, field in enumerate(embed.fields):
            if tg.status == field.name:
                return embed.title, embed, i
    return None, None, None


async def send_poll(
    ctx: Context,
    title: str,
    poll_args: str,
    max_choices: int = None,
    field: Optional[Tuple[str, str]] = None,
    deadline: float = 0,
) -> tuple[Message, list[PollOption]]:
    if deadline != 0:
        end_time: Optional[datetime] = datetime.today() + relativedelta(hours=int(deadline))
    else:
        end_time = None

    if not max_choices or max_choices == 0:
        max_choices = t.poll_config.choices.unlimited

    question, *options = [line.replace("\x00", "\n") for line in poll_args.replace("\\\n", "\x00").split("\n") if line]

    if not options:
        raise CommandError(t.missing_options)
    if len(options) > MAX_OPTIONS:
        raise CommandError(t.too_many_options(MAX_OPTIONS))
    if field and len(options) >= MAX_OPTIONS:
        raise CommandError(t.too_many_options(MAX_OPTIONS - 1))

    options = [PollOption(ctx, line, i) for i, line in enumerate(options)]

    if any(len(str(option)) > EmbedLimits.FIELD_VALUE for option in options):
        raise CommandError(t.option_too_long(EmbedLimits.FIELD_VALUE))

    embed = Embed(title=title, description=question, color=Colors.Polls, timestamp=utcnow())
    embed.set_author(name=str(ctx.author), icon_url=ctx.author.display_avatar.url)
    if end_time:
        embed.set_footer(text=t.footer(end_time.strftime("%Y-%m-%d %H:%M:%S")))

    if len(set(map(lambda x: x.emoji, options))) < len(options):
        raise CommandError(t.option_duplicated)

    for option in options:
        embed.add_field(name=t.option.field.name(0, 0.0), value=str(option), inline=False)

    if field:
        embed.add_field(name=field[0], value=field[1], inline=False)

    if not max_choices or isinstance(max_choices, str):
        place = t.select.place
        max_value = len(options)
    else:
        use = len(options) if max_choices >= len(options) else max_choices
        place: str = t.select.placeholder(cnt=use)
        max_value = use

    msg = await ctx.send(embed=embed)
    select = MySelect(
        custom_id=str(msg.id),
        placeholder=place,
        max_values=max_value,
        options=[
            SelectOption(label=t.select.label(index + 1), emoji=option.emoji, description=option.option)
            for index, option in enumerate(options)
        ],
    )
    await ctx.send(view=create_select_view(select))

    return msg, options


async def edit_team_yn(embed: Embed, poll: TeamYesNo, missing: list[Member]) -> Embed:
    calc = get_percentage([poll.in_favor, poll.against, poll.abstention])
    for index, field in enumerate(embed.fields):
        if field.name == t.yes_no.in_favor:
            embed.set_field_at(index, name=field.name, value=t.yes_no.count(calc[0][1], cnt=calc[0][0]))
        elif field.name == t.yes_no.against:
            embed.set_field_at(index, name=field.name, value=t.yes_no.count(calc[1][1], cnt=calc[1][0]))
        elif field.name == t.yes_no.abstention:
            embed.set_field_at(index, name=field.name, value=t.yes_no.count(calc[2][1], cnt=calc[2][0]))
        if field.name == tg.status:
            missing.sort(key=lambda m: str(m).lower())
            *teamlers, last = (x.mention for x in missing)
            teamlers: list[str]
            embed.set_field_at(
                index,
                name=field.name,
                value=t.teamlers_missing(teamlers=", ".join(teamlers), last=last, cnt=len(teamlers) + 1),
            )

    return embed


async def get_teamler(guild: Guild, team_roles: list[str]) -> set[Member]:
    teamlers: set[Member] = set()
    for role_name in team_roles:
        if not (team_role := guild.get_role(await RoleSettings.get(role_name))):
            continue

        teamlers.update(member for member in team_role.members if not member.bot)

    return teamlers


class MySelect(Select):
    @db_wrapper
    async def callback(self, interaction):
        message: Message = await interaction.channel.fetch_message(interaction.custom_id)
        teamlers: set[Member] = await get_teamler(interaction.guild, ["team"])
        team_poll = await get_teampoll_embed(message)

        if team_poll[0] == t.team_yn_poll:
            if interaction.user not in teamlers:
                await interaction.response.send_message(content=t.team_yn_poll_forbidden, ephemeral=True)
                return

            poll = await db.get(TeamYesNo, message_id=message.id)

            if not (user := await db.get(YesNoUser, poll_id=message.id, user=interaction.user.id)):
                await YesNoUser.create(interaction.user.id, message.id, int(self.values[0]))
                if int(self.values[0]) == 0:
                    poll.in_favor += 1
                elif int(self.values[0]) == 1:
                    poll.against += 1
                else:
                    poll.abstention += 1
            else:
                old_user_option = int(user.option)
                user.option = int(self.values[0])
                if int(self.values[0]) == 0:
                    poll.in_favor += 1
                elif int(self.values[0]) == 1:
                    poll.against += 1
                else:
                    poll.abstention += 1

                if old_user_option == 0:
                    poll.in_favor -= 1
                elif old_user_option == 1:
                    poll.against -= 1
                else:
                    poll.abstention -= 1

            rows = await db.all(filter_by(YesNoUser, poll_id=message.id))
            user_ids = [user.user for user in rows]
            missing: list[Member] = [team for team in teamlers if team.id not in user_ids]

            embed = await edit_team_yn(team_poll[1], poll, missing)
            await message.edit(embed=embed)

        elif team_poll[0] == t.team_poll:
            if interaction.user not in teamlers:
                await interaction.response.send_message(content=t.team_yn_poll_forbidden, ephemeral=True)
                return

        else:
            pass


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

    @commands.group(name="poll", aliases=["vote"])
    @guild_only()
    @docs(t.commands.poll.poll)
    async def poll(self, ctx: Context):
        if not ctx.subcommand_passed:
            raise UserInputError

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
            value=t.poll_config.duration.time(cnt=time) if not time <= 0 else t.poll_config.duration.unlimited,
            inline=False,
        )
        choice: int = await PollsDefaultSettings.max_choices.get()
        embed.add_field(
            name=t.poll_config.choices.name,
            value=t.poll_config.choices.amount(cnt=choice) if not choice <= 0 else t.poll_config.choices.unlimited,
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
            msg: str = t.duration.set(cnt=hours)

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
            msg: str = t.votes.set(cnt=votes)

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
            msg: str = t.weight_everyone.set(cnt=weight)

        await add_reactions(ctx.message, "white_check_mark")
        await send_to_changelog(ctx.guild, msg)

    @poll.command(name="quick", usage=t.usage.poll, aliases=["q"])
    @docs(t.commands.poll.quick)
    async def quick(self, ctx: Context, *, args: str):

        await send_poll(
            ctx=ctx,
            title=t.poll,
            poll_args=args,
            max_choices=await PollsDefaultSettings.max_choices.get(),
            deadline=await PollsDefaultSettings.duration.get(),
        )

    @poll.command(name="new", usage=t.usage.poll)
    @docs(t.commands.poll.new)
    async def new(self, ctx: Context, *, options: str):
        def check(m: Message):
            return m.author == ctx.author

        wizard = await ctx.send(embed=build_wizard())
        mess: Message = await self.bot.wait_for("message", check=check, timeout=60.0)
        args = mess.content

        if args.lower() == t.skip.message:
            await wizard.edit(embed=build_wizard(True), delete_after=5.0)
        else:
            await wizard.delete(delay=5.0)
        await mess.delete()

        parser = await get_parser()
        parsed: Namespace = parser.parse_known_args(args.split(" "))[0]

        title: str = t.team_poll
        poll_type: str = parsed.type
        if poll_type.lower() == "team" and not await PollsPermission.team_poll.check_permissions(ctx.author):
            poll_type = "standard"
        if poll_type == "standard":
            title: str = t.poll
        deadline: Union[list[str, str], int] = parsed.deadline
        if isinstance(deadline, int):
            deadline: int = deadline
        else:
            deadline = await PollsDefaultSettings.duration.get()  # TODO implement parsing for datetimes
        anonymous: bool = parsed.anonymous
        print(anonymous)
        choices: int = parsed.choices

        if poll_type.lower() == "team":
            missing = list(await get_teamler(self.bot.guilds[0], ["team"]))
            missing.sort(key=lambda m: str(m).lower())
            *teamlers, last = (x.mention for x in missing)
            teamlers: list[str]
            field = (tg.status, t.teamlers_missing(teamlers=", ".join(teamlers), last=last, cnt=len(teamlers) + 1))
        else:
            field = None

        poll_message, parsed_options = await send_poll(
            ctx=ctx, title=title, poll_args=options, max_choices=choices, field=field, deadline=deadline
        )
        await ctx.message.delete()

    @commands.command(aliases=["yn"])
    @guild_only()
    @docs(t.commands.yes_no)
    async def yesno(self, ctx: Context, message: Optional[Message] = None, text: Optional[str] = None):
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
    @docs(t.commands.team_yes_no)
    async def team_yesno(self, ctx: Context, *, text: str):
        ops = [(t.yes_no.in_favor, "thumbsup", 0), (t.yes_no.against, "thumbsdown", 1), (t.yes_no.abstention, "zzz", 2)]

        embed = Embed(title=t.team_yn_poll, description=text, color=Colors.Polls, timestamp=utcnow())
        embed.set_author(name=str(ctx.author), icon_url=ctx.author.display_avatar.url)

        embed.add_field(name=t.yes_no.in_favor, value=t.yes_no.count(0, cnt=0), inline=True)
        embed.add_field(name=t.yes_no.against, value=t.yes_no.count(0, cnt=0), inline=True)
        embed.add_field(name=t.yes_no.abstention, value=t.yes_no.count(0, cnt=0), inline=True)
        missing = list(await get_teamler(self.bot.guilds[0], ["team"]))
        missing.sort(key=lambda m: str(m).lower())
        *teamlers, last = (x.mention for x in missing)
        teamlers: list[str]
        embed.add_field(
            name=tg.status,
            value=t.teamlers_missing(teamlers=", ".join(teamlers), last=last, cnt=len(teamlers) + 1),
            inline=False,
        )

        embed_msg: Message = await ctx.send(embed=embed)
        select = MySelect(
            custom_id=str(embed_msg.id),
            placeholder=t.select.placeholder(cnt=1),
            options=[SelectOption(label=op[0], emoji=name_to_emoji[op[1]], value=str(op[2])) for op in ops],
        )
        await ctx.send(view=create_select_view(select))
        await TeamYesNo.create(embed_msg.id)
