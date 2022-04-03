from typing import Union

from sqlalchemy import BigInteger, Column

from PyDrocsid.database import Base, db


class BTPRole(Base):
    __tablename__ = "btp_role"

    role_id: Union[Column, int] = Column(BigInteger, primary_key=True, unique=True)

    @staticmethod
    async def create(role_id: int) -> "BTPRole":
        row = BTPRole(role_id=role_id)
        await db.add(row)
        return row
