from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from discord.utils import utcnow
from sqlalchemy import BigInteger, Boolean, Column, Integer, Text

from PyDrocsid.database import Base, UTCDateTime, db


class ModBase(Base if TYPE_CHECKING else object):
    id: Column | int = Column(Integer, primary_key=True, unique=True, autoincrement=True)
    member: Column | int = Column(BigInteger)
    member_name: Column | str = Column(Text)
    timestamp: Column | datetime = Column(UTCDateTime)
    reason: Column | str = Column(Text(collation="utf8mb4_bin"))
    evidence: Column | str = Column(Text(collation="utf8mb4_bin"))


class Punishment(ModBase):
    mod: Column | int = Column(BigInteger)
    mod_level: Column | int = Column(Integer)

    @classmethod
    async def create(
        cls, member: int, member_name: str, mod: int | None, reason: str | None, evidence: str | None
    ) -> Punishment:
        row = cls(member=member, member_name=member_name, mod=mod, timestamp=utcnow(), reason=reason, evidence=evidence)
        await db.add(row)
        return row

    @classmethod
    async def edit(cls, entry_id: int, mod: int, new_reason: str):
        row = await db.get(cls, id=entry_id)
        row.mod = mod
        row.reason = new_reason

    @classmethod
    async def delete(cls, entry_id: int):
        row = await db.get(cls, id=entry_id)
        await db.delete(row)


class TimedPunishment(ModBase):
    mod: Column | int = Column(BigInteger)
    minutes: Column | int = Column(Integer)
    active: Column | bool = Column(Boolean)
    deactivation_timestamp: Column | datetime | None = Column(UTCDateTime, nullable=True)
    deactivate_mod: Column | int | None = Column(BigInteger, nullable=True)
    deactivate_reason: Column | str | None = Column(Text(collation="utf8mb4_bin"), nullable=True)

    @classmethod
    async def create(
        cls, member: int, member_name: str, mod: int, minutes: int, reason: str, evidence: str | None
    ) -> TimedPunishment:
        row = cls(
            member=member,
            member_name=member_name,
            mod=mod,
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
    async def deactivate(cls, mute_id: int, deactivate_mod: int = None, reason: str = None) -> TimedPunishment:
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

    reporter: Column | int = Column(BigInteger)

    @staticmethod
    async def create(member: int, member_name: str, reporter: int, reason: str, evidence: str | None) -> Report:
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
