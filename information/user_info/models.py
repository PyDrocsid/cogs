from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional, Union

from discord.utils import utcnow
from sqlalchemy import BigInteger, Boolean, Column, Integer, Text

from PyDrocsid.database import Base, UTCDateTime, db, filter_by


class Join(Base):
    __tablename__ = "join"
    id: Union[Column, int] = Column(Integer, primary_key=True, unique=True, autoincrement=True)
    member: Union[Column, int] = Column(BigInteger)
    member_name: Union[Column, str] = Column(Text)
    timestamp: Union[Column, datetime] = Column(UTCDateTime)
    join_msg_channel_id: Union[Column, int] = Column(BigInteger, nullable=True)
    join_msg_id: Union[Column, int] = Column(BigInteger, nullable=True)

    @staticmethod
    async def create(member: int, member_name: str, timestamp: Optional[datetime] = None) -> Join:
        row = Join(member=member, member_name=member_name, timestamp=timestamp or utcnow())
        await db.add(row)
        await db.session.flush()
        return row

    @staticmethod
    async def update(member: int, member_name: str, joined_at: datetime):
        if await db.exists(filter_by(Join, member=member).filter(Join.timestamp >= joined_at - timedelta(minutes=1))):
            return

        await Join.create(member, member_name, joined_at)


class Leave(Base):
    __tablename__ = "leave"
    id: Union[Column, int] = Column(Integer, primary_key=True, unique=True, autoincrement=True)
    member: Union[Column, int] = Column(BigInteger)
    member_name: Union[Column, str] = Column(Text)
    timestamp: Union[Column, datetime] = Column(UTCDateTime)

    @staticmethod
    async def create(member: int, member_name: str) -> Leave:
        row = Leave(member=member, member_name=member_name, timestamp=utcnow())
        await db.add(row)
        return row


class UsernameUpdate(Base):
    __tablename__ = "username_update"

    id: Union[Column, int] = Column(Integer, primary_key=True, unique=True, autoincrement=True)
    member: Union[Column, int] = Column(BigInteger)
    member_name: Union[Column, str] = Column(Text)
    new_name: Union[Column, str] = Column(Text)
    nick: Union[Column, bool] = Column(Boolean)
    timestamp: Union[Column, datetime] = Column(UTCDateTime)

    @staticmethod
    async def create(member: int, member_name: str, new_name: str, nick: bool) -> UsernameUpdate:
        row = UsernameUpdate(member=member, member_name=member_name, new_name=new_name, nick=nick, timestamp=utcnow())
        await db.add(row)
        return row


class Verification(Base):
    __tablename__ = "verification"

    id: Union[Column, int] = Column(Integer, primary_key=True, unique=True, autoincrement=True)
    member: Union[Column, int] = Column(BigInteger)
    member_name: Union[Column, str] = Column(Text)
    accepted: Union[Column, bool] = Column(Boolean)
    timestamp: Union[Column, datetime] = Column(UTCDateTime)

    @staticmethod
    async def create(member: int, member_name: str, accepted: bool) -> Verification:
        row = Verification(member=member, member_name=member_name, accepted=accepted, timestamp=utcnow())
        await db.add(row)
        return row
