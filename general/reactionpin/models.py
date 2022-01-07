from __future__ import annotations

from typing import Union

from PyDrocsid.database import db, Base
from sqlalchemy import Column, BigInteger


class ReactionPinChannel(Base):
    __tablename__ = "reactionpin_channel"

    channel: Union[Column, int] = Column(BigInteger, primary_key=True, unique=True)

    @staticmethod
    async def create(channel: int) -> ReactionPinChannel:
        row = ReactionPinChannel(channel=channel)
        await db.add(row)
        return row
