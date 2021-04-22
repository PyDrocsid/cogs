from datetime import datetime
from typing import Union

from sqlalchemy import Column, Integer, Text, BigInteger, DateTime

from PyDrocsid.database import db


class UserNote(db.Base):
    __tablename__ = "user_notes"

    id: Union[Column, int] = Column(Integer, primary_key=True, unique=True, autoincrement=True)
    member: Union[Column, int] = Column(BigInteger)
    message: Union[Column, str] = Column(Text(collation="utf8mb4_bin"))
    timestamp: Union[Column, datetime] = Column(DateTime)

    @staticmethod
    async def create(member: int, message: str):
        row = UserNote(
            member=member,
            message=message,
            timestamp=datetime.utcnow()
        )
        await db.add(row)
        return row
