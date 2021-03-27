from __future__ import annotations

from typing import Union

from PyDrocsid.database import db
from sqlalchemy import Column, BigInteger


class MediaOnlyChannel(db.Base):
    __tablename__ = "mediaonly_channel"

    channel: Union[Column, int] = Column(BigInteger, primary_key=True, unique=True)

    @staticmethod
    async def create(channel: int) -> MediaOnlyChannel:
        row = MediaOnlyChannel(channel=channel)
        await db.add(row)
        return row
