from __future__ import annotations

from datetime import datetime
from typing import Union, AsyncIterable

from sqlalchemy import Column, BigInteger, Integer, Text, DateTime

from PyDrocsid.database import db, filter_by, select, delete
from PyDrocsid.environment import CACHE_TTL
from PyDrocsid.redis import redis


class MediaOnlyChannel(db.Base):
    __tablename__ = "mediaonly_channel"

    channel: Union[Column, int] = Column(BigInteger, primary_key=True, unique=True)

    @staticmethod
    async def add(channel: int):
        await redis.setex(f"mediaonly:channel={channel}", CACHE_TTL, 1)
        await db.add(MediaOnlyChannel(channel=channel))

    @staticmethod
    async def exists(channel: int) -> bool:
        if result := await redis.get(key := f"mediaonly:channel={channel}"):
            return result == "1"

        result = await db.exists(filter_by(MediaOnlyChannel, channel=channel))
        await redis.setex(key, CACHE_TTL, int(result))
        return result

    @staticmethod
    async def stream() -> AsyncIterable[int]:
        row: MediaOnlyChannel
        tr = redis.multi_exec()
        async for row in await db.stream(select(MediaOnlyChannel)):
            channel = row.channel
            tr.setex(f"mediaonly:channel={channel}", CACHE_TTL, 1)
            yield channel
        await tr.execute()

    @staticmethod
    async def remove(channel: int):
        await redis.setex(f"mediaonly:channel={channel}", CACHE_TTL, 0)
        await db.exec(delete(MediaOnlyChannel).filter_by(channel=channel))


class MediaOnlyDeletion(db.Base):
    __tablename__ = "mediaonly_deletion"

    id: Union[Column, int] = Column(Integer, primary_key=True, unique=True, autoincrement=True)
    member: Union[Column, int] = Column(BigInteger)
    member_name: Union[Column, str] = Column(Text(collation="utf8mb4_bin"))
    channel: Union[Column, int] = Column(BigInteger)
    timestamp: Union[Column, datetime] = Column(DateTime)

    @staticmethod
    async def create(member: int, member_name: str, channel: int) -> MediaOnlyDeletion:
        row = MediaOnlyDeletion(
            member=member,
            member_name=member_name,
            timestamp=datetime.utcnow(),
            channel=channel,
        )
        await db.add(row)
        return row
