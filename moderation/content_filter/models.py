from __future__ import annotations

from datetime import datetime
from typing import Union

from discord.utils import utcnow
from sqlalchemy import Column, BigInteger, Boolean, Integer, Text

from PyDrocsid.database import db, filter_by, UTCDateTime, Base
from PyDrocsid.redis import redis


async def sync_redis():
    await redis.delete("content_filter")

    regex: BadWord
    async for regex in await db.stream(select(BadWord)):
        await redis.lpush("content_filter", regex.regex)


class BadWord(Base):
    __tablename__ = "bad_word_list"

    id: Union[Column, int] = Column(Integer, primary_key=True, unique=True, autoincrement=True)
    regex: Union[Column, str] = Column(Text, unique=True)
    description: Union[Column, str] = Column(Text)
    delete: Union[Column, bool] = Column(Boolean)
    timestamp: Union[Column, datetime] = Column(UTCDateTime)

    @staticmethod
    async def create(regex: str, deleted: bool, description: str):
        await db.add(BadWord(description=description, regex=regex, delete=deleted, timestamp=utcnow()))
        await sync_redis()

    async def remove(self):
        await db.delete(self)
        await sync_redis()

    @staticmethod
    async def get_all_redis() -> list[str]:
        return await redis.lrange("content_filter", 0, -1)

    @staticmethod
    async def get_all_db() -> list[BadWord]:
        return await db.all(filter_by(BadWord))


class BadWordPost(Base):
    __tablename__ = "bad_word_post"

    id: Union[Column, int] = Column(Integer, primary_key=True, unique=True, autoincrement=True)
    member: Union[Column, int] = Column(BigInteger)
    member_name: Union[Column, str] = Column(Text)
    channel: Union[Column, int] = Column(BigInteger)
    content: Union[Column, str] = Column(Text)
    deleted_message: Union[Column, bool] = Column(Boolean)
    timestamp: Union[Column, datetime] = Column(UTCDateTime)

    @staticmethod
    async def create(member: int, member_name: str, channel: int, content: str, deleted: bool) -> BadWordPost:
        row = BadWordPost(
            member=member,
            member_name=member_name,
            timestamp=utcnow(),
            channel=channel,
            content=content,
            deleted_message=deleted,
        )
        await db.add(row)
        return row
