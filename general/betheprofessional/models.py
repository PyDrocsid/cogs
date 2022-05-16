from __future__ import annotations

from sqlalchemy.orm import relationship, backref

from PyDrocsid.database import db, Base
from sqlalchemy import Column, BigInteger, Boolean, Integer, String, ForeignKey


class BTPTopic(Base):
    __tablename__ = "btp_topic"

    id: Column | int = Column(Integer, primary_key=True)
    name: Column | str = Column(String(255), unique=True)
    parent_id: Column | int = Column(Integer, ForeignKey('btp_topic.id', ondelete='CASCADE'))
    children: list[BTPTopic] = relationship(
        "BTPTopic",
        backref=backref("parent", remote_side=id, foreign_keys=[parent_id]),
        lazy="subquery",
    )
    role_id: Column | int = Column(BigInteger, unique=True)
    users: list[BTPUser] = relationship("BTPUser", back_populates="topic")
    assignable: Column | bool = Column(Boolean)

    @staticmethod
    async def create(
            name: str, role_id: int | None, assignable: bool, parent_id: int | None) -> BTPTopic:
        row = BTPTopic(name=name, role_id=role_id, parent_id=parent_id, assignable=assignable)
        await db.add(row)
        return row


class BTPUser(Base):
    __tablename__ = "btp_users"

    id: Column | int = Column(Integer, primary_key=True)
    user_id: Column | int = Column(BigInteger)
    topic_id: Column | int = Column(Integer, ForeignKey('btp_topic.id', ondelete='CASCADE'))
    topic: BTPTopic = relationship("BTPTopic", back_populates="users", lazy="subquery", foreign_keys=[topic_id])

    @staticmethod
    async def create(user_id: int, topic_id: int) -> BTPUser:
        row = BTPUser(user_id=user_id, topic_id=topic_id)
        await db.add(row)
        return row
