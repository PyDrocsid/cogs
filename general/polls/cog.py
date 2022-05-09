import re
import string
from argparse import ArgumentParser, Namespace
from datetime import datetime
from typing import Optional, Union

from dateutil.relativedelta import relativedelta
from discord import (
    Embed,
    Forbidden,
    Guild,
    HTTPException,
    Member,
    Message,
    NotFound,
    RawMessageDeleteEvent,
    Role,
    SelectOption,
)
from discord.ext import commands, tasks
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
from .models import Option, Poll, PollVote, RoleWeight
from .permissions import PollsPermission
from .settings import PollsDefaultSettings
from ...contributor import Contributor
from ...pubsub import send_alert, send_to_changelog


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
            self.emoji = str(custom_emoji)
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

    def __str__(self):
        return f"{self.emoji} {self.option}" if self.option else self.emoji


def create_select_view(select_obj: Select, timeout: float = None) -> View:
    view = View(timeout=timeout)
    view.add_item(select_obj)

    return view


def get_percentage(poll: Poll) -> list[tuple[float, float]]:
    values: list[float] = []
    options = poll.options

    for option in options:
        values.append(sum([vote.vote_weight for vote in option.votes]))

    return [(float(value), float(round(((value / sum(values)) * 100), 2))) for value in values]


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
    parser.add_argument("--fair", "-F", default=await PollsDefaultSettings.fair.get(), type=bool, choices=[True, False])

    return parser


def calc_end_time(duration: Optional[float]) -> Optional[datetime]:
    if duration != 0 and not None:
        return utcnow() + relativedelta(hours=int(duration))
    return


async def send_poll(
    ctx: Context,
    title: str,
    poll_args: str,
    max_choices: int = None,
    field: Optional[tuple[str, str]] = None,
    deadline: Optional[float] = None,
) -> tuple[Message, Message, list[tuple[str, str]], str]:

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

    if deadline:
        end_time = calc_end_time(deadline)
        embed.set_footer(text=t.footer(end_time.strftime("%Y-%m-%d %H:%M")))

    if len(set(map(lambda x: x.emoji, options))) < len(options):
        raise CommandError(t.option_duplicated)

    for option in options:
        embed.add_field(name=t.option.field.name(0, 0), value=str(option), inline=False)

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
    select_obj = MySelect(
        custom_id=str(msg.id),
        placeholder=place,
        max_values=max_value,
        options=[
            SelectOption(label=t.select.label(index + 1), emoji=option.emoji, description=option.option)
            for index, option in enumerate(options)
        ],
    )
    view_msg = await ctx.send(view=create_select_view(select_obj=select_obj))
    parsed_options: list[tuple[str, str]] = [
        (obj.emoji, t.select.label(index + 1)) for index, obj in enumerate(options)
    ]
    try:
        await msg.pin()
    except HTTPException:
        embed = Embed(
            title=t.error.cant_pin.title,
            description=t.error.cant_pin.description(ctx.channel.mention),
            color=Colors.error,
        )
        await send_alert(ctx.guild, embed)
    return msg, view_msg, parsed_options, question


async def edit_poll_embed(embed: Embed, poll: Poll, missing: list[Member] = None) -> Embed:
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


async def get_teamler(guild: Guild, team_roles: list[str]) -> set[Member]:
    teamlers: set[Member] = set()
    for role_name in team_roles:
        if not (team_role := guild.get_role(await RoleSettings.get(role_name))):
            continue

        teamlers.update(member for member in team_role.members if not member.bot)

    return teamlers


async def handle_deleted_messages(bot, message_id: int):
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
    if not poll.end_time:
        await poll.remove()
        return False

    elif poll.end_time < utcnow():
        return False

    return True


async def close_poll(bot, poll: Poll):
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


