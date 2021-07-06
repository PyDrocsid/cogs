from __future__ import annotations

from typing import Union

from PyDrocsid.database import db
from PyDrocsid.database import select
from sqlalchemy import Column, Integer, BigInteger


class AutoDeleteMessage(db.Base):
    __tablename__ = "auto_delete_messages"

    channel: Union[Column, int] = Column(BigInteger, primary_key=True, unique=True)
    minutes: Union[Column, int] = Column(Integer)

    @staticmethod
    async def create(channel: int, minutes: int) -> AutoDeleteMessage:
        row = AutoDeleteMessage(channel=channel, minutes=minutes)
        await db.add(row)
        return row
