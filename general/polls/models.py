from __future__ import annotations

from datetime import datetime
from typing import Union

from discord.utils import utcnow
from sqlalchemy import BigInteger, Boolean, Column, Float, ForeignKey, Text
from sqlalchemy.orm import relationship

from PyDrocsid.database import Base, UTCDateTime, db, select


class TeamYesNo(Base):
    __tablename__ = "team_yes_no"

    message_id: Union[Column, int] = Column(BigInteger, unique=True, primary_key=True)
    users: list[YesNoUser] = relationship("YesNoUser", back_populates="poll", cascade="all, delete")
    in_favor: Union[Column, int] = Column(Float)
    against: Union[Column, int] = Column(Float)
    abstention: Union[Column, int] = Column(Float)
    timestamp: Union[Column, datetime] = Column(UTCDateTime)

    @staticmethod
    async def create(message_id: int) -> TeamYesNo:
        row = TeamYesNo(message_id=message_id, in_favor=0, against=0, abstention=0, timestamp=utcnow())
        await db.add(row)
        return row


class YesNoUser(Base):
    __tablename__ = "team_yes_no_voter"

    id: Union[Column, int] = Column(BigInteger, primary_key=True, autoincrement=True, unique=True)
    poll_id: Union[Column, int] = Column(BigInteger, ForeignKey("team_yes_no.message_id"))
    poll: TeamYesNo = relationship("TeamYesNo", back_populates="users")
    option: Union[Column, int] = Column(BigInteger)
    user: Union[Column, int] = Column(BigInteger)

    @staticmethod
    async def create(user: int, poll_id: int, option: int) -> YesNoUser:
        row = YesNoUser(user=user, poll_id=poll_id, option=option)
        await db.add(row)
        return row


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
    poll_open: Union[Column, bool] = Column(Boolean)
    can_delete: Union[Column, bool] = Column(Boolean)
    keep: Union[Column, bool] = Column(Boolean)

    @staticmethod
    async def create(
        message_id: int,
        channel: int,
        owner: int,
        title: str,
        options: list,
        end: int,
        anonymous: bool,
        can_delete: bool,
        keep: bool,
        poll_type: str,
    ) -> Poll:
        row = Poll(
            message_id=message_id,
            poll_channel=channel,
            owner_id=owner,
            timestamp=utcnow(),
            title=title,
            poll_type=poll_type,
            end=end,
            anonymous=anonymous,
            can_delete=can_delete,
            keep=keep,
        )
        for poll_option in options:
            await Option.create(poll=message_id, emote=poll_option.emoji, option_text=poll_option.option)

        await db.add(row)
        return row

    async def remove(self):
        await db.delete(self)


class Option(Base):
    __tablename__ = "poll_option"

    id: Union[Column, int] = Column(BigInteger, primary_key=True, autoincrement=True, unique=True)
    poll_id: Union[Column, int] = Column(BigInteger, ForeignKey("poll.message_id"))
    votes: list[Voted] = relationship("Voted", back_populates="option")
    poll: Poll = relationship("Poll", back_populates="options")
    emote: Union[Column, str] = Column(Text(30))
    option: Union[Column, str] = Column(Text(150))

    @staticmethod
    async def create(poll: int, emote: str, option_text: str) -> Option:
        options = Option(poll_id=poll, emote=emote, option=option_text)
        await db.add(options)

        return options


class Voted(Base):
    __tablename__ = "voted_user"

    id: Union[Column, int] = Column(BigInteger, primary_key=True, autoincrement=True, unique=True)
    user_id: Union[Column, int] = Column(BigInteger)
    option_id: Union[Column, int] = Column(BigInteger, ForeignKey("poll_option.id"))
    option: Option = relationship("Option", back_populates="votes", cascade="all, delete")
    vote_weight: Union[Column, float] = Column(Float)

    @staticmethod
    async def create(user_id: int, option_id: int, vote_weight: float):
        row = Voted(user_id=user_id, option_id=option_id, vote_weight=vote_weight)
        await db.add(row)


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
