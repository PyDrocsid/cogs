from __future__ import annotations

from typing import Union, Optional

from PyDrocsid.database import db, select, Base
from sqlalchemy import Column, BigInteger, String, Boolean


class ReactionRole(Base):
    __tablename__ = "reactionrole"

    channel_id: Union[Column, int] = Column(BigInteger, primary_key=True)
    message_id: Union[Column, int] = Column(BigInteger, primary_key=True)
    emoji: Union[Column, str] = Column(String(64), primary_key=True)
    role_id: Union[Column, int] = Column(BigInteger)
    reverse: Union[Column, bool] = Column(Boolean)
    auto_remove: Union[Column, bool] = Column(Boolean)

    @staticmethod
    async def create(
        channel_id: int,
        message_id: int,
        emoji: str,
        role_id: int,
        reverse: bool,
        auto_remove: bool,
    ) -> ReactionRole:
        row = ReactionRole(
            channel_id=channel_id,
            message_id=message_id,
            emoji=emoji,
            role_id=role_id,
            reverse=reverse,
            auto_remove=auto_remove,
        )
        await db.add(row)
        return row

    @staticmethod
    async def get(channel_id: int, message_id: int, emoji: str) -> Optional[ReactionRole]:
        return await db.first(
            select(ReactionRole).filter_by(channel_id=channel_id, message_id=message_id, emoji=emoji),
        )
