from __future__ import annotations

from datetime import datetime
from typing import Union, Optional
from uuid import uuid4

from discord.utils import utcnow
from sqlalchemy import Column, BigInteger, Boolean, ForeignKey, String
from sqlalchemy.orm import relationship

from PyDrocsid.database import db, UTCDateTime


class DynGroup(db.Base):
    __tablename__ = "dynvoice_group"

    id: Union[Column, str] = Column(String(36), primary_key=True, unique=True)
    user_role: Union[Column, int] = Column(BigInteger)
    channels: list[DynChannel] = relationship("DynChannel", back_populates="group", cascade="all, delete")

    @staticmethod
    async def create(channel_id: int, user_role: int) -> DynGroup:
        group = DynGroup(id=str(uuid4()), user_role=user_role)
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

    @staticmethod
    async def get(**kwargs) -> Optional[DynChannel]:
        return await db.get(
            DynChannel,
            [DynChannel.group, DynGroup.channels],
            DynChannel.members,
            **kwargs,
        )


class DynChannelMember(db.Base):
    __tablename__ = "dynvoice_channel_member"

    id: Union[Column, str] = Column(String(36), primary_key=True, unique=True)
    member_id: Union[Column, int] = Column(BigInteger)
    channel_id: Union[Column, int] = Column(BigInteger, ForeignKey("dynvoice_channel.channel_id"))
    channel: DynChannel = relationship("DynChannel", back_populates="members")
    timestamp: Union[Column, datetime] = Column(UTCDateTime)

    @staticmethod
    async def create(member_id: int, channel_id: int) -> DynChannelMember:
        member = DynChannelMember(
            id=str(uuid4()),
            member_id=member_id,
            channel_id=channel_id,
            timestamp=utcnow(),
        )
        await db.add(member)
        return member


class RoleVoiceLink(db.Base):
    __tablename__ = "role_voice_link"

    role: Union[Column, int] = Column(BigInteger, primary_key=True)
    voice_channel: Union[Column, str] = Column(String(36), primary_key=True)

    @staticmethod
    async def create(role: int, voice_channel: str) -> RoleVoiceLink:
        link = RoleVoiceLink(role=role, voice_channel=voice_channel)
        await db.add(link)
        return link
