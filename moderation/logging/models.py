from typing import Union

from sqlalchemy import Column, BigInteger

from PyDrocsid.database import db, filter_by, select, delete


class LogExclude(db.Base):
    __tablename__ = "log_exclude"

    channel_id: Union[Column, int] = Column(BigInteger, primary_key=True, unique=True)

    @staticmethod
    async def add(channel_id: int):
        await db.add(LogExclude(channel_id=channel_id))

    @staticmethod
    async def exists(channel_id: int) -> bool:
        return await db.exists(filter_by(LogExclude, channel_id=channel_id))

    @staticmethod
    async def all() -> list[int]:
        return [le.channel_id async for le in await db.stream(select(LogExclude))]

    @staticmethod
    async def remove(channel_id: int):
        await db.exec(delete(LogExclude).filter_by(channel_id=channel_id))
