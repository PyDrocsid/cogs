from __future__ import annotations

from datetime import datetime
from typing import Union
from uuid import uuid4

from sqlalchemy import Column, BigInteger, Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import relationship

from PyDrocsid.database import db


class DynGroup(db.Base):
    __tablename__ = "dynvoice_group"

    id: Union[Column, str] = Column(String(36), primary_key=True, unique=True)
    channels: list[DynChannel] = relationship("DynChannel", back_populates="group", cascade="all, delete")

    @staticmethod
    async def create(channel_id: int) -> DynGroup:
        group = DynGroup(id=str(uuid4()))
        group.channels.append(await DynChannel.create(channel_id, group.id))
        await db.add(group)
        return group


class DynChannel(db.Base):
    __tablename__ = "dynvoice_channel"

    channel_id: Union[Column, int] = Column(BigInteger, primary_key=True, unique=True)
    text_id: Union[Column, int] = Column(BigInteger)
    locked: Union[Column, bool] = Column(Boolean)
    group_id: Union[Column, str] = Column(String(36), ForeignKey("dynvoice_group.id"))
    group: DynGroup = relationship("DynGroup", back_populates="channels")
    owner_id: Union[Column, str] = Column(String(36))
    owner_override: Union[Column, int] = Column(BigInteger)
    members: list[DynChannelMember] = relationship(
        "DynChannelMember",
        back_populates="channel",
        cascade="all, delete",
        order_by="DynChannelMember.timestamp",
    )

    @staticmethod
    async def create(channel_id: int, group_id: int) -> DynChannel:
        channel = DynChannel(channel_id=channel_id, text_id=None, locked=False, group_id=group_id)
        await db.add(channel)
        return channel


class DynChannelMember(db.Base):
    __tablename__ = "dynvoice_channel_member"

    id: Union[Column, str] = Column(String(36), primary_key=True, unique=True)
    member_id: Union[Column, int] = Column(BigInteger)
    channel_id: Union[Column, int] = Column(BigInteger, ForeignKey("dynvoice_channel.channel_id"))
    channel: DynChannel = relationship("DynChannel", back_populates="members")
    timestamp: Union[Column, datetime] = Column(DateTime)

    @staticmethod
    async def create(member_id: int, channel_id: int) -> DynChannelMember:
        member = DynChannelMember(
            id=str(uuid4()),
            member_id=member_id,
            channel_id=channel_id,
            timestamp=datetime.utcnow(),
        )
        await db.add(member)
        return member
