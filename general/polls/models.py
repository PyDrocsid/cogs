from __future__ import annotations

from datetime import datetime
from typing import Union

from discord.utils import utcnow
from sqlalchemy import BigInteger, Boolean, Column, Float, ForeignKey, Text
from sqlalchemy.orm import relationship

from PyDrocsid.database import Base, UTCDateTime, db, select


class Poll(Base):
    __tablename__ = "poll"

    id: Union[Column, int] = Column(BigInteger, primary_key=True, autoincrement=True, unique=True)

    options: list[Option] = relationship("Option", back_populates="poll", cascade="all, delete")

    message_id: Union[Column, int] = Column(BigInteger, unique=True)
    poll_channel: Union[Column, int] = Column(BigInteger)
    owner_id: Union[Column, int] = Column(BigInteger)
    timestamp: Union[Column, datetime] = Column(UTCDateTime)
    title: Union[Column, str] = Column(Text(256))
    poll_type: Union[Column, str] = Column(Text(50))
    end_time: Union[Column, datetime] = Column(UTCDateTime)
    anonymous: Union[Column, bool] = Column(Boolean)
    votes_amount: Union[Column, int] = Column(BigInteger)
    poll_open: Union[Column, bool] = Column(Boolean)
    can_delete: Union[Column, bool] = Column(Boolean)
    keep: Union[Column, bool] = Column(Boolean)


class Voted(Base):
    __tablename__ = "voted_user"

    id: Union[Column, int] = Column(BigInteger, primary_key=True, autoincrement=True, unique=True)
    user_id: Union[Column, int] = Column(BigInteger)
    option_id: Union[Column, int] = Column(BigInteger, ForeignKey("poll_option.id"))
    option: Option = relationship("Option", back_populates="votes", cascade="all, delete")
    vote_weight: Union[Column, float] = Column(Float)


class Option(Base):
    __tablename__ = "poll_option"

    id: Union[Column, int] = Column(BigInteger, primary_key=True, autoincrement=True, unique=True)
    poll_id: Union[Column, int] = Column(BigInteger, ForeignKey("poll.id"))
    votes: list[Voted] = relationship("Voted", back_populates="option")
    poll: Poll = relationship("Poll", back_populates="options")
    emote: Union[Column, str] = Column(Text(30))
    option: Union[Column, str] = Column(Text(150))

    @staticmethod
    async def create(poll: int, emote: str, option_text: str) -> Option:
        options = Option(poll_id=poll, emote=emote, option=option_text)
        await db.add(options)

        return options


class RoleWeight(Base):
    __tablename__ = "role_weight"

    id: Union[Column, int] = Column(BigInteger, primary_key=True, autoincrement=True, unique=True)
    role_id: Union[Column, int] = Column(BigInteger, unique=True)
    weight: Union[Column, float] = Column(Float)
    timestamp: Union[Column, datetime] = Column(UTCDateTime)

    @staticmethod
    async def create(role: int, weight: float) -> RoleWeight:
        role_weight = RoleWeight(role_id=role, weight=weight, timestamp=utcnow())
        await db.add(role_weight)

        return role_weight

    async def remove(self) -> None:
        await db.delete(self)

    @staticmethod
    async def get() -> list[RoleWeight]:
        return await db.all(select(RoleWeight))
