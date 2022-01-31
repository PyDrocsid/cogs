from __future__ import annotations

from datetime import datetime
from typing import Union

from discord.utils import utcnow
from sqlalchemy import Column, BigInteger, Boolean, Integer, Text

from PyDrocsid.database import db, delete, filter_by, UTCDateTime, Base
from PyDrocsid.redis import redis


async def sync_redis():
    regex_list = await db.all(filter_by(BadWord))

    if regex_list:
        await redis.delete("content_filter")

        regex: BadWord
        for regex in regex_list:
            await redis.lpush("content_filter", regex.regex)


class BadWord(Base):
    __tablename__ = "bad_word_list"

    id: Union[Column, int] = Column(Integer, primary_key=True, unique=True, autoincrement=True)
    mod: Union[Column, int] = Column(BigInteger)
    regex: Union[Column, str] = Column(Text)
    description: Union[Column, str] = Column(Text)
    delete: Union[Column, bool] = Column(Boolean)
    timestamp: Union[Column, datetime] = Column(UTCDateTime)

    @staticmethod
    async def create(mod: int, regex: str, deleted: bool, description: str):
        await db.add(BadWord(mod=mod, description=description, regex=regex, delete=deleted))
        await sync_redis()

    @staticmethod
    async def remove(pattern_id: int):

        regex = await db.get(BadWord, id=pattern_id)
        if regex:
            await db.exec(delete(BadWord).filter_by(id=pattern_id))
            await sync_redis()

        return regex

    @staticmethod
    async def get_all() -> list:

        return await db.all(filter_by(BadWord))

    @staticmethod
    async def exists(pattern_id: int) -> bool:

        regex = await db.get(BadWord, id=pattern_id)

        return True if regex else False


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
