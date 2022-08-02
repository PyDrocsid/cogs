from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional, Union

from discord import Role
from discord.utils import utcnow
from sqlalchemy import BigInteger, Boolean, Column, Enum, Float, ForeignKey, Text
from sqlalchemy.orm import relationship

from PyDrocsid.database import Base, UTCDateTime, db, filter_by


class PollType(enum.Enum):
    TEAM = "team"
    STANDARD = "standard"


class PollStatus(enum.Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    CLOSED = "closed"


class Poll(Base):
    __tablename__ = "poll"

    id: Union[Column, int] = Column(BigInteger, primary_key=True, autoincrement=True, unique=True)

    options: list[Option] = relationship("Option", back_populates="poll", cascade="all, delete")
    roles: list[RoleWeight] = relationship("RoleWeight", back_populates="poll", cascade="all, delete")

    message_id: Union[Column, int] = Column(BigInteger, unique=True)
    message_url: Union[Column, str] = Column(Text(256))
    guild_id: Union[Column, int] = Column(BigInteger)
    interaction_message_id: Union[Column, int] = Column(BigInteger, unique=True)
    thread_id: Union[Column, int] = Column(BigInteger, unique=True)
    channel_id: Union[Column, int] = Column(BigInteger)
    owner_id: Union[Column, int] = Column(BigInteger)
    timestamp: Union[Column, datetime] = Column(UTCDateTime)
    title: Union[Column, str] = Column(Text(256))
    poll_type: Union[Column, PollType] = Column(Enum(PollType))
    end_time: Union[Column, int] = Column(BigInteger)
    anonymous: Union[Column, bool] = Column(Boolean)
    fair: Union[Column, bool] = Column(Boolean)
    status: Union[Column, PollStatus] = Column(Enum(PollStatus))
    last_time_state_change: Union[Column, datetime] = Column(UTCDateTime)
    max_choices: Union[Column, int] = Column(BigInteger)
    limited: Union[Column, bool] = Column(Boolean)

    @staticmethod
    async def create(
        message_id: int,
        message_url: str,
        guild_id: int,
        channel: int,
        owner: int,
        title: str,
        options: list[tuple[str, str, str]],
        end: Optional[int],
        anonymous: bool,
        poll_type: enum.Enum,
        interaction: int,
        thread: int,
        max_choices: int,
        allowed_roles: list[int] | None = None,
        weights: list[tuple[int, float]] | None = None,
    ) -> Poll:
        row = Poll(
            message_id=message_id,
            message_url=message_url,
            guild_id=guild_id,
            channel_id=channel,
            owner_id=owner,
            timestamp=utcnow(),
            title=title,
            poll_type=poll_type,
            end_time=end,
            anonymous=anonymous,
            interaction_message_id=interaction,
            thread_id=thread,
            status=PollStatus.ACTIVE,
            last_time_state_change=utcnow(),
            max_choices=max_choices,
            limited=bool(allowed_roles),
            fair=not bool(weights),
        )
        for position, poll_option in enumerate(options):
            row.options.append(
                await Option.create(
                    poll=message_id,
                    emote=poll_option[0],
                    text=poll_option[1],
                    option=poll_option[2],
                    field_position=position,
                )
            )

        if allowed_roles:
            _allowed_roles = allowed_roles
            for role_id, weight in weights or []:
                if role_id not in allowed_roles:
                    continue
                row.roles.append(await RoleWeight.create(message_id, role_id, weight))
                _allowed_roles.remove(role_id)

            for role_id in _allowed_roles:
                row.roles.append(await RoleWeight.create(message_id, role_id, 1))
        else:
            for role_id, weight in weights or []:
                row.roles.append(await RoleWeight.create(message_id, role_id, weight))

        await db.add(row)
        return row

    async def remove(self):
        await db.delete(self)

    async def get_highest_weight(self, user_roles: list[Role]) -> float | None:
        role_ids = [role.id for role in user_roles]
        print(self.roles)
        weight: float = 1
        for role in self.roles or []:
            if self.limited and role.role_id not in role_ids:
                continue

            _weight = role.weight
            if _weight and weight < (_weight := float(_weight)):
                weight = _weight

        return weight if weight != 1 else None


class Option(Base):
    __tablename__ = "poll_option"

    id: Union[Column, int] = Column(BigInteger, primary_key=True, autoincrement=True, unique=True)
    poll_id: Union[Column, int] = Column(BigInteger, ForeignKey("poll.message_id"))
    votes: list[PollVote] = relationship("PollVote", back_populates="option", cascade="all, delete")
    poll: Poll = relationship("Poll", back_populates="options")
    emote: Union[Column, str] = Column(Text(32))
    option: Union[Column, str] = Column(Text(20))
    text: Union[Column, str] = Column(Text(1024))
    field_position: Union[Column, int] = Column(BigInteger)

    @staticmethod
    async def create(poll: int, emote: str, option: str, text: str, field_position: int) -> Option:
        options = Option(poll_id=poll, emote=emote, option=option, text=text, field_position=field_position)
        await db.add(options)
        return options


class PollVote(Base):
    __tablename__ = "voted_user"

    id: Union[Column, int] = Column(BigInteger, primary_key=True, autoincrement=True, unique=True)
    user_id: Union[Column, int] = Column(BigInteger)
    option_id: Union[Column, int] = Column(BigInteger, ForeignKey("poll_option.id"))
    option: Option = relationship("Option", back_populates="votes")
    vote_weight: Union[Column, float] = Column(Float)
    poll_id: Union[Column, int] = Column(BigInteger)

    @staticmethod
    async def create(user_id: int, option_id: int, vote_weight: float, poll_id: int):
        row = PollVote(user_id=user_id, option_id=option_id, vote_weight=vote_weight, poll_id=poll_id)
        await db.add(row)
        return row

    async def remove(self):
        await db.delete(self)


class RoleWeight(Base):
    __tablename__ = "role_weight"

    id: Union[Column, int] = Column(BigInteger, primary_key=True, autoincrement=True, unique=True)
    role_id: Union[Column, int] = Column(BigInteger)
    weight: Union[Column, float] = Column(Float)
    poll: Poll = relationship("Poll", back_populates="roles")
    poll_id: Union[Column, int] = Column(BigInteger, ForeignKey("poll.message_id"))

    @staticmethod
    async def create(poll_id: int, role: int, weight: float) -> RoleWeight:
        role_weight = RoleWeight(poll_id=poll_id, role_id=role, weight=weight)
        await db.add(role_weight)
        return role_weight

    async def remove(self) -> None:
        await db.delete(self)

    @staticmethod
    async def get(guild: int, poll_type: PollType) -> list[RoleWeight]:
        return await db.all(filter_by(RoleWeight, guild_id=guild, poll_type=poll_type))


class IgnoredUser(Base):
    __tablename__ = "ignored_by_poll_ping"

    id: Union[Column, int] = Column(BigInteger, primary_key=True, autoincrement=True, unique=True)
    guild_id: Union[Column, int] = Column(BigInteger)
    member_id: Union[Column, int] = Column(BigInteger, unique=True)
    timestamp: Union[Column, datetime] = Column(UTCDateTime)

    @staticmethod
    async def create(guild_id: int, member_id: int):
        ignored_user = IgnoredUser(guild_id=guild_id, member_id=member_id)
        await db.add(ignored_user)
        return ignored_user

    async def remove(self) -> None:
        await db.delete(self)

    @staticmethod
    async def get(guild_id: int) -> list[IgnoredUser]:
        return await db.all(filter_by(IgnoredUser, guild_id=guild_id))
