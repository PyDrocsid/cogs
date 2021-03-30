from __future__ import annotations

from typing import Union

from PyDrocsid.database import db
from sqlalchemy import Column, BigInteger, Boolean


class RoleNotification(db.Base):
    __tablename__ = "role_notification"

    role_id: Union[Column, int] = Column(BigInteger, primary_key=True)
    channel_id: Union[Column, int] = Column(BigInteger, primary_key=True)
    ping_role: Union[Column, bool] = Column(Boolean)
    ping_user: Union[Column, bool] = Column(Boolean)

    @staticmethod
    async def create(role_id: int, channel_id: int, ping_role: bool, ping_user: bool) -> RoleNotification:
        row = RoleNotification(role_id=role_id, channel_id=channel_id, ping_role=ping_role, ping_user=ping_user)
        await db.add(row)
        return row
