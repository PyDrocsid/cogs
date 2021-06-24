from typing import Union

from PyDrocsid.database import db, db_wrapper
from sqlalchemy import Column, Integer, BigInteger


class AutoDeleteMessage(db.Base):
    __tablename__ = "auto_delete_messages"

    channel: Union[Column, int] = Column(BigInteger, primary_key=True, unique=True)
    minutes: Union[Column, int] = Column(Integer)

    @staticmethod
    async def create(channel: int, minutes: int):
        row = AutoDeleteMessage(
            channel=channel,
            minutes=minutes,
        )
        await db.add(row)
        return row

    @staticmethod
    @db_wrapper
    async def update(channel: int, minutes: int):
        row: AutoDeleteMessage = await db.get(AutoDeleteMessage, channel=channel)
        row.minutes = minutes
        return row
