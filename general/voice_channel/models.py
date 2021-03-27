from __future__ import annotations

from typing import Union

from PyDrocsid.database import db, select
from sqlalchemy import Column, Integer, String, BigInteger, Boolean


class DynamicVoiceChannel(db.Base):
    __tablename__ = "dynamic_voice_channel"

    channel_id: Union[Column, int] = Column(BigInteger, primary_key=True, unique=True)
    group_id: Union[Column, int] = Column(Integer)
    text_chat_id: Union[Column, int] = Column(BigInteger)
    owner: Union[Column, int] = Column(BigInteger)

    @staticmethod
    async def create(channel_id: int, group_id: int, text_chat_id: int, owner: int) -> DynamicVoiceChannel:
        row = DynamicVoiceChannel(channel_id=channel_id, group_id=group_id, text_chat_id=text_chat_id, owner=owner)
        await db.add(row)
        return row

    @staticmethod
    async def change_owner(channel_id: int, owner: int):
        row: DynamicVoiceChannel = await db.first(select(DynamicVoiceChannel).filter_by(channel_id=channel_id))
        row.owner = owner


class DynamicVoiceGroup(db.Base):
    __tablename__ = "dynamic_voice_group"

    id: Union[Column, int] = Column(Integer, primary_key=True, unique=True)
    name: Union[Column, str] = Column(String(32))
    channel_id: Union[Column, int] = Column(BigInteger)
    public: Union[Column, bool] = Column(Boolean)

    @staticmethod
    async def create(name: str, channel_id: int, public: bool) -> DynamicVoiceGroup:
        row = DynamicVoiceGroup(name=name, channel_id=channel_id, public=public)
        await db.add(row)
        return row


class RoleVoiceLink(db.Base):
    __tablename__ = "role_voice_link"

    role: Union[Column, int] = Column(BigInteger, primary_key=True)
    voice_channel: Union[Column, int] = Column(BigInteger, primary_key=True)

    @staticmethod
    async def create(role: int, voice_channel: int) -> RoleVoiceLink:
        link = RoleVoiceLink(role=role, voice_channel=voice_channel)

        await db.add(link)

        return link
