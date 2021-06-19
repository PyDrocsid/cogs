from typing import Union, Optional

from PyDrocsid.database import db
from sqlalchemy import Column, BigInteger, String, Integer, ForeignKey


class BTPTopic(db.Base):
    __tablename__ = "btp_topic"

    id: Union[Column, int] = Column(Integer, primary_key=True)
    name: Union[Column, str] = Column(String(255))
    parent: Union[Column, int] = Column(Integer)
    role_id: Union[Column, int] = Column(BigInteger)

    @staticmethod
    async def create(name: str, role_id: Union[int, None], parent: Optional[Union[int, None]]) -> "BTPTopic":
        row = BTPTopic(name=name, role_id=role_id, parent=parent)
        await db.add(row)
        return row


class BTPUser(db.Base):
    __tablename__ = "btp_users"

    user_id: Union[Column, int] = Column(BigInteger, primary_key=True)
    topic: Union[Column, int] = Column(Integer, ForeignKey(BTPTopic.id))

    @staticmethod
    async def create(user_id: int, topic: int) -> "BTPUser":
        row = BTPUser(user_id=user_id, topic=topic)
        await db.add(row)
        return row
