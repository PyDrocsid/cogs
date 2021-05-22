import secrets
from datetime import datetime
from typing import Union

from sqlalchemy import Column, Integer, Text, BigInteger, DateTime, String, BINARY

from PyDrocsid.database import db


class UserNote(db.Base):
    __tablename__ = "user_notes"

    message_id: Union[Column, int] = Column(BigInteger, primary_key=True, unique=True, autoincrement=True)
    member: Union[Column, int] = Column(BigInteger)
    author: Union[Column, int] = Column(BigInteger)
    message: Union[Column, str] = Column(Text(collation="utf8mb4_bin"))
    timestamp: Union[Column, datetime] = Column(DateTime)

    @staticmethod
    async def create(member: int, message: str, author: int):
        row = UserNote(
            member=member,
            message=message,
            author=author,
            timestamp=datetime.utcnow(),
        )
        await db.add(row)
        return row
