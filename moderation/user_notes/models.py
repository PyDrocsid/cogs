import secrets
from datetime import datetime
from typing import Union

from sqlalchemy import Column, Integer, Text, BigInteger, DateTime, String, BINARY

from PyDrocsid.database import db


class UserNote(db.Base):
    __tablename__ = "user_notes"

    message_id: Union[Column, str] = Column(String(length=10), primary_key=True, unique=True)
    member: Union[Column, int] = Column(BigInteger)
    applicant: Union[Column, str] = Column(Text(collation="utf8mb4_bin"))
    message: Union[Column, str] = Column(Text(collation="utf8mb4_bin"))
    timestamp: Union[Column, datetime] = Column(DateTime)

    @staticmethod
    async def create(member: int, message: str, applicant: str):
        row = UserNote(
            message_id=secrets.token_hex(nbytes=5)[:10],
            member=member,
            message=message,
            applicant=applicant,
            timestamp=datetime.utcnow()
        )
        await db.add(row)
        return row
