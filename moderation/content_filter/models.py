from __future__ import annotations

from datetime import datetime
from typing import Union

from discord.utils import utcnow
from sqlalchemy import Column, BigInteger, Boolean, Integer, Text

from PyDrocsid.database import db, delete, UTCDateTime, Base
from PyDrocsid.redis import redis


class BadWord(Base):
    __tablename__ = "bad_word_list"

    id: Union[Column, int] = Column(Integer, primary_key=True, unique=True, autoincrement=True)
    mod: Union[Column, int] = Column(BigInteger)
    regex: Union[Column, str] = Column(Text)
    description: Union[Column, str] = Column(Text)
    delete: Union[Column, bool] = Column(Boolean)
    timestamp: Union[Column, datetime] = Column(UTCDateTime)

    @staticmethod
    async def add(mod: int, regex: str, deleted: bool, description: str):
        await db.add(BadWord(mod=mod, description=description, regex=regex, delete=deleted))
        await redis.lpush("content_filter", regex)

    @staticmethod
    async def remove(pattern_id: int):

        regex = await db.get(BadWord, id=pattern_id)
        if regex:
            await redis.lrem("content_filter", 0, regex.regex)
            await db.exec(delete(BadWord).filter_by(id=pattern_id))

        return regex

    @staticmethod
    async def get_all() -> list:
        result = await redis.lrange("content_filter", 0, -1)

        for res in result:
            if not await db.get(BadWord, regex=res):
                await redis.lrem("content_filter", 0, res)

        return await redis.lrange("content_filter", 0, -1)

    @staticmethod
    async def exists(pattern_id: int) -> bool:

        regex = await db.get(BadWord, id=pattern_id)
        result = await redis.lrange("content_filter", 0, -1)

        for res in result:
            if not await db.get(BadWord, regex=res):
                await redis.lrem("content_filter", 0, res)

        if regex and regex.regex not in result:
            await redis.lpush("content_filter", regex.regex)
            return True

        if result and regex:
            return regex.regex in result


class BadWordPost(Base):
    __tablename__ = "bad_word_post"

    id: Union[Column, int] = Column(Integer, primary_key=True, unique=True, autoincrement=True)
    member: Union[Column, int] = Column(BigInteger)
    member_name: Union[Column, str] = Column(Text)
    channel: Union[Column, int] = Column(BigInteger)
    content: Union[Column, str] = Column(Text)
    deleted: Union[Column, bool] = Column(Boolean)
    timestamp: Union[Column, datetime] = Column(UTCDateTime)

    @staticmethod
    async def create(member: int, member_name: str, channel: int, content: str, deleted: bool) -> BadWordPost:
        row = BadWordPost(
            member=member,
            member_name=member_name,
            timestamp=utcnow(),
            channel=channel,
            content=content,
            deleted=deleted,
        )
        await db.add(row)
        return row
