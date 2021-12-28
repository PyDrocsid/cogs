from __future__ import annotations

import re
from typing import Union, Optional

from PyDrocsid.database import db, select, Base
from sqlalchemy import Column, BigInteger, String, Boolean


def encode(emoji: str) -> str:
    if re.match(r"^<(a?):([a-zA-Z0-9_]+):([0-9]+)>$", emoji):
        return emoji
    return emoji.encode().hex()


def decode(emoji: str) -> str:
    if re.match(r"^<(a?):([a-zA-Z0-9_]+):([0-9]+)>$", emoji):
        return emoji
    return bytes.fromhex(emoji).decode()


class ReactionRole(Base):
    __tablename__ = "reactionrole"

    channel_id: Union[Column, int] = Column(BigInteger, primary_key=True)
    message_id: Union[Column, int] = Column(BigInteger, primary_key=True)
    emoji_hex: Union[Column, str] = Column(String(64), primary_key=True)
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
            emoji_hex=encode(emoji),
            role_id=role_id,
            reverse=reverse,
            auto_remove=auto_remove,
        )
        await db.add(row)
        return row

    @staticmethod
    async def get(channel_id: int, message_id: int, emoji: str) -> Optional[ReactionRole]:
        return await db.first(
            select(ReactionRole).filter_by(channel_id=channel_id, message_id=message_id, emoji_hex=encode(emoji)),
        )

    @property
    def emoji(self):
        return decode(self.emoji_hex)
