from __future__ import annotations

from datetime import datetime
from typing import Union

from PyDrocsid.database import db, db_wrapper, UTCDateTime, Base
from sqlalchemy import Column, BigInteger


class Activity(Base):
    __tablename__ = "activity"

    id: Union[Column, int] = Column(BigInteger, primary_key=True, unique=True)
    timestamp: Union[Column, datetime] = Column(UTCDateTime)

    @staticmethod
    async def create(object_id: int, timestamp: datetime) -> Activity:
        row = Activity(id=object_id, timestamp=timestamp)
        await db.add(row)
        return row

    @staticmethod
    @db_wrapper
    async def update(object_id: int, timestamp: datetime) -> Activity:
        if not (row := await db.get(Activity, id=object_id)):
            row = await Activity.create(object_id, timestamp)
        elif timestamp > row.timestamp:
            row.timestamp = timestamp
        return row
