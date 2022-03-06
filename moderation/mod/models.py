from __future__ import annotations

from datetime import datetime
from typing import Union, Optional

from discord.utils import utcnow
from sqlalchemy import Column, Integer, BigInteger, Text, Boolean

from PyDrocsid.database import db, UTCDateTime, Base


class Report(Base):
    __tablename__ = "report"

    id: Union[Column, int] = Column(Integer, primary_key=True, unique=True, autoincrement=True)
    member: Union[Column, int] = Column(BigInteger)
    member_name: Union[Column, str] = Column(Text)
    reporter: Union[Column, int] = Column(BigInteger)
    timestamp: Union[Column, datetime] = Column(UTCDateTime)
    reason: Union[Column, str] = Column(Text)

    @staticmethod
    async def create(member: int, member_name: str, reporter: int, reason: str) -> Report:
        row = Report(member=member, member_name=member_name, reporter=reporter, timestamp=utcnow(), reason=reason)
        await db.add(row)
        return row


class Warn(Base):
    __tablename__ = "warn"

    id: Union[Column, int] = Column(Integer, primary_key=True, unique=True, autoincrement=True)
    member: Union[Column, int] = Column(BigInteger)
    member_name: Union[Column, str] = Column(Text)
    mod: Union[Column, int] = Column(BigInteger)
    timestamp: Union[Column, datetime] = Column(UTCDateTime)
    reason: Union[Column, str] = Column(Text)

    @staticmethod
    async def create(member: int, member_name: str, mod: int, reason: str) -> Warn:
        row = Warn(member=member, member_name=member_name, mod=mod, timestamp=utcnow(), reason=reason)
        await db.add(row)
        return row


class Mute(Base):
    __tablename__ = "mute"

    id: Union[Column, int] = Column(Integer, primary_key=True, unique=True, autoincrement=True)
    member: Union[Column, int] = Column(BigInteger)
    member_name: Union[Column, str] = Column(Text)
    mod: Union[Column, int] = Column(BigInteger)
    timestamp: Union[Column, datetime] = Column(UTCDateTime)
    days: Union[Column, int] = Column(Integer)
    reason: Union[Column, str] = Column(Text)
    active: Union[Column, bool] = Column(Boolean)
    deactivation_timestamp: Union[Column, Optional[datetime]] = Column(UTCDateTime, nullable=True)
    unmute_mod: Union[Column, Optional[int]] = Column(BigInteger, nullable=True)
    unmute_reason: Union[Column, Optional[str]] = Column(Text, nullable=True)
    upgraded: Union[Column, bool] = Column(Boolean, default=False)
    is_upgrade: Union[Column, bool] = Column(Boolean)

    @staticmethod
    async def create(member: int, member_name: str, mod: int, days: int, reason: str, is_upgrade: bool = False) -> Mute:
        row = Mute(
            member=member,
            member_name=member_name,
            mod=mod,
            timestamp=utcnow(),
            days=days,
            reason=reason,
            active=True,
            deactivation_timestamp=None,
            unmute_mod=None,
            unmute_reason=None,
            is_upgrade=is_upgrade,
        )
        await db.add(row)
        return row

    @staticmethod
    async def deactivate(mute_id: int, unmute_mod: int = None, reason: str = None) -> "Mute":
        row: Mute = await db.get(Mute, id=mute_id)
        row.active = False
        row.deactivation_timestamp = utcnow()
        row.unmute_mod = unmute_mod
        row.unmute_reason = reason
        return row

    @staticmethod
    async def upgrade(ban_id: int, mod: int):
        mute = await Mute.deactivate(ban_id, mod)
        mute.upgraded = True


class Kick(Base):
    __tablename__ = "kick"

    id: Union[Column, int] = Column(Integer, primary_key=True, unique=True, autoincrement=True)
    member: Union[Column, int] = Column(BigInteger)
    member_name: Union[Column, str] = Column(Text)
    mod: Union[Column, int] = Column(BigInteger)
    timestamp: Union[Column, datetime] = Column(UTCDateTime)
    reason: Union[Column, str] = Column(Text)

    @staticmethod
    async def create(member: int, member_name: str, mod: Optional[int], reason: Optional[str]) -> Kick:
        row = Kick(member=member, member_name=member_name, mod=mod, timestamp=utcnow(), reason=reason)
        await db.add(row)
        return row


class Ban(Base):
    __tablename__ = "ban"

    id: Union[Column, int] = Column(Integer, primary_key=True, unique=True, autoincrement=True)
    member: Union[Column, int] = Column(BigInteger)
    member_name: Union[Column, str] = Column(Text)
    mod: Union[Column, int] = Column(BigInteger)
    timestamp: Union[Column, datetime] = Column(UTCDateTime)
    days: Union[Column, int] = Column(Integer)
    reason: Union[Column, str] = Column(Text)
    active: Union[Column, bool] = Column(Boolean)
    deactivation_timestamp: Union[Column, Optional[datetime]] = Column(UTCDateTime, nullable=True)
    unban_reason: Union[Column, Optional[str]] = Column(Text, nullable=True)
    unban_mod: Union[Column, Optional[int]] = Column(BigInteger, nullable=True)
    upgraded: Union[Column, bool] = Column(Boolean, default=False)
    is_upgrade: Union[Column, bool] = Column(Boolean)

    @staticmethod
    async def create(member: int, member_name: str, mod: int, days: int, reason: str, is_upgrade: bool = False) -> Ban:
        row = Ban(
            member=member,
            member_name=member_name,
            mod=mod,
            timestamp=utcnow(),
            days=days,
            reason=reason,
            active=True,
            deactivation_timestamp=None,
            unban_reason=None,
            unban_mod=None,
            is_upgrade=is_upgrade,
        )
        await db.add(row)
        return row

    @staticmethod
    async def deactivate(ban_id: int, unban_mod: int = None, unban_reason: str = None) -> Ban:
        row: Ban = await db.get(Ban, id=ban_id)
        row.active = False
        row.deactivation_timestamp = utcnow()
        row.unban_mod = unban_mod
        row.unban_reason = unban_reason
        return row

    @staticmethod
    async def upgrade(ban_id: int, mod: int):
        ban = await Ban.deactivate(ban_id, mod)
        ban.upgraded = True
