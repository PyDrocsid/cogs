from __future__ import annotations

from PyDrocsid.database import db, Base
from sqlalchemy import Column, BigInteger, Boolean, Integer, String, ForeignKey


class BTPTopic(Base):
    __tablename__ = "btp_topic"

    id: Column | int = Column(Integer, primary_key=True)
    name: Column | str = Column(String(255), unique=True)
    parent: Column | int = Column(Integer)  # TODO foreign key?
    role_id: Column | int = Column(BigInteger, unique=True)
    assignable: Column | bool = Column(Boolean)

    @staticmethod
    async def create(
            name: str, role_id: int | None, assignable: bool, parent: int | None) -> BTPTopic:
        row = BTPTopic(name=name, role_id=role_id, parent=parent, assignable=assignable)
        await db.add(row)
        return row


class BTPUser(Base):
    __tablename__ = "btp_users"

    id: Column | int = Column(Integer, primary_key=True)
    user_id: Column | int = Column(BigInteger)
    topic: Column | int = Column(Integer, ForeignKey(BTPTopic.id))  # TODO use relationship

    @staticmethod
    async def create(user_id: int, topic: int) -> BTPUser:
        row = BTPUser(user_id=user_id, topic=topic)
        await db.add(row)
        return row
