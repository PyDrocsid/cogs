from __future__ import annotations

from datetime import datetime
from typing import Optional, Union

from discord.utils import utcnow
from sqlalchemy import BigInteger, Boolean, Column, Float, ForeignKey, Text
from sqlalchemy.orm import relationship

from PyDrocsid.database import Base, UTCDateTime, db, filter_by, select


class Poll(Base):
    __tablename__ = "poll"

    id: Union[Column, int] = Column(BigInteger, primary_key=True, autoincrement=True, unique=True)

    options: list[Option] = relationship("Option", back_populates="poll", cascade="all, delete")

    message_id: Union[Column, int] = Column(BigInteger, unique=True)
    interaction_message_id: Union[Column, int] = Column(BigInteger, unique=True)
    channel_id: Union[Column, int] = Column(BigInteger)
    owner_id: Union[Column, int] = Column(BigInteger)
    timestamp: Union[Column, datetime] = Column(UTCDateTime)
    title: Union[Column, str] = Column(Text(256))
    poll_type: Union[Column, str] = Column(Text(50))
    end_time: Union[Column, datetime] = Column(UTCDateTime)
    anonymous: Union[Column, bool] = Column(Boolean)
    can_delete: Union[Column, bool] = Column(Boolean)
    fair: Union[Column, bool] = Column(Boolean)

    @staticmethod
    async def create(
        message_id: int,
        channel: int,
        owner: int,
        title: str,
        options: list[tuple[str, str]],
        end: Optional[datetime],
        anonymous: bool,
        can_delete: bool,
        poll_type: str,
        interaction: int,
        fair: bool,
    ) -> Poll:
        row = Poll(
            message_id=message_id,
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
        )
        for position, poll_option in enumerate(options):
            await Option.create(
                poll=message_id, emote=poll_option[0], option_text=poll_option[1], field_position=position
            )

        await db.add(row)
        return row

    async def remove(self):
        await db.delete(self)

    async def get_options(self) -> list[Option]:
        return list(await db.all(filter_by(Option, poll_id=self.message_id)))

    async def get_voted_user(self):
        return [await option.get_user() for option in await db.all(filter_by(Option, poll_id=self.message_id))]


class Option(Base):
    __tablename__ = "poll_option"

    id: Union[Column, int] = Column(BigInteger, primary_key=True, autoincrement=True, unique=True)
    poll_id: Union[Column, int] = Column(BigInteger, ForeignKey("poll.message_id"))
    votes: list[Voted] = relationship("Voted", back_populates="option")
    poll: Poll = relationship("Poll", back_populates="options")
    emote: Union[Column, str] = Column(Text(30))
    option: Union[Column, str] = Column(Text(150))
    field_position: Union[Column, int] = Column(BigInteger)

    @staticmethod
    async def create(poll: int, emote: str, option_text: str, field_position: int) -> Option:
        options = Option(poll_id=poll, emote=emote, option=option_text, field_position=field_position)
        await db.add(options)

        return options

    async def get_user(self) -> list[Voted]:
        return list(await db.all(filter_by(Voted, option_id=self.id)))


class Voted(Base):
    __tablename__ = "voted_user"

    id: Union[Column, int] = Column(BigInteger, primary_key=True, autoincrement=True, unique=True)
    user_id: Union[Column, int] = Column(BigInteger)
    option_id: Union[Column, int] = Column(BigInteger, ForeignKey("poll_option.id"))
    option: Option = relationship("Option", back_populates="votes", cascade="all, delete")
    vote_weight: Union[Column, float] = Column(Float)
    poll_id: Union[Column, int] = Column(BigInteger)

    @staticmethod
    async def create(user_id: int, option_id: int, vote_weight: float, poll_id: int):
        row = Voted(user_id=user_id, option_id=option_id, vote_weight=vote_weight, poll_id=poll_id)
        await db.add(row)

    async def remove(self):
        await db.delete(self)


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
