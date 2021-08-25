from typing import Union

from PyDrocsid.database import db
from sqlalchemy import Column, BigInteger


class CleverBotChannel(db.Base):
    __tablename__ = "cleverbot_channel"

    channel: Union[Column, int] = Column(BigInteger, primary_key=True, unique=True)

    @staticmethod
    async def create(channel: int) -> "CleverBotChannel":
        row = CleverBotChannel(channel=channel)
        await db.add(row)
        return row
