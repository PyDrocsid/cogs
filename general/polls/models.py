from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional, Union

from discord import Role
from discord.utils import utcnow
from sqlalchemy import BigInteger, Boolean, Column, Enum, Float, ForeignKey, Text
from sqlalchemy.orm import relationship

from PyDrocsid.database import Base, UTCDateTime, db, filter_by, select
from PyDrocsid.environment import CACHE_TTL
from PyDrocsid.redis import redis


class PollType(enum.Enum):
    TEAM = "team"
    STANDARD = "standard"


class PollStatus(enum.Enum):
    ACTIVE = 0
    PAUSED = 1
    CLOSED = 2


async def sync_redis(role_id: int = None) -> list[dict[str, int | float]]:
    out = []

    async with redis.pipeline() as pipe:
        if role_id:
            await pipe.delete(f"poll_role_weight={role_id}")
        weights: RoleWeight
        async for weights in await db.stream(select(RoleWeight)):
            await pipe.delete(key := f"poll_role_weight={role_id or weights.role_id}")
            save = {"role": int(weights.role_id), "weight": float(weights.weight)}
            out.append(save)
            await pipe.setex(key, CACHE_TTL, str(weights.weight))

        await pipe.execute()

    return out


class Poll(Base):
    __tablename__ = "poll"

    id: Union[Column, int] = Column(BigInteger, primary_key=True, autoincrement=True, unique=True)

    options: list[Option] = relationship("Option", back_populates="poll", cascade="all, delete")

    message_id: Union[Column, int] = Column(BigInteger, unique=True)
    message_url: Union[Column, str] = Column(Text(256))
    guild_id: Union[Column, int] = Column(BigInteger)
    interaction_message_id: Union[Column, int] = Column(BigInteger, unique=True)
    channel_id: Union[Column, int] = Column(BigInteger)
    owner_id: Union[Column, int] = Column(BigInteger)
    timestamp: Union[Column, datetime] = Column(UTCDateTime)
    title: Union[Column, str] = Column(Text(256))
    poll_type: Union[Column, PollType] = Column(Enum(PollType))
    end_time: Union[Column, int] = Column(BigInteger)
    anonymous: Union[Column, bool] = Column(Boolean)
    can_delete: Union[Column, bool] = Column(Boolean)
    fair: Union[Column, bool] = Column(Boolean)
    status: Union[Column, PollStatus] = Column(Enum(PollStatus))
    max_choices: Union[Column, int] = Column(BigInteger)

    @staticmethod
    async def create(
        message_id: int,
        message_url: str,
        guild_id: int,
        channel: int,
        owner: int,
        title: str,
        options: list[tuple[str, str]],
        end: Optional[int],
        anonymous: bool,
        can_delete: bool,
        poll_type: enum.Enum,
        interaction: int,
        fair: bool,
        max_choices: int,
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
            can_delete=can_delete,
            interaction_message_id=interaction,
            fair=fair,
            status=0,
            max_choices=max_choices,
        )
        for position, poll_option in enumerate(options):
            row.options.append(
                await Option.create(
                    poll=message_id, emote=poll_option[0], option_text=poll_option[1], field_position=position
                )
            )

        await db.add(row)
        return row

    async def remove(self):
        await db.delete(self)


class Option(Base):
    __tablename__ = "poll_option"

    id: Union[Column, int] = Column(BigInteger, primary_key=True, autoincrement=True, unique=True)
    poll_id: Union[Column, int] = Column(BigInteger, ForeignKey("poll.message_id"))
    votes: list[PollVote] = relationship("PollVote", back_populates="option", cascade="all, delete")
    poll: Poll = relationship("Poll", back_populates="options")
    emote: Union[Column, str] = Column(Text(30))
    option: Union[Column, str] = Column(Text(250))
    field_position: Union[Column, int] = Column(BigInteger)

    @staticmethod
    async def create(poll: int, emote: str, option_text: str, field_position: int) -> Option:
        options = Option(poll_id=poll, emote=emote, option=option_text, field_position=field_position)
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
    guild_id: Union[Column, int] = Column(BigInteger)
    role_id: Union[Column, int] = Column(BigInteger, unique=True)
    weight: Union[Column, float] = Column(Float)
    timestamp: Union[Column, datetime] = Column(UTCDateTime)

    @staticmethod
    async def create(guild_id: int, role: int, weight: float) -> RoleWeight:
        role_weight = RoleWeight(guild_id=guild_id, role_id=role, weight=weight, timestamp=utcnow())
        await db.add(role_weight)
        await sync_redis()
        return role_weight

    async def remove(self) -> None:
        await db.delete(self)
        await sync_redis(self.role_id)

    @staticmethod
    async def get(guild: int) -> list[RoleWeight]:
        return await db.all(filter_by(RoleWeight, guild_id=guild))

    @staticmethod
    async def get_highest(user_roles: list[Role]) -> float:
        weight: float = 0.0
        for role in user_roles:
            _weight = await redis.get(f"poll_role_weight={role.id}")

            if _weight and weight < (_weight := float(_weight)):
                weight = _weight

        return weight
