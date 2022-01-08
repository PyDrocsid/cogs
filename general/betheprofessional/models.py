from typing import Union, Optional
from PyDrocsid.database import db, Base
from sqlalchemy import Column, BigInteger, Boolean, Integer, String, ForeignKey


class BTPTopic(Base):
    __tablename__ = "btp_topic"

    id: Union[Column, int] = Column(Integer, primary_key=True)
    name: Union[Column, str] = Column(String(255))
    parent: Union[Column, int] = Column(Integer)
    role_id: Union[Column, int] = Column(BigInteger)
    assignable: Union[Column, bool] = Column(Boolean)

    @staticmethod
    async def create(
            name: str,
            role_id: Union[int, None],
            assignable: bool,
            parent: Optional[Union[int, None]],
    ) -> "BTPTopic":
        row = BTPTopic(name=name, role_id=role_id, parent=parent, assignable=assignable)
        await db.add(row)
        return row


class BTPUser(Base):
    __tablename__ = "btp_users"

    id: Union[Column, int] = Column(Integer, primary_key=True)
    user_id: Union[Column, int] = Column(BigInteger)
    topic: Union[Column, int] = Column(Integer, ForeignKey(BTPTopic.id))

    @staticmethod
    async def create(user_id: int, topic: int) -> "BTPUser":
        row = BTPUser(user_id=user_id, topic=topic)
        await db.add(row)
        return row
