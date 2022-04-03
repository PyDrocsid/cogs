from __future__ import annotations

from typing import Union

from sqlalchemy import BigInteger, Boolean, Column

from PyDrocsid.database import Base, db, select


class RoleAuth(Base):
    __tablename__ = "role_auth"

    source: Union[Column, int] = Column(BigInteger, primary_key=True)
    target: Union[Column, int] = Column(BigInteger, primary_key=True)
    perma_allowed: Union[Column, bool] = Column(Boolean())

    @staticmethod
    async def add(source: int, target: int, perma_allowed: bool):
        await db.add(RoleAuth(source=source, target=target, perma_allowed=perma_allowed))

    @staticmethod
    async def check(source: int, target: int) -> bool:
        return await db.exists(select(RoleAuth).filter_by(source=source, target=target))


class PermaRole(Base):
    __tablename__ = "perma_role"

    member_id: Union[Column, int] = Column(BigInteger, primary_key=True)
    role_id: Union[Column, int] = Column(BigInteger, primary_key=True)

    @staticmethod
    async def add(member_id: int, role_id: int):
        await db.add(PermaRole(member_id=member_id, role_id=role_id))