class MySelect(Select):
    @db_wrapper
    async def callback(self, interaction):
        user = interaction.user
        selected_options: list = self.values
        message: Message = await interaction.channel.fetch_message(interaction.custom_id)
        embed: Embed = message.embeds[0] if message.embeds else None
        poll: Poll = await db.get(Poll, (Poll.options, Option.votes), message_id=message.id)
        if not poll or not embed:
            return

        options: list[Option] = poll.options
        new_options: list[Option] = [option for option in options if option.option in selected_options]
        missing: list[Member] | None = None

        opt: Option
        for opt in poll.options:
            for vote in opt.votes:
                if vote.user_id == user.id:
                    await vote.remove()
                    opt.votes.remove(vote)

        if poll.fair:
            user_weight: float = await PollsDefaultSettings.everyone_power.get()
        else:
            user_weight: float = 1.0  # TODO: Add function to get user vote weight
        for option in new_options:
            option.votes.append(
                await PollVote.create(option_id=option.id, user_id=user.id, poll_id=poll.id, vote_weight=user_weight)
            )
        if poll.poll_type == "team":
            teamlers: set[Member] = await get_teamler(interaction.guild, ["team"])
            if user not in teamlers:
                await interaction.response.send_message(content=t.team_yn_poll_forbidden, ephemeral=True)
                return

            user_ids: set[int] = set()
            for option in poll.options:
                for vote in option.votes:
                    user_ids.add(vote.user_id)

            missing: list[Member] | None = [teamler for teamler in teamlers if teamler.id not in user_ids]
            missing.sort(key=lambda m: str(m).lower())

        embed = await edit_poll_embed(embed, poll, missing)
        await message.edit(embed=embed)


