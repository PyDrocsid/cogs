from __future__ import annotations

from typing import Union

from sqlalchemy import BigInteger, Column

from PyDrocsid.database import Base, db


class ReactionPinChannel(Base):
    __tablename__ = "reactionpin_channel"

    channel: Union[Column, int] = Column(BigInteger, primary_key=True, unique=True)

    @staticmethod
    async def create(channel: int) -> ReactionPinChannel:
        row = ReactionPinChannel(channel=channel)
        await db.add(row)
        return row
