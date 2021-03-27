from __future__ import annotations

from typing import Union

from sqlalchemy import Column, BigInteger

from PyDrocsid.database import db, select


class RoleAuth(db.Base):
    __tablename__ = "role_auth"

    source: Union[Column, int] = Column(BigInteger, primary_key=True)
    target: Union[Column, int] = Column(BigInteger, primary_key=True)

    @staticmethod
    async def add(source: int, target: int):
        await db.add(RoleAuth(source=source, target=target))

    @staticmethod
    async def check(source: int, target: int) -> bool:
        return await db.exists(select(RoleAuth).filter_by(source=source, target=target))