class PollsCog(Cog, name="Polls"):
    CONTRIBUTORS = [
        Contributor.MaxiHuHe04,
        Contributor.Defelo,
        Contributor.TNT2k,
        Contributor.wolflu,
        Contributor.NekoFanatic,  # rewrote most of this code
    ]

    def __init__(self, team_roles: list[str]):
        self.team_roles: list[str] = team_roles

    async def on_ready(self):
        polls: list[Poll] = await db.all(filter_by(Poll, (Poll.options, Option.votes), active=True))
        for poll in polls:
            if await check_poll_time(poll):
                select_obj = MySelect(
                    custom_id=str(poll.message_id),
                    placeholder=t.select.placeholder(cnt=poll.max_choices),
                    max_values=poll.max_choices,
                    options=[
                        SelectOption(
                            label=t.select.label(option.field_position + 1),
                            emoji=option.emote,
                            description=option.option,
                        )
                        for option in poll.options
                    ],
                )

                self.bot.add_view(view=create_select_view(select_obj), message_id=poll.interaction_message_id)

        try:
            self.poll_loop.start()
        except RuntimeError:
            self.poll_loop.restart()

    async def on_message_delete(self, message: Message):
        await handle_deleted_messages(self.bot, message.id)

    async def on_raw_message_delete(self, event: RawMessageDeleteEvent):
        await handle_deleted_messages(self.bot, event.message_id)

    @tasks.loop(minutes=1)
    @db_wrapper
    async def poll_loop(self):
        polls: list[Poll] = await db.all(filter_by(Poll, active=True))

        for poll in polls:
            if not await check_poll_time(poll):
                await close_poll(self.bot, poll)

    @commands.group(name="poll", aliases=["vote"])
    @guild_only()
    @docs(t.commands.poll.poll)
    async def poll(self, ctx: Context):
        if not ctx.subcommand_passed:
            raise UserInputError

    @poll.command(name="list", aliases=["l"])
    @guild_only()
    @docs(t.commands.poll.list)
    async def list(self, ctx: Context):
        polls: list[Poll] = await db.all(filter_by(Poll, active=True, guild_id=ctx.guild.id))
        if polls:
            description = ""
            for poll in polls:
                if poll.poll_type == "team" and not await PollsPermission.team_poll.check_permissions(ctx.author):
                    continue
                if poll.poll_type == "team":
                    description += t.polls.team_row(
                        poll.title, poll.message_url, poll.owner_id, poll.end_time.strftime("%Y-%m-%d %H:%M")
                    )
                else:
                    description += t.polls.row(
                        poll.title, poll.message_url, poll.owner_id, poll.end_time.strftime("%Y-%m-%d %H:%M")
                    )

            embed: Embed = Embed(title=t.polls.title, description=description, color=Colors.Polls)

            await send_long_embed(ctx, embed=embed, paginate=True)

    @poll.command(name="delete", aliases=["del"])
    @docs(t.commands.poll.delete)
    async def delete(self, ctx: Context, message: Message):
        poll: Poll = await db.get(Poll, message_id=message.id)
        if not poll:
            raise CommandError(t.error.not_poll)
        if not await PollsPermission.delete.check_permissions(ctx.author) and not poll.owner_id == ctx.author.id:
            raise PermissionError

        await message.delete()
        await poll.remove()
        interaction_message: Message = await ctx.channel.fetch_message(poll.interaction_message_id)
        if interaction_message:
            await interaction_message.delete()

        await add_reactions(ctx.message, "white_check_mark")

    @poll.command(name="voted", aliases=["v"])
    @docs(t.commands.poll.voted)
    async def voted(self, ctx: Context, message: Message):
        poll: Poll = await db.get(Poll, (Poll.options, Option.votes), message_id=message.id)
        author = ctx.author
        if not poll:
            raise CommandError(t.error.not_poll)
        if (
            poll.anonymous
            and not await PollsPermission.anonymous_bypass.check_permissions(author)
            and not poll.owner_id == author.id
        ):
            raise PermissionError

        users: dict[str, list[int]] = {}
        for option in poll.options:
            for vote in option.votes:
                try:
                    users[str(vote.user_id)].append(option.field_position + 1)
                except KeyError:
                    users[str(vote.user_id)] = [option.field_position + 1]

        description = ""
        for key, value in users.items():
            description += t.voted.row(key, value)
        embed = Embed(title=t.voted.title, description=description, color=Colors.Polls)

        await send_long_embed(ctx, embed=embed, repeat_title=True, paginate=True)

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
        max_time: int = await PollsDefaultSettings.max_duration.get()
        embed.add_field(
            name=t.poll_config.duration.name,
            value=t.poll_config.duration.time(cnt=time) if not time <= 0 else t.poll_config.duration.time(cnt=max_time),
            inline=False,
        )
        embed.add_field(
            name=t.poll_config.max_duration.name, value=t.poll_config.max_duration.time(cnt=max_time), inline=False
        )
        choice: int = await PollsDefaultSettings.max_choices.get()
        embed.add_field(
            name=t.poll_config.choices.name,
            value=t.poll_config.choices.amount(cnt=choice) if not choice <= 0 else t.poll_config.choices.unlimited,
            inline=False,
        )
        anonymous: bool = await PollsDefaultSettings.anonymous.get()
        embed.add_field(name=t.poll_config.anonymous.name, value=str(anonymous), inline=False)
        roles = await RoleWeight.get(ctx.guild.id)
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
            await RoleWeight.create(ctx.guild.id, role.id, weight)
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

    @settings.command(name="max_duration", aliases=["md"])
    @PollsPermission.write.check
    @docs(t.commands.poll.settings.max_duration)
    async def max_duration(self, ctx: Context, days: int = None):
        if not days:
            days = 7
        msg: str = t.max_duration.set(cnt=days)

        await PollsDefaultSettings.max_duration.set(days)
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

    @settings.command(name="fair", aliases=["f"])
    @PollsPermission.write.check
    @docs(t.commands.poll.settings.fair)
    async def fair(self, ctx: Context, status: bool):
        if status:
            msg: str = t.fair.is_on
        else:
            msg: str = t.fair.is_off

        await PollsDefaultSettings.fair.set(status)
        await add_reactions(ctx.message, "white_check_mark")
        await send_to_changelog(ctx.guild, msg)

    @poll.command(name="quick", usage=t.usage.poll, aliases=["q"])
    @docs(t.commands.poll.quick)
    async def quick(self, ctx: Context, *, args: str):
        deadline = await PollsDefaultSettings.duration.get()
        if deadline == 0:
            deadline = await PollsDefaultSettings.max_duration.get()
        max_choices = await PollsDefaultSettings.max_choices.get()
        anonymous = await PollsDefaultSettings.anonymous.get()
        message, interaction, parsed_options, question = await send_poll(
            ctx=ctx, title=t.poll, poll_args=args, max_choices=max_choices, deadline=deadline
        )

        await Poll.create(
            message_id=message.id,
            message_url=message.jump_url,
            guild_id=ctx.guild.id,
            channel=message.channel.id,
            owner=ctx.author.id,
            title=question,
            end=calc_end_time(deadline),
            anonymous=anonymous,
            can_delete=True,
            options=parsed_options,
            poll_type=await PollsDefaultSettings.type.get(),
            interaction=interaction.id,
            fair=await PollsDefaultSettings.fair.get(),
            max_choices=max_choices,
        )

        await ctx.message.delete()

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
            deadline = (
                deadline
                if deadline >= await PollsDefaultSettings.max_duration.get()
                else await PollsDefaultSettings.max_duration.get()
            )
        else:
            if await PollsDefaultSettings.duration.get() == 0:
                deadline = await PollsDefaultSettings.max_duration.get()
            else:
                deadline = await PollsDefaultSettings.duration.get()
        anonymous: bool = parsed.anonymous
        choices: int = parsed.choices

        if poll_type.lower() == "team":
            can_delete, fair = False, True
            missing = list(await get_teamler(self.bot.guilds[0], ["team"]))
            missing.sort(key=lambda m: str(m).lower())
            *teamlers, last = (x.mention for x in missing)
            teamlers: list[str]
            field = (tg.status, t.teamlers_missing(teamlers=", ".join(teamlers), last=last, cnt=len(teamlers) + 1))
        else:
            can_delete, fair = True, parsed.fair
            field = None

        message, interaction, parsed_options, question = await send_poll(
            ctx=ctx, title=title, poll_args=options, max_choices=choices, field=field, deadline=deadline
        )
        await ctx.message.delete()

        await Poll.create(
            message_id=message.id,
            message_url=message.jump_url,
            guild_id=ctx.guild.id,
            channel=message.channel.id,
            owner=ctx.author.id,
            title=question,
            end=calc_end_time(deadline),
            anonymous=anonymous,
            can_delete=can_delete,
            options=parsed_options,
            poll_type=poll_type.lower(),
            interaction=interaction.id,
            fair=fair,
            max_choices=choices,
        )

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
        options = t.yes_no.option_string(text)

        missing = list(await get_teamler(self.bot.guilds[0], ["team"]))
        missing.sort(key=lambda m: str(m).lower())
        *teamlers, last = (x.mention for x in missing)
        teamlers: list[str]
        field = (tg.status, t.teamlers_missing(teamlers=", ".join(teamlers), last=last, cnt=len(teamlers) + 1))

        message, interaction, parsed_options, question = await send_poll(
            ctx=ctx,
            title=t.team_poll,
            max_choices=1,
            poll_args=options,
            field=field,
            deadline=await PollsDefaultSettings.max_duration.get() * 24,
        )
        await Poll.create(
            message_id=message.id,
            message_url=message.jump_url,
            guild_id=ctx.guild.id,
            channel=message.channel.id,
            owner=ctx.author.id,
            title=question,
            end=calc_end_time(await PollsDefaultSettings.max_duration.get() * 24),
            anonymous=False,
            can_delete=False,
            options=parsed_options,
            poll_type="team",
            interaction=interaction.id,
            fair=True,
            max_choices=1,
        )
