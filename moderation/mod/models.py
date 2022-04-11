from __future__ import annotations

from typing import Union, Optional, Type
from datetime import datetime

from sqlalchemy import Column, Integer, BigInteger, Text, Boolean

from PyDrocsid.database import db, UTCDateTime, Base

from discord.utils import utcnow


class ModBase:
    id: Union[Column, int] = Column(Integer, primary_key=True, unique=True, autoincrement=True)
    member: Union[Column, int] = Column(BigInteger)
    member_name: Union[Column, str] = Column(Text)
    timestamp: Union[Column, datetime] = Column(UTCDateTime)
    reason: Union[Column, str] = Column(Text(collation="utf8mb4_bin"))
    evidence: Union[Column, str] = Column(Text(collation="utf8mb4_bin"))


class Punishment(ModBase):
    mod: Union[Column, int] = Column(BigInteger)
    mod_level: Union[Column, int] = Column(Integer)

    @classmethod
    async def create(
        cls, member: int, member_name: str, mod: int, mod_level: int, reason: str, evidence: Optional[str]
    ) -> Punishment:
        row = cls(
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

    @classmethod
    async def edit(cls, entry_id: int, mod: int, mod_level: int, new_reason: str):
        row = await db.get(cls, id=entry_id)
        row.mod = mod
        row.mod_level = mod_level
        row.reason = new_reason

    @classmethod
    async def delete(cls, entry_id: int):
        row = await db.get(cls, id=entry_id)
        await db.delete(row)


class TimedPunishment(ModBase):
    mod: Union[Column, int] = Column(BigInteger)
    mod_level: Union[Column, int] = Column(Integer)
    minutes: Union[Column, int] = Column(Integer)
    active: Union[Column, bool] = Column(Boolean)
    deactivation_timestamp: Union[Column, Optional[datetime]] = Column(UTCDateTime, nullable=True)
    deactivate_mod: Union[Column, Optional[int]] = Column(BigInteger, nullable=True)
    deactivate_reason: Union[Column, Optional[str]] = Column(Text(collation="utf8mb4_bin"), nullable=True)

    @classmethod
    async def create(
        cls, member: int, member_name: str, mod: int, mod_level: int, minutes: int, reason: str, evidence: Optional[str]
    ) -> TimedPunishment:
        row = cls(
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
            deactivate_mod=None,
            deactivate_reason=None,
        )
        await db.add(row)
        return row

    @classmethod
    async def deactivate(cls, mute_id: int, deactivate_mod: int = None, reason: str = None) -> "TimedPunishment":
        row: TimedPunishment = await db.get(cls, id=mute_id)
        row.active = False
        row.deactivation_timestamp = utcnow()
        row.deactivate_mod = deactivate_mod
        row.deactivate_reason = reason
        return row

    @classmethod
    async def edit_reason(cls, entry_id: int, mod: int, mod_level: int, new_reason: str):
        row = await db.get(cls, id=entry_id)
        row.mod = mod
        row.mod_level = mod_level
        row.reason = new_reason

    @classmethod
    async def edit_duration(cls, entry_id: int, mod: int, mod_level: int, new_duration: int):
        row = await db.get(cls, id=entry_id)
        row.mod = mod
        row.mod_level = mod_level
        row.minutes = new_duration

    @classmethod
    async def delete(cls, entry_id: int):
        row = await db.get(cls, id=entry_id)
        await db.delete(row)


class Report(ModBase, Base):
    __tablename__ = "report"

    reporter: Union[Column, int] = Column(BigInteger)

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


class Warn(Punishment, Base):
    __tablename__ = "warn"


class Mute(TimedPunishment, Base):
    __tablename__ = "mute"


class Kick(Punishment, Base):
    __tablename__ = "kick"


class Ban(TimedPunishment, Base):
    __tablename__ = "ban"
