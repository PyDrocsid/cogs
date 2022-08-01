import shlex
import string
from argparse import ArgumentParser
from datetime import datetime
from io import BytesIO

import matplotlib.pyplot as plt
import numpy as np
from dateutil.relativedelta import relativedelta
from discord import (
    Embed,
    File,
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
from discord.ext.commands import (
    BadArgument,
    Bot,
    CommandError,
    Context,
    EmojiConverter,
    EmojiNotFound,
    RoleConverter,
    UserInputError,
    guild_only,
)
from discord.ui import Select, View
from discord.utils import format_dt, utcnow

from PyDrocsid.cog import Cog
from PyDrocsid.command import Confirmation, add_reactions, docs, optional_permissions
from PyDrocsid.database import db, db_wrapper, filter_by
from PyDrocsid.embeds import EmbedLimits, send_long_embed
from PyDrocsid.emojis import emoji_to_name, name_to_emoji
from PyDrocsid.settings import RoleSettings
from PyDrocsid.translations import t
from PyDrocsid.util import is_teamler

from .colors import Colors
from .models import IgnoredUser, Option, Poll, PollStatus, PollType, PollVote, RoleWeight, sync_redis
from .permissions import PollsPermission
from .settings import PollsDefaultSettings as PdS
from .settings import PollsTeamSettings as PtS
from ...contributor import Contributor
from ...pubsub import send_alert, send_to_changelog


tg = t.g
t = t.polls

MAX_OPTIONS = 25  # Discord select menu limit
DEFAULT_EMOJIS = [name_to_emoji[f"regional_indicator_{x}"] for x in string.ascii_lowercase]


class PollOption:
    emoji: str = None
    option: str = None

    async def init(self, ctx: Context, line: str, number: int):
        if not line:
            raise CommandError(t.error.empty_option)

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


class RoleParser:
    def __init__(self, ctx: Context):
        self.ctx = ctx

    async def parse_roles(self, raw: str) -> list[int]:
        out: list[int] = []
        parsed = raw.replace(" ", "").split(",")
        for role_str in parsed:
            try:
                role: Role = await RoleConverter().convert(self.ctx, role_str)
                out.append(role.id)
            except BadArgument:
                continue

        return out

    async def parse_weights(self, raw: str) -> list[tuple[int, float]]:
        out: list[tuple[int, float]] = []
        parsed = raw.replace(" ", "").split(",")
        for role_str in parsed:
            spl = role_str.split(":")
            if not len(spl) == 2:
                continue
            try:
                weight = float(spl[1])
            except ValueError:
                continue
            try:
                role: Role = await RoleConverter().convert(self.ctx, spl[0])
                out.append((role.id, weight))
            except BadArgument:
                continue

        return out


def create_select_view(select_obj: Select, timeout: float = None) -> View:
    """returns a view object"""
    view = View(timeout=timeout)
    view.add_item(select_obj)

    return view


def build_wizard(skip: bool = False) -> Embed:
    """creates a help embed for setting up advanced polls"""
    if skip:
        return Embed(title=t.wizard.skip.skipped.title, description=t.wizard.skip.skipped.desc, color=Colors.Polls)

    embed = Embed(title=t.wizard.title, description=t.wizard.desc, color=Colors.Polls)
    embed.add_field(name=t.wizard.args.name, value=t.wizard.args.value, inline=False)
    embed.add_field(name=t.wizard.example.name, value=t.wizard.example.value, inline=False)
    embed.add_field(name=t.wizard.skip.name, value=t.wizard.skip.value, inline=False)

    return embed


async def get_parser() -> ArgumentParser:
    """creates a parser object with options for advanced polls"""
    parser = ArgumentParser()
    parser.add_argument("--deadline", "-D", default=0, type=int)
    parser.add_argument("--anonymous", "-A", default=False, type=bool, choices=[True, False])
    parser.add_argument("--choices", "-C", default=MAX_OPTIONS, type=int)
    parser.add_argument("--roles", "-R", default="none", type=str)
    parser.add_argument("--weights", "-W", default="none", type=str)

    return parser


def calc_end_time(duration: float | None) -> datetime | None:
    """returns the time when a poll should be closed"""
    return utcnow() + relativedelta(seconds=int(duration)) if duration else None


async def send_poll(
    ctx: Context,
    title: str,
    poll_args: str,
    max_choices: int = None,
    team_poll: bool = False,
    deadline: int | None = None,
    anonymous: bool = False,
    allowed_roles: list[int] | None = None,
    weights: list[tuple[int, float]] | None = None,
):
    """sends a poll embed + view message containing the select field"""

    if not max_choices:
        max_choices = t.poll_config.choices.unlimited

    question, *options = [line.replace("\x00", "\n") for line in poll_args.replace("\\\n", "\x00").split("\n") if line]

    if not options:
        raise CommandError(t.error.missing_options)
    if len(options) > MAX_OPTIONS:
        raise CommandError(t.error.too_many_options(MAX_OPTIONS))

    options = [await PollOption().init(ctx, line, i) for i, line in enumerate(options)]

    if any(len(str(option)) > EmbedLimits.FIELD_VALUE for option in options):
        raise CommandError(t.error.option_too_long(EmbedLimits.FIELD_VALUE))

    if not max_choices or isinstance(max_choices, str):
        place = t.poll.select.place
        max_value = len(options)
    else:
        options_amount = len(options) if max_choices >= len(options) else max_choices
        place: str = t.poll.select.placeholder(cnt=options_amount)
        max_value = options_amount

    embed = Embed(title=title, description=question, color=Colors.Polls, timestamp=utcnow())
    embed.set_author(name=str(ctx.author), icon_url=ctx.author.display_avatar.url)

    embed.add_field(name=t.poll.choices.name, value=str(max_value))
    if allowed_roles:
        embed.add_field(name=t.poll.roles.name, value=" ".join([f"<@&{role}>" for role in allowed_roles]))
    if weights:
        embed.add_field(
            name=t.poll.weights.name, value=" ".join([f"<@&{role}>: `{weight}`" for role, weight in weights])
        )

    if deadline:
        embed.set_footer(text=t.poll.footer.default(calc_end_time(deadline).strftime("%Y-%m-%d %H:%M")))

    if len({option.emoji for option in options}) < len(options):
        raise CommandError(t.error.option_duplicated)

    embed.add_field(name=t.poll.option, value="\n".join([str(opt) for opt in options]), inline=False)

    poll_type: PollType = PollType.STANDARD
    if team_poll:
        missing = list(await get_staff(ctx.guild, ["team"]))
        missing.sort(key=lambda m: str(m).lower())
        *teamlers, last = (x.mention for x in missing)
        teamlers: list[str]
        field = (tg.status, t.error.teamlers_missing(teamlers=", ".join(teamlers), last=last, cnt=len(teamlers) + 1))

        poll_type = poll_type.TEAM
        embed.add_field(name=field[0], value=field[1], inline=False)

    msg = await ctx.send(embed=embed)
    select_obj = MySelect(
        custom_id=str(msg.id),
        placeholder=place,
        max_values=max_value,
        options=[
            SelectOption(label=t.poll.select.label(index + 1), emoji=option.emoji, description=option.option)
            for index, option in enumerate(options)
        ],
    )
    view_msg = await ctx.send(view=create_select_view(select_obj=select_obj))
    thread = await msg.create_thread(name=question)

    parsed_options: list[tuple[str, str, str]] = [
        (obj.emoji, obj.option, t.poll.select.label(ix)) for ix, obj in enumerate(options, start=1)
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

    await Poll.create(
        message_id=msg.id,
        message_url=msg.jump_url,
        guild_id=ctx.guild.id,
        channel=msg.channel.id,
        owner=ctx.author.id,
        title=question,
        end=deadline,
        anonymous=anonymous,
        options=parsed_options,
        poll_type=poll_type,
        interaction=view_msg.id,
        max_choices=max_choices,
        thread=thread.id,
        weights=weights,
    )


async def edit_poll_embed(embed: Embed, poll: Poll, missing: list[Member] = None) -> Embed:
    """edits the poll embed, updating the votes from team-members"""
    for index, field in enumerate(embed.fields):
        if field.name == tg.status:
            if missing:
                missing.sort(key=lambda m: str(m).lower())
                *teamlers, last = (x.mention for x in missing)
                teamlers: list[str]
                text = t.error.teamlers_missing(teamlers=", ".join(teamlers), last=last, cnt=len(teamlers) + 1)
            else:
                text = t.poll.all_voted

            embed.set_field_at(index, name=field.name, value=text)
            break
    embed.set_footer(text=t.poll.footer.default(calc_end_time(poll.end_time).strftime("%Y-%m-%d %H:%M")))

    return embed


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


async def notify_missing_staff(bot: Bot, poll: Poll):
    thread = bot.get_channel(poll.thread_id)
    if not thread:
        return
    try:
        teamlers: set[Member] = await get_staff(bot.get_guild(poll.guild_id), ["team"])
    except CommandError:
        await thread.send(embed=Embed(title=t.error.no_teamlers, color=Colors.error))
        return

    ignored_ids: list[int] = [i.id for i in await IgnoredUser.get(poll.guild_id)]
    user_ids: set[int] = set()
    for option in poll.options:
        for vote in option.votes:
            if vote.user_id not in ignored_ids:
                user_ids.add(vote.user_id)

    missing: list[Member] | None = [teamler for teamler in teamlers if teamler.id not in user_ids]
    missing.sort(key=lambda m: str(m).lower())

    desc = " ".join(f"<@{user}>" for user in missing)
    await thread.send(t.error.team_poll_missing(desc))


async def handle_deleted_messages(bot, message_id: int):
    """if a message containing a poll gets deleted, this function deletes the interaction message (both direction)"""
    deleted_embed: Poll | None = await db.get(Poll, message_id=message_id)
    deleted_interaction: Poll | None = await db.get(Poll, interaction_message_id=message_id)

    if not deleted_embed and not deleted_interaction:
        return

    poll = deleted_embed or deleted_interaction
    if poll.status == PollStatus.CLOSED or poll.poll_type == PollType.TEAM:
        return
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

    # removes all invalid polls
    if not poll.end_time and not poll.poll_type == PollType.TEAM:
        await poll.remove()
        return False

    # paused or closed polls
    if poll.status != PollStatus.ACTIVE:
        return False

    # poll still running
    if poll.last_time_state_change + relativedelta(seconds=poll.end_time) < utcnow():
        return False

    return True


async def close_poll(bot, poll: Poll):
    """deletes the interaction message and edits the footer of the poll embed"""
    try:
        channel = await bot.fetch_channel(poll.channel_id)
        thread = await bot.fetch_channel(poll.thread_id)
        embed_message = await channel.fetch_message(poll.message_id)
        interaction_message = await channel.fetch_message(poll.interaction_message_id)
    except NotFound:
        poll.status = PollStatus.CLOSED
        return

    embed = embed_message.embeds[0]
    embed.colour = Colors.purple
    embed.set_footer(text=t.poll.footer.closed)

    await embed_message.edit(embed=embed)
    await embed_message.unpin()

    try:
        res = show_results(poll, True)
        await thread.send(embed=res[0], file=res[1])
    except CommandError:
        pass
    await thread.archive(True)

    poll.status = PollStatus.CLOSED
    poll.last_time_state_change = utcnow()
    await db.commit()
    await interaction_message.delete()


async def get_poll_list_embed(ctx: Context, poll_type: PollType, state: PollStatus) -> Embed:
    description = ""
    polls: list[Poll] = await db.all(filter_by(Poll, status=state, guild_id=ctx.guild.id, poll_type=poll_type))

    for poll in polls:
        time = (
            f'until {format_dt(calc_end_time(poll.end_time), style="R")}'
            if poll.status == PollStatus.ACTIVE
            else poll.status
        )
        description += t.polls.row(poll.title, poll.message_url, poll.owner_id, time)

    if polls and description:
        embed: Embed = Embed(
            title=t.polls.title(state.value, poll_type.value), description=description, color=Colors.Polls
        )
    else:
        embed: Embed = Embed(title=t.error.no_polls(state.value, poll_type.value), color=Colors.error)

    return embed


async def status_change(bot: Bot, poll: Poll):
    try:
        channel = await bot.fetch_channel(poll.channel_id)
        embed_message = await channel.fetch_message(poll.message_id)
    except NotFound:
        if poll.status == PollStatus.ACTIVE:
            poll.status = PollStatus.PAUSED
        else:
            poll.status = PollStatus.ACTIVE
        return

    embed = embed_message.embeds[0]
    if poll.status == PollStatus.ACTIVE:
        poll.status = PollStatus.PAUSED
        embed.set_footer(text=t.poll.footer.paused)
        embed.colour = Colors.grey
        await embed_message.unpin()
    else:
        poll.status = PollStatus.ACTIVE
        embed.set_footer(text=t.poll.footer.default(calc_end_time(poll.end_time).strftime("%Y-%m-%d %H:%M")))
        embed.colour = Colors.Polls
        await embed_message.pin()

    poll.last_time_state_change = utcnow()
    await embed_message.edit(embed=embed)


def show_results(
    poll: Poll, show_all: bool = False
) -> tuple[Embed, File]:  # style is good for now, if you don't like it, change it by yourself
    data: list[tuple[str, float | int]] = [
        (option.text, weight) for option in poll.options if (weight := sum(vote.vote_weight for vote in option.votes))
    ]
    if not data:
        raise CommandError(t.error.no_votes)
    data_tuple: list[tuple[str, float]] = [(text[:10], num) for text, num in data if num]
    data_tuple.sort(key=lambda x: x[1])
    if not show_all:
        data_tuple = data_tuple[:10]
    data_np = np.array([value for _, value in data_tuple])
    cc = plt.cycler("color", plt.cm.rainbow(np.linspace(1, 0, len(data_np))))
    explode = [len(data_tuple) / 50 for _ in data_tuple]
    with plt.style.context({"axes.prop_cycle": cc}):
        fig1, ax1 = plt.subplots()
        ax1.axis("equal")
        pie, *_ = ax1.pie(data_np, autopct="%1.1f%%", startangle=90, pctdistance=0.8, explode=explode)
        plt.setp(pie, width=0.5)
        plt.legend(
            bbox_to_anchor=(1.1, 1.1), loc="upper right", borderaxespad=0, labels=[f"{i}" for i, _ in data_tuple]
        )
        plt.title(poll.title, fontdict={"fontsize": 20, "color": "#FFFFFF"}, pad=50)
        buf = BytesIO()
        fig1.set_size_inches(11.1, 8)
        fig1.savefig(buf, format="png", transparent=True, dpi=400)
        plt.clf()
        buf.seek(0)

    file = File(filename="poll_result.png", fp=buf)

    embed = Embed(title=t.poll.results, color=Colors.Polls)
    embed.set_image(url="attachment://poll_result.png")

    return embed, file


class MySelect(Select):
    """adds a method for handling interactions with the select menu"""

    @db_wrapper
    async def callback(self, interaction):  # TODO: needs to check for weights and allowed roles
        user = interaction.user
        selected_options: list = self.values
        message: Message = await interaction.channel.fetch_message(interaction.custom_id)
        embed: Embed = message.embeds[0] if message.embeds else None
        poll: Poll = await db.get(Poll, (Poll.options, Option.votes), message_id=message.id)

        if not poll or not embed:
            return

        if not poll.status == PollStatus.ACTIVE:
            await interaction.response.send_message(
                content=t.error.poll_cant_be_used(poll.status.value), ephemeral=True
            )
            return

        new_options: list[Option] = [option for option in poll.options if option.option in selected_options]

        opt: Option
        for opt in poll.options:
            for vote in opt.votes:
                if vote.user_id == user.id:
                    await vote.remove()
                    opt.votes.remove(vote)

        ev_pover = 1
        if poll.fair:
            user_weight: float = ev_pover
        else:
            highest_role = await RoleWeight.get_highest(user.roles) or 0
            user_weight: float = ev_pover if highest_role < ev_pover else highest_role

        for option in new_options:
            option.votes.append(
                await PollVote.create(option_id=option.id, user_id=user.id, poll_id=poll.id, vote_weight=user_weight)
            )

        if poll.poll_type == PollType.TEAM:
            try:
                teamlers: set[Member] = await get_staff(interaction.guild, ["team"])
            except CommandError:
                await interaction.response.send_message(content=t.error.no_teamlers, ephemeral=True)
                return
            if user not in teamlers:
                await interaction.response.send_message(content=t.error.teampoll_forbidden, ephemeral=True)
                return

            user_ids: set[int] = set()
            for option in poll.options:
                for vote in option.votes:
                    user_ids.add(vote.user_id)

            missing: list[Member] | None = [teamler for teamler in teamlers if teamler.id not in user_ids]
            embed = await edit_poll_embed(embed, poll, missing)

        await message.edit(embed=embed)
        await interaction.response.send_message(content=t.poll.voted, ephemeral=True)


class PollsCog(Cog, name="Polls"):
    CONTRIBUTORS = [
        Contributor.MaxiHuHe04,
        Contributor.Defelo,
        Contributor.TNT2k,
        Contributor.wolflu,
        Contributor.Infinity,
    ]

    def __init__(self, team_roles: list[str]):
        self.team_roles: list[str] = team_roles

    async def on_ready(self):
        await sync_redis()
        polls: list[Poll] = await db.all(filter_by(Poll, (Poll.options, Option.votes), status=PollStatus.ACTIVE))
        for poll in polls:
            if not await check_poll_time(poll):
                continue

            select_obj = MySelect(
                custom_id=str(poll.message_id),
                placeholder=t.poll.select.placeholder(cnt=poll.max_choices),
                max_values=poll.max_choices,
                options=[
                    SelectOption(
                        label=t.poll.select.label(option.field_position + 1),
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
        polls: list[Poll] = await db.all(filter_by(Poll, status=PollStatus.ACTIVE))

        for poll in polls:
            if not await check_poll_time(poll) and poll.poll_type == PollType.STANDARD:
                await close_poll(self.bot, poll)
            elif not await check_poll_time(poll) and poll.poll_type == PollType.TEAM:
                poll.end_time = poll.end_time + relativedelta(days=1).seconds
                await notify_missing_staff(self.bot, poll)

    @commands.group(name="poll", aliases=["vote"])
    @guild_only()
    @docs(t.commands.poll.poll)
    async def poll(self, ctx: Context):
        if not ctx.subcommand_passed:
            raise UserInputError

    @poll.command(name="list", aliases=["l"])
    @guild_only()
    @docs(t.commands.poll.list)
    async def poll_list(self, ctx: Context, active: bool = True):
        embed = await get_poll_list_embed(ctx, PollType.STANDARD, PollStatus.ACTIVE if active else PollStatus.PAUSED)

        await send_long_embed(ctx, embed=embed, paginate=True)

    @poll.command(name="close", aliases=["c"])
    @optional_permissions(PollsPermission.manage)
    @docs(t.commands.poll.close)
    async def close(self, ctx: Context, message: Message):
        poll: Poll = await db.get(Poll, (Poll.options, Option.votes), message_id=message.id)
        if not poll:
            raise CommandError(t.error.not_poll)
        if poll.status == PollStatus.CLOSED:
            raise CommandError(t.error.poll_closed)
        if poll.owner_id != ctx.author.id:
            raise CommandError(tg.not_allowed)

        await close_poll(self.bot, poll)
        await ctx.message.add_reaction(name_to_emoji["white_check_mark"])

    @poll.command(name="delete", aliases=["del"])
    @optional_permissions(PollsPermission.manage)
    @docs(t.commands.poll.delete)
    async def delete(self, ctx: Context, message: Message):
        poll: Poll = await db.get(Poll, message_id=message.id)
        if not poll:
            raise CommandError(t.error.not_poll)
        if not poll.owner_id == ctx.author.id and not PollsPermission.manage.check(ctx):
            raise CommandError(tg.not_allowed)

        if not await Confirmation().run(ctx, t.texts.delete.confirm):
            return

        await message.delete()
        await poll.remove()
        try:
            interaction_message: Message = await ctx.channel.fetch_message(poll.interaction_message_id)
            await interaction_message.delete()
        except NotFound:
            pass

        await add_reactions(ctx.message, "white_check_mark")

    @poll.command(name="voted", aliases=["v"])
    @optional_permissions(PollsPermission.manage)
    @docs(t.commands.poll.voted)
    async def voted(self, ctx: Context, message: Message):
        poll: Poll = await db.get(Poll, (Poll.options, Option.votes), message_id=message.id)
        author = ctx.author
        if not poll:
            raise CommandError(t.error.not_poll)
        if poll.anonymous and not poll.owner_id == author.id:
            raise CommandError(tg.not_allowed)

        users = {}
        for option in poll.options:
            for vote in option.votes:
                if not users.get(str(vote.user_id)):
                    users[str(vote.user_id)] = [option.field_position + 1]
                else:
                    users[str(vote.user_id)].append(option.field_position + 1)

        description = ""
        for key, value in users.items():
            description += t.texts.voted.row(key, value)
        embed = Embed(title=t.texts.voted.title, description=description, color=Colors.Polls)

        await send_long_embed(ctx, embed=embed, repeat_title=True, paginate=True)

    @poll.command(name="results", aliases=["res"])
    @optional_permissions(PollsPermission.manage)
    @docs(t.commands.poll.result)
    async def result(self, ctx: Context, message: Message, show_all: bool = False):
        poll: Poll = await db.get(Poll, (Poll.options, Poll.roles, Option.votes), message_id=message.id)
        if poll.status == PollStatus.ACTIVE and not poll.owner_id == ctx.author.id:
            raise CommandError(t.error.still_active)
        if not poll:
            raise CommandError(t.error.not_poll)

        embed, file = show_results(poll, show_all)

        await send_long_embed(ctx, embed=embed, file=file)

    @poll.command(name="activate", aliases=["a"])
    @optional_permissions(PollsPermission.manage)
    @docs(t.commands.poll.activate)
    async def activate(self, ctx: Context, message: Message):
        poll: Poll = await db.get(Poll, (Poll.options, Option.votes), message_id=message.id)
        if not poll:
            raise CommandError(t.error.not_poll)
        if not ctx.author.id == poll.owner_id:
            raise CommandError(tg.not_allowed)

        if poll.status == PollStatus.ACTIVE:
            raise CommandError(t.error.poll_status_not_changed(poll.status.value))

        await status_change(self.bot, poll)
        await send_long_embed(ctx, embed=Embed(title=t.poll.status_changed(poll.status.value)))

    @poll.command(name="pause", aliases=["p", "deactivate", "disable"])
    @optional_permissions(PollsPermission.manage)
    @docs(t.commands.poll.paused)
    async def pause(self, ctx: Context, message: Message):
        poll: Poll = await db.get(Poll, (Poll.options, Option.votes), message_id=message.id)
        if not poll:
            raise CommandError(t.error.not_poll)
        if not ctx.author.id == poll.owner_id:
            raise CommandError(tg.not_allowed)

        if poll.status == PollStatus.PAUSED:
            raise CommandError(t.error.poll_status_not_changed(poll.status.value))

        await status_change(self.bot, poll)
        await send_long_embed(ctx, embed=Embed(title=t.poll.status_changed(poll.status.value)))

    @poll.group(name="settings", aliases=["s"])
    @PollsPermission.read.check
    @docs(t.commands.poll.settings.settings)
    async def settings(self, ctx: Context):
        if ctx.subcommand_passed is not None:
            if ctx.invoked_subcommand is None:
                raise UserInputError
            return

        embed = Embed(title=t.poll_config.title, color=Colors.Polls)
        time: int = await PdS.duration.get()
        max_time: int = await PdS.max_duration.get()
        embed.add_field(
            name=t.poll_config.duration.name,
            value=t.poll_config.duration.time(cnt=time) if not time <= 0 else t.poll_config.duration.time(cnt=max_time),
        )
        embed.add_field(name=t.poll_config.max_duration.name, value=t.poll_config.max_duration.time(cnt=max_time))

        await send_long_embed(ctx, embed)

    @settings.command(name="duration", aliases=["d"])
    @PollsPermission.write.check
    @docs(t.commands.poll.settings.duration)
    async def duration(self, ctx: Context, hours: int | None = None):
        if not hours:
            hours = 0
            msg: str = t.texts.duration.reset()
        else:
            msg: str = t.texts.duration.set(cnt=hours)

        await PdS.duration.set(hours)
        await add_reactions(ctx.message, "white_check_mark")
        await send_to_changelog(ctx.guild, msg)

    @settings.command(name="max_duration", aliases=["md"])
    @PollsPermission.write.check
    @docs(t.commands.poll.settings.max_duration)
    async def max_duration(self, ctx: Context, days: int | None = None):
        days = days or 7
        msg: str = t.texts.max_duration.set(cnt=days)

        await PdS.max_duration.set(days)
        await add_reactions(ctx.message, "white_check_mark")
        await send_to_changelog(ctx.guild, msg)

    @poll.group(name="team", aliases=["t"])
    @PollsPermission.team_poll.check
    @docs(t.commands.poll.team.team)
    async def team(self, ctx: Context):
        if not ctx.subcommand_passed:
            raise UserInputError

    @team.group(name="settings", aliases=["s"])  # TODO: function for team-poll settings
    @PollsPermission.read.check
    @docs(t.commands.poll.team.settings.settings)
    async def tp_settings(self, ctx: Context):
        if ctx.subcommand_passed is not None:
            if ctx.invoked_subcommand is None:
                raise UserInputError
            return

        ignored: list[IgnoredUser] = await IgnoredUser.get(ctx.guild.id)
        ignore = "None" if not ignored else " ".join(f"<@{i.member_id}>" for i in ignored)

        embed = Embed(title=t.team_settings.title, color=Colors.Polls)
        embed.add_field(name=t.team_settings.ignore.name, value=ignore)

        await send_long_embed(ctx, embed=embed)

    @tp_settings.command(name="ignore", aliases=["i"])
    @PollsPermission.write.check
    @docs(t.commands.poll.team.settings.ignore)
    async def ignore(self, ctx: Context, member: Member):
        user: IgnoredUser = await db.get(IgnoredUser, member_id=member.id, guild_id=ctx.guild.id)

        if user:
            await user.remove()
            desc = t.texts.ignore.removed(member.id)
        else:
            await IgnoredUser.create(ctx.guild.id, member.id)
            desc = t.texts.ignore.added(member.id)

        await send_to_changelog(ctx.guild, desc)
        await add_reactions(ctx.message, "white_check_mark")

    @team.command(name="conclude", aliases=["c"])
    @PollsPermission.manage.check
    @docs(t.commands.poll.team.conclude)
    async def conclude(self, ctx: Context, message: Message, accepted: bool):
        poll: Poll = await db.get(Poll, (Poll.options, Poll.roles, Option.votes), message_id=message.id)
        if not poll or poll.poll_type != PollType.TEAM or poll.status == PollStatus.CLOSED or not message.embeds:
            raise CommandError(t.error.not_poll)

        embed: Embed = message.embeds[0] if message.embeds else None
        thread = self.bot.get_channel(poll.thread_id)

        for index, field in enumerate(embed.fields):
            if field.name == tg.status:
                if accepted:
                    embed.colour = Colors.green
                    text = t.texts.conclude.accepted
                else:
                    embed.colour = Colors.red
                    text = t.texts.conclude.rejected

                embed.set_field_at(index, name=field.name, value=text(ctx.author.mention))
        await message.edit(embed=embed)

        res = show_results(poll, True)
        if thread:
            await thread.send(embed=res[0], file=res[1])
            await thread.archive(True)
        else:
            await ctx.send(embed=res[0], file=res[1])

        await close_poll(self.bot, poll)

    @team.command(name="new", aliases=["n"])  # TODO: new team-polls
    @docs(t.commands.poll.team.new)
    async def team_new(self, ctx: Context, *, args: str):
        pass

    @team.command(name="list", aliases=["l"])
    @docs(t.commands.poll.list)
    async def list(self, ctx: Context):
        embed = await get_poll_list_embed(ctx, PollType.TEAM, PollStatus.ACTIVE)

        await send_long_embed(ctx, embed=embed, paginate=True)

    @poll.command(name="quick", usage=t.usage.poll, aliases=["q"])
    @docs(t.commands.poll.quick)
    async def quick(self, ctx: Context, *, args: str):
        await send_poll(
            ctx=ctx,
            title=t.poll.standard,
            poll_args=args,
            max_choices=MAX_OPTIONS,
            deadline=await PdS.duration.get() * 60 * 60 or await PdS.max_duration.get() * 60 * 60 * 24,
        )

        await ctx.message.delete()

    @poll.command(name="new", usage=t.usage.poll)
    @docs(t.commands.poll.new)
    async def new(self, ctx: Context, *, options: str):
        wizard = await ctx.send(embed=build_wizard())
        mess: Message = await self.bot.wait_for("message", check=lambda m: m.author == ctx.author, timeout=120.0)
        args = mess.content

        if args.lower() == t.wizard.skip.message:
            await wizard.edit(embed=build_wizard(True), delete_after=5.0)
        else:
            await wizard.delete(delay=5.0)
        await mess.delete()

        parser = await get_parser()
        parsed, _ = parser.parse_known_args(shlex.split(args))

        max_deadline = await PdS.max_duration.get() * 24
        deadline: int = parsed.deadline
        if deadline == 0:
            deadline = await PdS.duration.get()
        deadline = max_deadline if not deadline or deadline > max_deadline else deadline
        deadline *= 3600

        roles = await RoleParser(ctx).parse_roles(parsed.roles)
        weights = await RoleParser(ctx).parse_weights(parsed.weights)

        await send_poll(
            ctx=ctx,
            title=t.poll.standard,
            poll_args=options,
            max_choices=parsed.choices,
            deadline=deadline,
            anonymous=parsed.anonymous,
            allowed_roles=roles,
            weights=weights,
        )
        await ctx.message.delete()

    @commands.command(aliases=["yn"])
    @guild_only()
    @docs(t.commands.yes_no)
    async def yesno(self, ctx: Context, message: Message | None = None, text: str | None = None):
        if message is None or message.guild is None or text:
            message = ctx.message

        if message.author != ctx.author and not await is_teamler(ctx.author):
            raise CommandError(t.error.foreign_message)

        try:
            await message.add_reaction(name_to_emoji["thumbsup"])
            await message.add_reaction(name_to_emoji["thumbsdown"])
        except Forbidden:
            raise CommandError(t.error.could_not_add_reactions(message.channel.mention))

        if message != ctx.message:
            try:
                await ctx.message.add_reaction(name_to_emoji["white_check_mark"])
            except Forbidden:
                pass

    @commands.command(name="team_yes_no", aliases=["tyn"])
    @PollsPermission.team_poll.check
    @guild_only()
    @docs(t.commands.team_yes_no)
    async def team_yesno(self, ctx: Context, *, text: str):
        await send_poll(
            ctx=ctx,
            title=t.poll.team_poll,
            max_choices=1,
            poll_args=t.yes_no.option_string(text),
            team_poll=True,
            deadline=await PtS.duration.get() * 60 * 60 * 24,
        )
