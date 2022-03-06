from __future__ import annotations

from typing import Union, Optional
from datetime import datetime

from sqlalchemy import Column, Integer, BigInteger, Text, Boolean

from PyDrocsid.database import db, UTCDateTime, Base

from discord.utils import utcnow


class Report(Base):
    __tablename__ = "report"

    id: Union[Column, int] = Column(Integer, primary_key=True, unique=True, autoincrement=True)
    member: Union[Column, int] = Column(BigInteger)
    member_name: Union[Column, str] = Column(Text)
    reporter: Union[Column, int] = Column(BigInteger)
    timestamp: Union[Column, datetime] = Column(UTCDateTime)
    reason: Union[Column, str] = Column(Text(collation="utf8mb4_bin"))
    evidence: Union[Column, str] = Column(Text(collation="utf8mb4_bin"))

    @staticmethod
    async def create(member: int, member_name: str, reporter: int, reason: str, evidence: Optional[str]) -> Report:
        row = Report(
            member=member,
            member_name=member_name,
            reporter=reporter,
            timestamp=utcnow(),
            reason=reason,
            evidence=evidence,
        )
        await db.add(row)
        return row


class Warn(Base):
    __tablename__ = "warn"

    id: Union[Column, int] = Column(Integer, primary_key=True, unique=True, autoincrement=True)
    member: Union[Column, int] = Column(BigInteger)
    member_name: Union[Column, str] = Column(Text)
    mod: Union[Column, int] = Column(BigInteger)
    mod_level: Union[Column, int] = Column(Integer)
    timestamp: Union[Column, datetime] = Column(UTCDateTime)
    reason: Union[Column, str] = Column(Text(collation="utf8mb4_bin"))
    evidence: Union[Column, str] = Column(Text(collation="utf8mb4_bin"))

    @staticmethod
    async def create(
        member: int, member_name: str, mod: int, mod_level: int, reason: str, evidence: Optional[str]
    ) -> Warn:
        row = Warn(
            member=member,
            member_name=member_name,
            mod=mod,
            mod_level=mod_level,
            timestamp=utcnow(),
            reason=reason,
            evidence=evidence,
        )
        await db.add(row)
        return row

    @staticmethod
    async def edit(warn_id: int, mod: int, mod_level: int, new_reason: str):
        row = await db.get(Warn, id=warn_id)
        row.mod = mod
        row.mod_level = mod_level
        row.reason = new_reason

    @staticmethod
    async def delete(warn_id: int):
        row = await db.get(Warn, id=warn_id)
        await db.delete(row)


