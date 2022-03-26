from __future__ import annotations

from datetime import datetime
from typing import Union

from discord.utils import utcnow
from sqlalchemy import Column, BigInteger, Boolean, Integer, Text

from PyDrocsid.database import Base, db, select, UTCDateTime
from PyDrocsid.environment import CACHE_TTL
from PyDrocsid.redis import redis


async def sync_redis() -> list[str]:
    out = []

    async with redis.pipeline() as pipe:
        await pipe.delete("content_filter")

        regex: BadWord
        async for regex in await db.stream(select(BadWord)):
            out.append(regex.regex)
            await pipe.lpush("content_filter", regex.regex)

        await pipe.lpush("content_filter", "")
        await pipe.expire("content_filter", CACHE_TTL)

        await pipe.execute()

    return out


class BadWord(Base):
    __tablename__ = "bad_word_list"

    id: Union[Column, int] = Column(Integer, primary_key=True, unique=True, autoincrement=True)
    regex: Union[Column, str] = Column(Text, unique=True)
    description: Union[Column, str] = Column(Text)
    delete: Union[Column, bool] = Column(Boolean)
    timestamp: Union[Column, datetime] = Column(UTCDateTime)

    @staticmethod
    async def create(regex: str, description: str, delete: bool) -> BadWord:
        row = BadWord(regex=regex, description=description, delete=delete, timestamp=utcnow())
        await db.add(row)
        await sync_redis()
        return row

    async def remove(self) -> None:
        await db.delete(self)
        await sync_redis()

    @staticmethod
    async def get_all_redis() -> list[str]:
        if out := await redis.lrange("content_filter", 0, -1):
            return [x for x in out if x]

        return await sync_redis()

    @staticmethod
    async def get_all_db() -> list[BadWord]:
        return await db.all(select(BadWord))


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
            channel=channel,
            content=content,
            deleted_message=deleted,
            timestamp=utcnow(),
        )
        await db.add(row)
        return row
