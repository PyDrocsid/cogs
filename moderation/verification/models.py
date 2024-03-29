from __future__ import annotations

from typing import Union

from sqlalchemy import BigInteger, Boolean, Column

from PyDrocsid.database import Base, db


class VerificationRole(Base):
    __tablename__ = "verification_role"

    role_id: Union[Column, int] = Column(BigInteger, primary_key=True, unique=True)
    reverse: Union[Column, bool] = Column(Boolean)

    @staticmethod
    async def create(role_id: int, reverse: bool) -> VerificationRole:
        row = VerificationRole(role_id=role_id, reverse=reverse)
        await db.add(row)
        return row
