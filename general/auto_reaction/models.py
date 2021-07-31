from __future__ import annotations

from typing import Union

from PyDrocsid.database import db
from sqlalchemy import Column, Text, BigInteger, Table, ForeignKey
from sqlalchemy.orm import relationship


class AutoReactionChannel(db.Base):
    __tablename__ = "auto_reaction_channel"

    id: Union[Column, int] = Column(
        BigInteger, primary_key=True, unique=True, autoincrement=True
    )
    channel: Union[Column, int] = Column(BigInteger)
    reactions = relationship(
        "AutoReaction", secondary="auto_reaction_link", back_populates="channels"
    )

    @staticmethod
    async def create(channel_id: int) -> AutoReactionChannel:
        row = AutoReactionChannel(
            channel=channel_id,
        )
        await db.add(row)
        return row


class AutoReaction(db.Base):
    __tablename__ = "auto_reaction"

    id: Union[Column, int] = Column(
        BigInteger, primary_key=True, unique=True, autoincrement=True
    )
    reaction: Union[Column, str] = Column(Text(collation="utf8mb4_bin"))
    channels = relationship(
        "AutoReactionChannel",
        secondary="auto_reaction_link",
        back_populates="reactions",
    )

    @staticmethod
    async def create(reaction: str) -> AutoReaction:
        row = AutoReaction(
            reaction=reaction,
        )
        await db.add(row)
        return row


class AutoReactionLink(db.Base):
    __tablename__ = "auto_reaction_link"
    id: Union[Column, int] = Column(
        BigInteger, primary_key=True, unique=True, autoincrement=True
    )

    channel_id = Column(BigInteger, ForeignKey("auto_reaction_channel.id"))

    autoreaction_id = Column(BigInteger, ForeignKey("auto_reaction.id"))

    @staticmethod
    async def create(channel_id: int, autoreaction_id: int) -> AutoReactionLink:
        link = AutoReactionLink(channel_id=channel_id, autoreaction_id=autoreaction_id)
        await db.add(link)
        return link
