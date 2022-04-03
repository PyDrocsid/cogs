from typing import Union

from sqlalchemy import BigInteger, Column

from PyDrocsid.database import Base, db


class CleverBotChannel(Base):
    __tablename__ = "cleverbot_channel"

    channel: Union[Column, int] = Column(BigInteger, primary_key=True, unique=True)

    @staticmethod
    async def create(channel: int) -> "CleverBotChannel":
        row = CleverBotChannel(channel=channel)
        await db.add(row)
        return row