class Mute(Base):
    __tablename__ = "mute"

    id: Union[Column, int] = Column(Integer, primary_key=True, unique=True, autoincrement=True)
    member: Union[Column, int] = Column(BigInteger)
    member_name: Union[Column, str] = Column(Text)
    mod: Union[Column, int] = Column(BigInteger)
    mod_level: Union[Column, int] = Column(Integer)
    timestamp: Union[Column, datetime] = Column(UTCDateTime)
    minutes: Union[Column, int] = Column(Integer)
    reason: Union[Column, str] = Column(Text(collation="utf8mb4_bin"))
    evidence: Union[Column, str] = Column(Text(collation="utf8mb4_bin"))
    active: Union[Column, bool] = Column(Boolean)
    deactivation_timestamp: Union[Column, Optional[datetime]] = Column(UTCDateTime, nullable=True)
    unmute_mod: Union[Column, Optional[int]] = Column(BigInteger, nullable=True)
    unmute_reason: Union[Column, Optional[str]] = Column(Text(collation="utf8mb4_bin"), nullable=True)

    @staticmethod
    async def create(
        member: int, member_name: str, mod: int, mod_level: int, minutes: int, reason: str, evidence: Optional[str]
    ) -> Mute:
        row = Mute(
            member=member,
            member_name=member_name,
            mod=mod,
            mod_level=mod_level,
            timestamp=utcnow(),
            minutes=minutes,
            reason=reason,
            evidence=evidence,
            active=True,
            deactivation_timestamp=None,
            unmute_mod=None,
            unmute_reason=None,
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
    async def edit_reason(mute_id: int, mod: int, mod_level: int, new_reason: str):
        row = await db.get(Mute, id=mute_id)
        row.mod = mod
        row.mod_level = mod_level
        row.reason = new_reason

    @staticmethod
    async def edit_duration(mute_id: int, mod: int, mod_level: int, new_duration: int):
        row = await db.get(Mute, id=mute_id)
        row.mod = mod
        row.mod_level = mod_level
        row.minutes = new_duration

    @staticmethod
    async def delete(mute_id: int):
        row = await db.get(Mute, id=mute_id)
        await db.delete(row)


class Kick(Base):
    __tablename__ = "kick"

    id: Union[Column, int] = Column(Integer, primary_key=True, unique=True, autoincrement=True)
    member: Union[Column, int] = Column(BigInteger)
    member_name: Union[Column, str] = Column(Text)
    mod: Union[Column, int] = Column(BigInteger)
    mod_level: Union[Column, int] = Column(Integer)
    timestamp: Union[Column, datetime] = Column(UTCDateTime)
    reason: Union[Column, str] = Column(Text(collation="utf8mb4_bin"))
    evidence: Union[Column, str] = Column(Text(collation="utf8mb4_bin"))

    @staticmethod
    async def create(
        member: int,
        member_name: str,
        mod: Optional[int],
        mod_level: Optional[int],
        reason: Optional[str],
        evidence: Optional[str],
    ) -> Kick:
        row = Kick(
            member=member,
            member_name=member_name,
            mod=mod,
            mod_level=mod_level,
            timestamp=utcnow(),
            reason=reason,
            evidence=evidence,
        )
        await db.add(row)
        return row

    @staticmethod
    async def edit(kick_id: int, mod: int, mod_level: int, new_reason: str):
        row = await db.get(Kick, id=kick_id)
        row.mod = mod
        row.mod_level = mod_level
        row.reason = new_reason

    @staticmethod
    async def delete(kick_id: int):
        row = await db.get(Kick, id=kick_id)
        await db.delete(row)


class Ban(Base):
    __tablename__ = "ban"

    id: Union[Column, int] = Column(Integer, primary_key=True, unique=True, autoincrement=True)
    member: Union[Column, int] = Column(BigInteger)
    member_name: Union[Column, str] = Column(Text)
    mod: Union[Column, int] = Column(BigInteger)
    mod_level: Union[Column, int] = Column(Integer)
    timestamp: Union[Column, datetime] = Column(UTCDateTime)
    minutes: Union[Column, int] = Column(Integer)
    reason: Union[Column, str] = Column(Text(collation="utf8mb4_bin"))
    evidence: Union[Column, str] = Column(Text(collation="utf8mb4_bin"))
    active: Union[Column, bool] = Column(Boolean)
    deactivation_timestamp: Union[Column, Optional[datetime]] = Column(UTCDateTime, nullable=True)
    unban_reason: Union[Column, Optional[str]] = Column(Text, nullable=True)
    unban_mod: Union[Column, Optional[int]] = Column(BigInteger, nullable=True)

    @staticmethod
    async def create(
        member: int, member_name: str, mod: int, mod_level: int, minutes: int, reason: str, evidence: Optional[str]
    ) -> Ban:
        row = Ban(
            member=member,
            member_name=member_name,
            mod=mod,
            mod_level=mod_level,
            timestamp=utcnow(),
            minutes=minutes,
            reason=reason,
            evidence=evidence,
            active=True,
            deactivation_timestamp=None,
            unban_reason=None,
            unban_mod=None,
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
    async def edit_reason(ban_id: int, mod: int, mod_level: int, new_reason: str):
        row = await db.get(Ban, id=ban_id)
        row.mod = mod
        row.mod_level = mod_level
        row.reason = new_reason

    @staticmethod
    async def edit_duration(ban_id: int, mod: int, mod_level: int, new_duration: int):
        row = await db.get(Ban, id=ban_id)
        row.mod = mod
        row.mod_level = mod_level
        row.minutes = new_duration

    @staticmethod
    async def delete(ban_id: int):
        row = await db.get(Ban, id=ban_id)
        await db.delete(row)
