from __future__ import annotations

from datetime import datetime
from typing import Optional, Union

from discord.utils import utcnow
from sqlalchemy import BigInteger, Boolean, Column, Float, ForeignKey, Text
from sqlalchemy.orm import relationship

from PyDrocsid.database import Base, UTCDateTime, db, select


# tabelle für vote stimmen (ForeignKey)
# konfigutierbar ausschluss der mute-rolle
# userpolls abspecken
# default werte in settings
# wizzard weg (alles eine zeile)
# yn so lassen


class Poll:
    def __init__(self, owner: int, channel: int):
        self.owner: int = owner
        self.channel: int = channel
        self.message_id: int = 0

        self.question: str = ""
        self.type: str = "standard"  # standard, team
        self.options: list[tuple[str, str]] = []  # [(emote, option), ...]
        self.max_votes: int = 1
        self.voted: dict[str, tuple[list[int], int]] = {}  # {"user1": ([option_number, ...], weight), ...}
        self.votes: dict[str, int]  # {option: number_of_votes, ...}
        self.roles: dict[str, float] = {}  # {"role_id": weight, ...}
        self.hidden: bool = False
        self.duration: Optional[datetime] = None
        self.active: bool = False


class Polls(Base):
    __tablename__ = "polls"

    id: Union[Column, int] = Column(BigInteger, primary_key=True, autoincrement=True, unique=True)

    options: list[Options] = relationship("Options", back_populates="poll")

    message_id: Union[Column, int] = Column(BigInteger, unique=True)
    poll_channel: Union[Column, int] = Column(BigInteger)
    owner_id: Union[Column, int] = Column(BigInteger)
    timestamp: Union[Column, datetime] = Column(UTCDateTime)
    title: Union[Column, str] = Column(Text(256))
    poll_type: Union[Column, str] = Column(Text(50))
    end_time: Union[Column, datetime] = Column(UTCDateTime)
    hidden_votes: Union[Column, bool] = Column(Boolean)
    votes_amount: Union[Column, int] = Column(BigInteger)
    poll_open: Union[Column, bool] = Column(Boolean)
    can_delete: Union[Column, bool] = Column(Boolean)
    keep: Union[Column, bool] = Column(Boolean)


class Voted(Base):
    __tablename__ = "voted_user"

    id: Union[Column, int] = Column(BigInteger, primary_key=True, autoincrement=True, unique=True)
    user_id: Union[Column, int] = Column(BigInteger)
    option_id: Options = relationship("Options")
    vote_weight: Union[Column, float] = Column(Float)


class Options(Base):
    __tablename__ = "poll_options"

    id: Union[Column, int] = Column(
        BigInteger, ForeignKey("voted_user.option_id"), primary_key=True, autoincrement=True, unique=True
    )
    poll_id: Union[Column, int] = Column(BigInteger, ForeignKey("polls.id"))
    emote: Union[Column, str] = Column(Text(30))
    option: Union[Column, str] = Column(Text(150))

    @staticmethod
    async def create(poll: int, emote: str, option_text: str) -> Options:
        options = Options(poll_id=poll, emote=emote, option=option_text)
        await db.add(options)

        return options


class RolesWeights(Base):
    __tablename__ = "roles_weight"

    id: Union[Column, int] = Column(BigInteger, primary_key=True, autoincrement=True, unique=True)
    role_id: Union[Column, int] = Column(BigInteger, unique=True)
    weight: Union[Column, float] = Column(Float)
    timestamp: Union[Column, datetime] = Column(UTCDateTime)

    @staticmethod
    async def create(role: int, weight: float) -> RolesWeights:
        roles_weights = RolesWeights(role_id=role, weight=weight, timestamp=utcnow())
        await db.add(roles_weights)

        return roles_weights

    async def remove(self) -> None:
        await db.delete(self)

    @staticmethod
    async def get() -> list[RolesWeights]:
        return await db.all(select(RolesWeights))
