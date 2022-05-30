from __future__ import annotations

from datetime import datetime
from typing import Optional, Union

from discord.utils import utcnow
from sqlalchemy import BigInteger, Boolean, Column, Integer, String, Text

from PyDrocsid.database import Base, UTCDateTime, db


class AllowedInvite(Base):
    __tablename__ = "allowed_invite"

    guild_id: Union[Column, int] = Column(BigInteger, primary_key=True, unique=True)
    code: Union[Column, str] = Column(String(16))
    guild_name: Union[Column, str] = Column(String(128))
    applicant: Union[Column, int] = Column(BigInteger)
    approver: Union[Column, int] = Column(BigInteger)
    description: Union[Column, Optional[str]] = Column(Text, nullable=True)
    created_at: Union[Column, datetime] = Column(UTCDateTime)

    @staticmethod
    async def create(guild_id: int, code: str, guild_name: str, applicant: int, approver: int) -> AllowedInvite:
        row = AllowedInvite(
            guild_id=guild_id,
            code=code,
            guild_name=guild_name,
            applicant=applicant,
            approver=approver,
            description=None,
            created_at=utcnow(),
        )
        await db.add(row)
        return row

    @staticmethod
    async def update(guild_id: int, code: str, guild_name: str):
        row: AllowedInvite = await db.get(AllowedInvite, guild_id=guild_id)
        row.code = code
        row.guild_name = guild_name


class InviteLog(Base):
    __tablename__ = "invite_log"

    id: Union[Column, int] = Column(Integer, primary_key=True, unique=True, autoincrement=True)
    guild_id: Union[Column, int] = Column(BigInteger)
    guild_name: Union[Column, str] = Column(String(128))
    applicant: Union[Column, int] = Column(BigInteger)
    mod: Union[Column, int] = Column(BigInteger)
    timestamp: Union[Column, datetime] = Column(UTCDateTime)
    approved: Union[Column, bool] = Column(Boolean)

    @staticmethod
    async def create(guild_id: int, guild_name: str, applicant: int, mod: int, approved: bool) -> InviteLog:
        row = InviteLog(
            guild_id=guild_id,
            guild_name=guild_name,
            applicant=applicant,
            mod=mod,
            timestamp=utcnow(),
            approved=approved,
        )
        await db.add(row)
        return row


class IllegalInvitePost(Base):
    __tablename__ = "illegal_invite_post"

    id: Union[Column, int] = Column(Integer, primary_key=True, unique=True, autoincrement=True)
    member: Union[Column, int] = Column(BigInteger)
    member_name: Union[Column, str] = Column(Text)
    channel: Union[Column, int] = Column(BigInteger)
    name: Union[Column, str] = Column(Text)
    timestamp: Union[Column, datetime] = Column(UTCDateTime)

    @staticmethod
    async def create(member: int, member_name: str, channel: int, name: str) -> IllegalInvitePost:
        row = IllegalInvitePost(member=member, member_name=member_name, timestamp=utcnow(), channel=channel, name=name)
        await db.add(row)
        return row
